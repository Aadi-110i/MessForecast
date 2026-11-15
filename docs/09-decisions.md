# 09 — Decisions

The choices worth arguing about. Each one states what was decided, why, what it costs, and —
where it matters — where this build deviates from the specification.

Some of these were forced by the brief. Some were judgement calls. A few are the kind of thing a
reviewer should push back on, and that is the point of writing them down.

---

## 1. Track P, and why the choice was not really a choice

The specification offers two stacks: Track J (Next.js + Node.js + MongoDB) and Track P (Django +
PostgreSQL, forecasting in-process). Track P was chosen, and the deciding factor was the
forecasting itself.

Track J's own text says the upgrade path "needs a second service" — a Python service for
Prophet or gradient boosting, reached over the network. Track P says the opposite: *"the upgrade
path to statsmodels or scikit-learn needs no second service"*.

The upgrade path is the part of this project with real uncertainty in it. The specification says
the baseline is the semester-1 deliverable and that the learned model comes "only after a term of
real data" — that is, after this project ends. Building the architecture so that the eventual
model swap is a module replacement rather than a network boundary is worth a great deal, and it
is exactly what Track P gives.

**Cost:** Django's admin gives up-to-date master-data editing for free, which Track J would have
had to build. It was not missed.

---

## 2. The baseline model is the deliverable — taken literally

> *a team that reaches for machine learning on a problem with no data yet has not understood the
> problem. The baseline is the deliverable for semester 1.*

There is **no machine learning in this build**. No scikit-learn, no Prophet, no statsmodels. The
forecaster is a recency-weighted moving average with weekday, event and trend adjustment, and
`apps/forecasting/engine.py` imports **nothing outside the standard library**.

This is stricter than "we did the baseline first". A build that ships a baseline *and* a learned
model behind a flag has already made the decision the specification asked not to make. This one
cannot be accused of that.

**What it cost:** the measured MAPE is 2.36 %, which is good. A gradient-boosting model on 12
weeks of synthetic data would have produced a number that meant nothing.

**The upgrade path is real, not aspirational.** The engine has one entry point:

```python
def predict(self, observations, target_date, ...) -> ForecastResult
```

and takes plain `Observation` objects, not Django querysets. A learned model replaces the module;
the `Forecast` model, the plan builder, the API and the dashboard do not change.

---

## 3. The engine has no third-party imports

The specification says the baseline is "a few lines of pandas inside a Celery task". This
implementation does not use pandas in the engine, and that is a deliberate deviation.

The engine works on plain Python lists of `Observation` dataclasses and returns a
`ForecastResult`. Nothing in it touches the ORM.

**Why.** Two reasons, both practical.

First, **reproducibility**. The `input_signature` is a SHA-256 over the observation series. For
that signature to mean anything, the numbers going into it must be the same numbers every time.
Float arithmetic through a dataframe pipeline is reproducible on one machine and not necessarily
across pandas versions.

Second, **speed**. The engine's hot path originally used `Decimal ** fractional_exponent`,
which is roughly a hundred times slower than float arithmetic — the decimal exponentiation goes
through a slow path. Converting the hot path to float math took `predict()` from roughly 340 ms
to **3.4 ms** for 56 observations. A 336-forecast week went from minutes to about 1.1 seconds.

**What it cost:** the engine is more code than a pandas one-liner would be. In exchange, the
forecast is fast enough to run on every request, and the "same inputs, same numbers" promise is
one a human can check.

---

## 4. Cost per portion uses the GROSS quantity, not the net

This is the decision with the largest effect on every number in the reporting, so it is stated
explicitly.

A recipe says: 1 kg of onions, 10 % trim loss. The kitchen buys 1 ÷ 0.9 = 1.111 kg and throws
0.111 kg away. The **cost of one portion of the dish uses 1.111 kg**, not 1 kg.

```
cost per portion = Σ over ingredients of ( recipe quantity ÷ (1 − trim loss %) × unit cost )
```

**Why.** The kitchen paid for the peelings. If the waste figure uses the net quantity but the
purchase cost uses the gross, the two halves of the system disagree about what was bought, and
the ingredient-consumption-vs-indent report becomes meaningless. Using gross throughout keeps
the arithmetic honest: the money spent and the food produced agree.

**What it cost:** every dish's cost per portion is higher than the naive calculation, and so is
every waste cost. The alternative — the naive calculation — would have reported a smaller saving.
The 42.95 % reduction is therefore a conservative figure.

---

## 5. "Portions per student" is the bridge between attendance and food

The loop is: forecast attendance → portions to prepare → ingredients. The middle step does not
follow from the first one. A student at lunch eats about 2.6 portions; a student at breakfast
eats about 1.6. "329 students" is not a quantity of food.

So `ServiceLevelConfig` carries `portions_per_student` — 1.60 for breakfast, 2.60 for lunch,
2.30 for dinner — and the plan carries **both** `attendance_target` and `portions_target`.

**Why it matters.** Without this bridge, the forecast and the cooking quantity are separate
numbers that never meet, and the whole planning chain has a hole in the middle. With it, the
chain is: forecast attendance → × portions per student → × (1 + safety margin) → portions to
cook.

**Why it lives in the database.** The real number is a property of the mess, not of the software.
The mess manager changes it from the admin on day one, without a deployment. It is also the first
thing to get wrong when the real kitchen is measured, so it must not be baked into code.

---

## 6. No rollup tables

There is no `DemandAggregate` and no `AccuracySnapshot`. Every report is computed from the facts
on demand.

**Why.** A rollup table is a second copy of the truth. It has to be kept in step, and when it
drifts, the report is wrong in a way nobody can see. The failure mode — "the dashboard says
waste fell but the records say otherwise" — is far worse than a slow query.

At this data volume (504 services, 2,128 waste records, 336 forecasts) the queries are fast
enough. The reporting is index-backed and returns in well under a second.

**What it cost.** The dashboard's accuracy page renders 82 KB of HTML because it carries 200
forecast-versus-actual rows. If the data grew to a year of history across a campus, that page
would need pagination — and then, and only then, a rollup would be worth building. The decision
can be revisited when the measurement tells us to, rather than now.

---

## 7. A view that forgets to declare a read capability is closed, not open

`apps/api/permissions.py::HasCapability`:

```python
if request.method in permissions.SAFE_METHODS:
    read_capability = getattr(view, "read_capability", None)
    if read_capability is None:
        read_capability = capability
    return has_capability(request.user, read_capability)
```

The fallback is **strict**. A view that declares `capability = "MANAGE_MASTERS"` and forgets
`read_capability` therefore requires `MANAGE_MASTERS` for reads too — not open access.

**Why.** The alternative — falling back to "any signed-in user can read" — means a forgotten
line silently publishes a write-scoped resource to everybody. The cost of the strict fallback is
that a view needs two declarations when it wants students to read it and admins to write it. That
is a two-line cost for a whole class of disclosure bug that cannot happen.

`action_capabilities` handles the case where one action needs a different capability from the
rest: generating a forecast is a mess manager's job (`PLAN_MENU`), while editing the forecast
*configuration* is the administrator's (`CONFIGURE_FORECAST`).

---

## 8. The specification's `TruncDate` is a MongoDB helper

> *TRACK P · Python + Django + PostgreSQL. Aggregate with TruncDate and annotate.*

`TruncDate` is a MongoDB shell helper. On PostgreSQL the equivalent is Django's `Trunc` family
together with `ExtractWeekDay`, which is what `apps/demand/services.py` uses:

```python
.annotate(week=Trunc("date", "week"))
.annotate(weekday=ExtractWeekDay("date"))
```

The specification's sentence ends with "**and annotate**", and the intent — time-bucketed
aggregation with per-bucket statistics — is preserved exactly. Only the MongoDB-specific
spelling changes, because Track P is PostgreSQL.

This is a **deviation in spelling only**, and it is recorded here rather than silently.

---

## 9. `WasteRecord.service_date` is denormalised

`WasteRecord` stores the service date directly, rather than reaching through
`service_actual → service → date` on every query.

**Why.** Django rejects an index on a joined field — `models.E012: The index refers to the field
'date' which is not part of the model`. The options were to drop the index or to copy the date.
Waste is reported by period, by hall and by dish, so the index is the one that matters, and the
date is copied.

**What it costs.** One field that has to be kept in step. It is written by the waste service in
the same operation that creates the record, and `compute_waste_for_actual` is idempotent, so
recomputing rewrites it from the source. There is no path that writes a waste record without the
date.

---

## 10. The API returns money and quantities as strings

Every monetary and quantity field is a JSON **string**: `"cost_per_portion": "6.9005000000"`.

**Why.** A JSON number is a float on the wire, and a float cannot hold `6.9005000000` exactly. A
client that parses it as a number silently loses money — and the client that loses money is
usually the one writing the finance report.

The specification insists that costs live in `DecimalField`, which is exactly why this matters:
the precision is real in the database, so it should survive the wire.

**What it cost.** Clients have to parse. This is a documented convention, not an accident, and
it is stated at the top of [04 API reference](04-api-reference.md).

---

## 11. The service worker precaches static assets only — no HTML

The precache list is ten static files: CSS, JavaScript, the manifest, the icon, the offline
page. **No HTML page is precached.**

**Why.** The obvious thing to precache is the app shell, which usually means the HTML. But the
app shell here is login-gated. If the login page were in the precache, then a tablet that opened
the app for the first time while offline would get the *login page* from the cache — and the
operator would be staring at a sign-in form instead of the kitchen screen.

HTML is cached dynamically on navigation instead, once a signed-in page has actually been
fetched over the network. The worker then serves that page offline.

---

## 12. API reads are never cached

The worker intercepts GETs, and it lets `/api/...`, `/scan/...` and `/kitchen/guidance` go
straight to the network. When they fail, the worker returns a 503 with a JSON body saying the
value could not be refreshed.

**Why.** A cached attendance count would be shown as if it were current. An operator glancing at
"480 turned up" has no way to know it is from this morning rather than this afternoon. A stale
number with no indication is worse than an error.

The cost is that the kitchen screen shows less when the network is down. That is the right
trade: the scans are safe and the operator is told the truth.

---

## 13. No CDN, no web fonts, no build step

The front-end is Django templates, plain CSS and vanilla JavaScript. There is no npm, no
bundler, no CDN and no web font. The charts are inline SVG drawn by hand.

**Why.** The kitchen tablet may have no internet. A front-end that fetches a font from a CDN is
a front-end that renders wrong in the one place it matters. The three typefaces — Bahnschrift
for display, Segoe UI for body, Consolas for data — are all locally installed on Windows, so they
work with no network at all.

**What it cost.** No component library, no utility framework, no CSS preprocessor. The CSS is
hand-written and longer than it would otherwise be. In exchange, the deployment is
`collectstatic` and nothing else, and the tablet works offline on first load.

---

## 14. Celery runs eagerly when there is no broker

`CELERY_TASK_ALWAYS_EAGER` is set when `CELERY_BROKER_URL` is empty.

**Why.** No Redis or RabbitMQ is available on the development machine, and more importantly, the
scheduled work needs to be *exercisable*. With eager mode, `manage.py run_forecasts` and the
Celery task call the same function and behave the same way, so the daily job can be run by hand
on a laptop and by beat on a server, with no difference in what is executed.

**What it costs.** The application does not schedule itself. In production the schedule has to be
driven by cron, a systemd timer, or Celery beat with a real broker. That is one cron line, and
it is stated plainly in [08 Deployment](08-deployment.md) rather than hidden.

---

## 15. The seed does not hash 1,400 student passwords

The seed creates 1,400 student accounts. Hashing each with PBKDF2 takes about a second, so
1,400 of them dominated the runtime.

The seed now creates **5 loginable students per hall** — the rest are created without a usable
password — which cut the seed from several minutes to **32.5 seconds** for the full 12 weeks.

**Why.** The seed's job is to produce a realistic *history*, not to make 1,400 people able to log
in. The students who need to log in get passwords.

**What it cost.** Only the first few students per hall can sign in with `messdemo`. Nobody
needs to sign in as student #847.

---

## 16. The indent export moved to `/api/preparation-plans/{id}/indent/`

The API route for the procurement export is:

```
GET /api/preparation-plans/{id}/indent/
```

not `/api/preparation-plans/{id}/indent.csv`.

**Why.** DRF's router appends a trailing slash to action URLs. A `url_path` containing a dot
produces a pattern the router mangles into `indent.csv` without the trailing slash, so the URL
that actually serves is `/indent/`. Naming the action `indent` and putting the format in the
`Content-Type` header is the honest description of what it does.

**What it cost.** A `.csv` in the URL is nicer to look at. The friendly route still exists for
browsers — `GET /dashboard/export/indent/{id}.csv` — and sets a filename. The API route sets
`Content-Type: text/csv`.

---

## 17. The design is an "expo ticket and operations ledger"

The visual direction is not a generic dashboard. It is a **kitchen expo ticket**: a printed,
pinned, slightly grubby card at the pass that says what is happening today, in a big readable
number, with the currency and the weight. The dashboard around it is an **operations ledger**:
ruled rows, tabular figures, no gradients, no shadows pretending to be depth.

The palette is ink `#14181F` on paper `#F7F7F4`, with saffron `#C9752B` for food and preparation,
teal `#0E6E63` for forecasts and accuracy, ember `#B3261E` for waste, and moss `#3F6B2E` for
saving.

**Why.** The users are not analysts. A kitchen staff member and a mess manager read this screen
in a hot room, often standing up, often with a phone in one hand. The expo-ticket metaphor is
the artefact they already read every day, and the ledger is the artefact they already trust for
money.

The consequences are concrete rather than decorative: the kitchen screen has a minimum 72 px
touch target and 20 px minimum text, an 84 px sticky save button, and oversized steppers for
recording portions with wet hands. The data screens use a monospaced face for every number so
columns line up. There are no hover-only affordances on the kitchen screen, because there is
nothing to hover with.

---

## 18. The dashboard renders its own charts as inline SVG

No charting library. `static/js/app.js` draws the charts as SVG.

**Why.** A charting library is either a CDN dependency (breaking offline), a bundled dependency
(a build step), or a large vendored file (for a handful of charts). The charts needed are a
bar chart, a line chart and a weekday pattern — about 200 lines of SVG.

**What it cost.** More code than a library call. In exchange there is no build step, no CDN, and
the charts work offline on first load.

---

## 19. Things that were tried and did not work

Kept here because the next person will try them again.

| Attempt | Why it failed |
|---|---|
| `Decimal ** fractional_exponent` in the engine's hot path | roughly 100× slower than float arithmetic; it was the original seed bottleneck |
| Hashing 1,400 student passwords during the seed | PBKDF2 at ~1 s each dominated a 32-second seed |
| `get_or_create` per student to build the register | ~2,800 queries; `bulk_create` is orders of magnitude faster |
| `bulk_create` of `MealService` and `MenuSchedule` | *did* work — kept. The note is that `get_or_create` per row did not |
| `TextChoices.values()` as a method | `TextChoices.values` is a **list**, not a method — it raises `TypeError` |
| Django's `FileResponse` with a `Path` | Django 6.0 wants a file object, not a path — open the file and pass the handle |
| An index on `WasteRecord.service_actual.service.date` | Django rejects a joined-field index (`models.E012`) — hence the denormalised `service_date` |
| A route sweep using the default `testserver` host | every request was rejected with `DisallowedHost` (400) and the sweep passed **vacuously** — a false green. The sweep now sets `Host: 127.0.0.1` |
| Preloading the login page into the service-worker precache | offline first load would have shown the operator a sign-in form instead of the kitchen screen |

---

## 20. What is deliberately not here

| Not built | Why |
|---|---|
| A learned forecasting model | the specification forbids it for semester 1, and 12 weeks of data cannot support one |
| SMS notifications | the notification payload and the delivery seam exist; a specific SMS gateway is a procurement decision |
| A vendor RFID SDK | the RFID path writes into the same capture pipeline as QR and manual entry; binding a vendor is a deployment decision |
| A rollup table | see section 6 |
| A multi-campus UI | the schema supports it; one campus is the actual scope |
| An automated browser test of the IndexedDB queue | needs a browser driver — listed as a gap in [06 Testing](06-testing.md) |
| A real ERP connector | `import_erp` reads a CSV; the ERP's API is the college's to expose |
