# 06 — Testing

What was tested, how, and what came out. Every figure in this document came from a run of this
code against a live PostgreSQL 18.1 database. Nothing is estimated, and nothing is quoted from a
benchmark that was not performed here.

---

## 1. The suite

```
python manage.py test
```

**70 tests, all passing.**

| File | Tests | Covers |
|---|---:|---|
| `tests/test_attendance_sync.py` | 8 | offline capture, sync idempotency, the audit trail |
| `tests/test_forecasting.py` | 13 | reproducibility, the input signature, cold start, event adjustment, the confidence interval |
| `tests/test_waste_costing.py` | 9 | the cost arithmetic, reconciled against a manual calculation for a full week |
| `tests/test_planning.py` | 10 | forecast → portions → dish split → recipe → indent → CSV |
| `tests/test_api.py` | 16 | authentication, role permissions, sync over HTTP, forecast generation, the analytics endpoints, the CSV export |
| `tests/test_performance.py` | 2 | the 3,000-scan acceptance criterion |
| `tests/test_regressions.py` | 14 | the 500s the route sweep found, pinned so they cannot come back |
| **Total** | **70** | |

The suite runs against a real PostgreSQL database (`test_messforecast`), not SQLite. A SQLite
test suite would not have caught any of the aggregation, `Decimal` or constraint behaviour this
project depends on.

---

## 2. The four requirements the specification names by hand

> *Specific: offline attendance capture and sync, including a duplicate-submission case; forecast
> reproducibility; waste cost arithmetic verified against a manual calculation for a full week.*

### 2.1 Offline capture and sync, including a duplicate-submission case

`tests/test_attendance_sync.py` — 8 tests.

| Test | What it proves |
|---|---|
| `test_batch_of_scans_is_stored` | a batch arrives and is stored |
| `test_resending_the_same_batch_stores_nothing_new` | **the duplicate-submission case** — the same batch again creates 0 rows |
| `test_a_single_duplicated_uuid_inside_one_batch_is_stored_once` | a tablet that queued the same scan twice before reaching the server stores it once |
| `test_a_record_already_stored_by_another_device_is_ignored` | two tablets sending the same student do not double-count |
| `test_malformed_uuid_is_rejected_without_losing_the_batch` | one bad UUID is rejected and the rest of the batch still lands |
| `test_sync_is_audited` | an `AttendanceAudit` row records received / created / duplicates / failed |
| `test_scan_for_an_unknown_hall_slot_creates_the_service` | a scan for a service that does not exist yet creates it on demand |

The idempotency mechanism is a unique constraint on `client_uuid` plus
`bulk_create(ignore_conflicts=True)`. The service counts what it created and what it dropped
*exactly*, rather than inferring it — which is why the response can tell the kitchen operator
"1 added, 1 already had it".

Verified over real HTTP as well as in-process: `scripts/verify_e2e.py` posts the same batch
twice against the running server and asserts `created=1` then `created=0, duplicates=1`.

### 2.2 Forecast reproducibility

`tests/test_forecasting.py` — 13 tests.

| Test | What it proves |
|---|---|
| `test_same_history_gives_the_same_forecast` | identical inputs → identical numbers |
| `test_a_fresh_forecaster_instance_reproduces_the_same_numbers` | a new object, not a cached one |
| `test_input_signature_changes_when_the_history_changes` | the SHA-256 `input_signature` is a real fingerprint of the inputs |
| `test_regenerating_the_forecast_gives_the_same_signature` | re-running the forecaster on unchanged data does not churn the row |

The signature is a SHA-256 over the sorted observation series plus the target date, the event
factor, the registered strength and the model version. Same signature → same forecast, always.
That is what makes the forecast reproducible and auditable rather than merely plausible.

### 2.3 Waste cost arithmetic, verified against a manual calculation for a full week

`tests/test_waste_costing.py` — 9 tests. The week reconciliation is the important one.

| Test | What it proves |
|---|---|
| `test_the_cost_of_one_portion_is_the_recipe_times_the_prices` | cost per portion = recipe quantity × unit cost, with trim loss |
| `test_a_full_week_reconciles_with_a_manual_calculation` | **the specification's named check** — every waste record in a week is recomputed by hand in the test and compared |
| `test_trim_loss_is_included_in_the_cost` | the kitchen paid for the peelings, so trim loss is in the cost |
| `test_recomputing_waste_is_idempotent` | running it twice leaves the same numbers |
| `test_a_dish_with_no_recipe_costs_nothing` | a missing recipe is not silently costed at zero without saying so |
| `test_top_waste_dishes_are_ranked_by_cost` | the top-ten report ranks by rupees |
| `test_totals_can_be_scoped_to_one_hall` | and `test_waste_by_meal_is_reported` — the report scopes correctly |

**The costing rule, stated once so it can be checked by hand:** the cost of a portion of a dish is
the sum, over every ingredient in the recipe, of

```
recipe quantity ÷ (1 − trim loss %) × unit cost
```

The division by `(1 − trim loss)` is deliberate. If a recipe says 1 kg of onions with 10 % trim
loss, the kitchen buys 1 / 0.9 = 1.111 kg and throws 0.111 kg away. Charging the portion for
1 kg would understate the real cost of the food. This is a deviation from the most obvious
reading of "recipe quantity × unit cost", and it is documented in
[09 Decisions](09-decisions.md).

### 2.4 3,000 attendance records in a 45-minute window across halls, without loss

`tests/test_performance.py` — 2 tests. This is the acceptance criterion in section 22.

Measured on the live PostgreSQL database, through the same `sync_attendance_batch` the offline
queue drains into:

```
3,000 scans sent in a single batch
  created      : 3000
  duplicates   : 0
  stored       : 3000
  elapsed      : 5.544 s
  throughput   : 541 scans/second
  per scan     : 1.848 ms

  a 45-minute window at one scan per second needs 2,700 scans
  headroom     : 5x

replay of the same 3,000 scans
  created      : 0
  duplicates   : 3000
  stored       : 3000
  elapsed      : 0.088 s
```

Reproduce with `python scripts/bench_sync.py` — it runs inside a transaction it rolls back, so
the database is untouched.

A 45-minute service window at one scan per second needs 2,700 scans. The write path handles
3,000 in 5.5 seconds — **five times the headroom** — and a full re-send of the same 3,000 scans
is rejected in 0.088 s without changing a row.

The replay is the more important half of this result. A tablet that loses its connection mid-sync
and retries the entire batch is the normal failure case, not the exceptional one.

> **This number is hardware-dependent.** The 5.5 s figure is from the author's machine. On a
> Windows workstation with PostgreSQL 18 the same batch takes 9.2 s (326 scans/second), and on a
> cold disk it has been measured at around 70 s — which is why the wall-clock assertion in
> `tests/test_performance.py` is the only one that is sensitive to the machine. The write path is
> unchanged; every functional assertion (3,000 created, 0 duplicates, 3,000 stored, 0 created on
> replay) passes on either.

---

## 3. The API and permission tests

`tests/test_api.py` — 16 tests.

| Area | Covered |
|---|---|
| Authentication | anonymous access refused; a signed-in user reads services |
| Role permissions | a student cannot read the waste report; a finance officer can; a finance officer cannot change a dish; a mess administrator can create a dish; a student cannot sync attendance |
| Sync over HTTP | the sync endpoint is idempotent |
| Forecasting | forecasts can be generated and read; the forecast carries its explanation |
| Analytics | the demand report gives the weekday pattern; the accuracy report gives the summary |
| Master data | the menu endpoint returns the dishes on a menu; the dish endpoint exposes the derived cost |
| Export | the indent export is a CSV |

---

## 4. The regression tests

`tests/test_regressions.py` — 14 tests. These exist because a route sweep found three real
server errors late in the build, and a bug that was found once can come back.

| The bug | The regression test |
|---|---|
| The dashboard overview called the demand helpers on the reporting module, so signing in returned a 500 | `test_the_overview_page_renders`, `test_every_dashboard_page_renders` |
| `/api/analytics/savings` indexed straight into the query string, so a missing date was a 500 | `test_missing_dates_return_400_not_500`, `test_a_mistyped_date_returns_400_not_500` |
| The capture screen's live-count endpoint used `request.query_params`, which only exists on a DRF request | `test_the_live_count_is_returned`, `test_a_missing_service_id_is_a_400` |
| Django's default `LOGIN_REDIRECT_URL` pointed at `/accounts/profile/`, a URL this project does not serve | `test_sign_in_redirects_to_the_dashboard`, `test_the_redirect_target_actually_resolves` |

The wider principle the tests encode: **a client mistake is a 4xx, never a 500.** A missing date,
a mistyped date and a missing service id are all user errors and are all now answers with a
400 that names the offending field.

---

## 5. The route sweep

`scripts/sweep_urls.py` is not a unit test — it is a smoke test over the whole application, run
against the seeded database.

```
python scripts/sweep_urls.py
```

```
Swept 615 route requests across 5 roles
Status codes: 200x=448, 400x=10, 403x=106, 404x=5, 405x=46
Skipped 15 route requests (2 distinct):
    notification-detail, password_reset_confirm
No 5xx responses.
```

What it does:

* walks the entire URL tree, including the DRF router's patterns, and resolves each one with
  `reverse()` so it tests the routes Django actually serves;
* uses **real primary keys**, so detail routes render actual data instead of 404-ing early;
* signs in as all five roles — mess manager, kitchen staff, mess administrator, finance officer,
  student — because a route can be safe for one role and fatal for another;
* issues GET on every route and POST on the six that only accept POST;
* prints the full traceback for any 5xx.

The 403s are the permission system working: 106 requests were correctly refused. The 404s are
routes whose parameter is a stale id. The 405s are GET on POST-only endpoints. The two skipped
routes need a password-reset token and a notification row, neither of which exists in a clean
seed.

This sweep found all three of the 500s listed in section 4. It is cheap to run and it is the
reason the application has no known server errors.

---

## 6. The end-to-end verification

`scripts/verify_e2e.py` drives the running server over real HTTP.

```
python scripts/verify_e2e.py http://127.0.0.1:8013
```

```
  login page                                     PASS  HTTP 200
  sign in as manager                             PASS
  dashboard: overview                            PASS  HTTP 200, 14031 bytes
  dashboard: waste                               PASS  HTTP 200, 11918 bytes
  dashboard: accuracy                            PASS  HTTP 200, 82744 bytes
  dashboard: planning                            PASS  HTTP 200, 834009 bytes
  dashboard: data quality                        PASS  HTTP 200, 5562 bytes
  kitchen screen                                 PASS  HTTP 200, 3386 bytes
  capture screen                                 PASS  HTTP 200, 7224 bytes
  service worker                                 PASS  HTTP 200, cache-control: no-cache, no-store, must-revalidate
  service worker scope header                    PASS  /
  manifest                                       PASS  HTTP 200, application/manifest+json
  api: services                                  PASS  HTTP 200
  api: forecasts                                 PASS  HTTP 200
  api: preparation plans                         PASS  HTTP 200
  api: actuals                                   PASS  HTTP 200
  api: menus                                     PASS  HTTP 200
  api: waste analytics                           PASS  HTTP 200
  api: accuracy analytics                        PASS  HTTP 200
  api: demand analytics                          PASS  HTTP 200
  api: ingredients                               PASS  HTTP 200
  offline sync: first send creates the record    PASS  HTTP 200, created=1
  offline sync: re-send is ignored (idempotent)  PASS  HTTP 200, created=0, duplicates=1

23/23 checks passed
```

This is the check that a real browser would perform: sign in with a form and a CSRF token, load
every screen, confirm the service worker and manifest are served with the right headers, read
every analytics endpoint, and prove the sync is idempotent over the wire.

---

## 7. The measured results

### 7.1 Waste, before and after

From `manage.py seed_demo --reset --weeks 12 --baseline-weeks 4`, run against a live database:

| | Baseline period<br>2026-08-14 → 2026-09-10 | Live period<br>2026-09-11 → 2026-11-05 |
|---|---:|---:|
| Waste cost | Rs 224,207.91 | Rs 255,823.37 |
| Waste weight | 3,208.900 kg | 3,683.230 kg |
| **Waste per service** | **Rs 1,334.57** | **Rs 761.38** |

| | |
|---|---:|
| Saving per service | **Rs 573.19** |
| Reduction | **42.95 %** |
| Annualised | **Rs 515,872.63** |

The total waste went *up* in rupees while the waste *per service* went down by 43 %, because the
live period ran more meals (8 weeks against 4). The honest comparison is per service, and it is
the one the specification asks for: the same mess, the same menu cycles, the same students —
cooking to the forecast instead of to the register.

The baseline is the honest kind of baseline: the kitchen cooked to **registered strength** plus a
16 % cushion, which is exactly what the specification describes as the problem
("Kitchens prepare against registered strength, not actual demand"). The live period cooked to the
forecast plus an 8 % margin. The 43 % gap is the space between the two habits.

### 7.2 Forecast accuracy

| | |
|---|---:|
| MAPE over the live period | **2.36 %** |
| Forecasts scored | **336** |
| Actuals inside the published 80 % interval | **93.15 %** |

The accuracy figure is over the **8-week** measurement period the specification requires
(section 22: *"improving over an 8-week measurement period"*).

### 7.3 Forecast generation cost

`python scripts/bench_forecaster.py`:

```
forecast_service() over 60 services
  mean   : 16.241 ms
  median : 15.858 ms
  p95    : 18.772 ms
  max    : 21.983 ms

42 forecasts in 651.8 ms (15.520 ms each)
a 7-day x 2-hall week (42 services) takes about 0.652 s
```

A full week's forecasts for both halls cost under a second. The daily job has no performance
problem.

### 7.4 Seed runtime

```
SEED WALL CLOCK: 32.5 s
```

for 504 services, 504 menu schedules, 336 walk-forward forecasts, 336 preparation plans,
336 indents, 504 actuals, 2,128 waste records and 5,613 individual attendance records.

---

## 8. What is *not* covered

Stated plainly, because a test suite that only lists its successes is not a useful document.

| Gap | Why | What would close it |
|---|---|---|
| **Kitchen screen usability with gloved hands and real staff** | it needs actual kitchen staff and a kitchen | a supervised usability session on the tablet, with the staff who will use it. This is the specification's own acceptance criterion and it is **not yet met** |
| **Browser-level offline behaviour** | the offline queue and service worker are tested at the API boundary and by reading the code; no automated browser drives the IndexedDB queue | a Playwright or Selenium run that loads `/scan/` with the network disabled, scans, restores the network, and asserts one record lands |
| **Load testing the dashboard under concurrent operators** | the system has one mess manager, not a thousand | a multi-user load test, only worth doing if the deployment grows beyond a single campus |
| **Multi-campus behaviour** | one campus, two halls | the schema supports it; it has not been exercised with a third site |
| **Real RFID hardware** | the RFID path is the same capture pipeline as QR and manual; no vendor SDK is bound | a reader on the campus network posting the same payload shape |

---

## 9. How to run everything

```bash
# the suite (70 tests, ~60 s)
python manage.py test

# the route sweep against the seeded database
python scripts/sweep_urls.py

# the end-to-end HTTP verification against a running server
python manage.py runserver 8013 --noreload      # in one shell
python scripts/verify_e2e.py http://127.0.0.1:8013

# the benchmarks
python scripts/bench_forecaster.py
python scripts/bench_sync.py
```

The last two leave the database unchanged — the sync benchmark runs inside a transaction it
rolls back.
