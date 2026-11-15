# 07 — Milestones

The specification sets the schedule:

> *M0 discovery and recipe data capture (2w) · M1 masters, attendance, calendar (3w) · M2 analysis
> and forecasting (2w) · M3 planning and actuals (2w) · M4 waste costing and reporting (2w) · M5
> UAT and production (1w).*

Twelve weeks. This document maps the delivered build onto that schedule, states what each
milestone produced, and is honest about which parts of M0 and M5 need the campus rather than a
developer.

---

## The plan against the schedule

| Milestone | Weeks | Specification scope | Delivered | Status |
|---|---:|---|---|---|
| **M0** Discovery and recipe data capture | 2 | Understand the kitchen, capture recipes | Recipe and cost master modelled and seeded; demand-analysis modules built to settle what to capture | **Done, with a gap** — see below |
| **M1** Masters, attendance, calendar | 3 | M1, M2, M3 modules | `apps/catalog`, `apps/menu`, `apps/attendance`, `apps/events` | **Done** |
| **M2** Analysis and forecasting | 2 | M4, M5 modules | `apps/demand`, `apps/forecasting` | **Done** |
| **M3** Planning and actuals | 2 | M6, M7 modules | `apps/planning`, `apps/actuals`, the kitchen tablet screen | **Done** |
| **M4** Waste costing and reporting | 2 | M8, M9 modules | `apps/waste`, `apps/reporting`, the dashboard, the API | **Done** |
| **M5** UAT and production | 1 | Deployment, documentation, UAT | Deployment guide, full documentation, seed pipeline, verification tooling | **Partly done** — UAT needs the campus |

---

## M0 — Discovery and recipe data capture (2 weeks)

**Specification:** *"discovery and recipe data capture"*.

### What was built

The recipe master is the thing M0 exists to produce, and it is the thing every later milestone
depends on. Without a recipe, there is no cost, no indent and no waste figure.

* `Ingredient` with a base unit, a purchase pack size and a pack unit — because a kitchen does
  not buy 2.3 kg of rice, it buys a 25 kg bag.
* `CostRate` as a separate, effective-dated table, so a price change on 1 November does not
  rewrite last month's waste.
* `Recipe` with a version and an effective date, so a recipe can be corrected without erasing
  history.
* `RecipeItem` carrying the quantity, the unit and the **trim loss percentage** — the field that
  turns a recipe into a cost.
* `Dish` with a serving size, which is what connects "portions" to "grams".

Seeded with 26 ingredients, 20 dishes, 20 recipes and 79 recipe lines, each ingredient priced in
rupees per base unit.

### The discovery work, done in code

The modules that usually come after M0 were built early, because they answer the questions M0 is
supposed to ask:

| Question the discovery phase must answer | Where it is answered |
|---|---|
| How much does one portion of a dish cost? | `apps/catalog/models.py::Dish.cost_per_portion` |
| How many portions does one student eat? | `ServiceLevelConfig.portions_per_student` — 1.60 breakfast, 2.60 lunch, 2.30 dinner |
| What is the kitchen's acceptable cushion? | `ServiceLevelConfig.acceptable_overprep_pct` and `max_overprep_pct` |
| How much does the menu actually rotate through? | `apps/menu/models.py` — 3 menu cycles, 38 menu items, 504 schedules |
| What moves demand most? | `apps/demand/services.py::attendance_by_period` — exam services ran at 422.7 students against 208.4 on ordinary days, a 102.8 % lift |

That last line is the reason the academic calendar is a first-class feature of the forecaster and
not a note in a comment. It was measured before the forecaster was written.

### The gap

**No real recipe data from the campus kitchen was captured.** The 20 recipes in the seeded
database are plausible, internally consistent and costed, but they are not the mess's actual
recipes. M0 in the specification is a *field* activity: standing in a kitchen with a notebook
while someone cooks.

This matters and is stated rather than glossed:

* the cost figures, and therefore the waste cost and the saving, are correct **as arithmetic**
  over the recipe data provided — and will be as correct as the recipes are once the real ones
  are loaded;
* the **dish mix** in the demand model is assumed, not observed. The forecaster learns each
  dish's share from the actuals, so it self-corrects over a term of real service;
* the **portion sizes** (1.60 / 2.60 / 2.30) are a starting point. They live in
  `ServiceLevelConfig`, not in code, precisely so the mess manager can change them from the
  database on day one without a deployment.

**To close it:** load the real recipes through the Django admin (or `import_erp`), set the real
portion sizes, and re-measure. Nothing else in the system needs to change.

---

## M1 — Masters, attendance, calendar (3 weeks)

**Specification:** M1 (menu, dish, recipe), M2 (attendance capture), M3 (calendar and events).

| Deliverable | Where | Evidence |
|---|---|---|
| Dining halls, ingredients, dishes, versioned recipes, effective-dated costs | `apps/catalog/` | 2 halls, 26 ingredients, 20 dishes, 20 recipes, 79 recipe lines, 26 cost rates |
| Menus, menu items, the menu calendar | `apps/menu/` | 3 menu cycles, 38 menu items, 504 schedules |
| Per-service attendance by QR, RFID or manual entry | `apps/attendance/`, `templates/scan/` | 5,613 individual scan records in the seed; 8 sync tests |
| Offline tolerance with client-UUID idempotency | `apps/attendance/services.py`, `static/pwa/offline-queue.js` | replay of 3,000 scans creates 0 rows in 0.088 s |
| Academic calendar, holidays, exams, festivals, vacations | `apps/events/` | 7 calendar events with impact factors |
| Service-level configuration | `apps/events/models.py::ServiceLevelConfig` | 4 configurations (per hall × meal) |
| Role model with six roles | `apps/accounts/` | one capability table, enforced in the API and the screens |

**The decision that shaped this milestone:** the attendance record carries a **client-generated
UUID** with a unique constraint, and the sync endpoint is a batch endpoint that returns an exact
count of what it created and what it dropped. Everything about the offline story follows from
that one choice, so it was made here and settled.

---

## M2 — Analysis and forecasting (2 weeks)

**Specification:** M4 (historical demand analysis), M5 (forecasting engine with confidence range).

| Deliverable | Where | Evidence |
|---|---|---|
| Aggregation by meal, weekday, week, event type, exam period, dish | `apps/demand/services.py` | `GET /api/analytics/demand` |
| A statistical baseline with weekday, event and trend adjustment | `apps/forecasting/engine.py` | written out in plain language in [05 Forecast method](05-forecast-method.md) |
| A confidence interval | `apps/forecasting/engine.py` — inverse-normal quantile on the backtest RMSE | 80 % interval; **93.15 %** of actuals landed inside it |
| A plain-language explanation for every forecast | `apps/forecasting/engine.py` → `explanation` | every forecast in the API carries one |
| Reproducibility | SHA-256 `input_signature` | `tests/test_forecasting.py` — 13 tests |
| Walk-forward backtest that measures the forecaster's own error | `BaselineForecaster.backtest` | `rmse` and `mape` on every forecast row |

**The decision that shaped this milestone:** the specification says the baseline statistical model
is the semester-1 deliverable and that a learned model waits for a term of real data. That was
taken literally. There is no machine learning in this build, the engine has **no third-party
imports at all**, and it is one module with one entry point — so a learned model replaces the
module and nothing else.

The measured result over the 8-week live window: **MAPE 2.36 %** across **336** forecasts.

---

## M3 — Planning and actuals (2 weeks)

**Specification:** M6 (preparation and ingredient planning), M7 (post-service actuals).

| Deliverable | Where | Evidence |
|---|---|---|
| Forecast → students → portions, with the hall's safety margin | `apps/planning/services.py` | 336 plans, each with `attendance_target` and `portions_to_prepare` |
| Portions → dish split, by learned share | `apps/planning/services.py` — largest-remainder apportionment | 1,418 plan lines; the split always sums back to the total (a test asserts it) |
| Dish split → recipe → ingredient quantity | `apps/planning/services.py` | 336 indents, 3,806 indent lines |
| Procurement-format export | `apps/planning/services.py::indent_csv_rows` | CSV at `/api/preparation-plans/{id}/indent/` and `/dashboard/export/indent/{id}.csv` |
| Prepared / served / leftover, per dish | `apps/actuals/` | 504 actuals, 2,128 dish actuals |
| A tablet-first kitchen screen | `templates/kitchen/screen.html`, `static/css/kitchen.css` | 72 px minimum targets, 20 px minimum text, an 84 px sticky save button |
| Preparation guidance in plain language for the kitchen | `PreparationPlan.guidance_text` | printed on the kitchen screen and sent in the daily notification |

**The decision that shaped this milestone:** the plan carries **both** `attendance_target` and
`portions_target`, and the bridge between them is `portions_per_student` on
`ServiceLevelConfig`. A student at lunch eats about 2.6 portions. Without that bridge,
"329 students" cannot become "924 portions", and the whole chain breaks at the first step.

---

## M4 — Waste costing and reporting (2 weeks)

**Specification:** M8 (waste measurement and costing), M9 (accuracy and improvement reporting).

| Deliverable | Where | Evidence |
|---|---|---|
| Waste quantity and cost per dish, per service | `apps/waste/services.py` | 2,128 waste records — one per dish per service |
| Waste against the forecast | `WasteRecord.forecast_portions` and `over_prepared_portions` | each record says how far the kitchen was over |
| A cause for each waste record | `WasteRecord.cause` | `OVER_PREPARATION` and others |
| MAPE by meal, hall and week | `apps/reporting/services.py` | `GET /api/analytics/accuracy` |
| Waste by dish, meal, hall and period | `apps/waste/services.py` | `GET /api/analytics/waste` |
| Top-ten waste dishes | `waste_services.top_waste_dishes` | on the dashboard and in the API |
| Cost-saving trend against the baseline | `apps/reporting/services.py::baseline_comparison`, `saving_trend_by_week` | `GET /api/analytics/savings` |
| Attendance patterns by weekday, event and exam period | `apps/demand/services.py` | `GET /api/analytics/demand` |
| Ingredient consumption against indent | `reporting.ingredient_consumption_vs_indent` | `GET /api/analytics/ingredients` |
| The baseline measurement the saving is evidenced against | `manage.py run_baseline_measurement` | 4 weeks of baseline in the seed, and the command for the real thing |

**The decision that shaped this milestone:** there are **no rollup tables**. No
`DemandAggregate`, no `AccuracySnapshot`. A rollup is a second copy of the truth that can drift
out of step with the facts, and every report is computed from the facts on demand instead. At
this data volume — 504 services, 2,128 waste records — the queries are fast, and the reporting
can never be wrong in the way a stale rollup is wrong.

The measured result: **Rs 1,334.57** of waste per service in the baseline period, **Rs 761.38**
in the live period — a **42.95 %** reduction, **Rs 573.19** saved per service,
**Rs 515,872.63** annualised.

---

## M5 — UAT and production (1 week)

**Specification:** *"UAT and production"*, plus section 16's deployment requirements.

### Delivered

| Deliverable | Where | Evidence |
|---|---|---|
| Deployment guide | [08 Deployment](08-deployment.md) | — |
| The full documentation set | `docs/01`–`docs/10` | — |
| The forecast method in plain language for the mess manager | [05 Forecast method](05-forecast-method.md) | no code, no formulas |
| A realistic seed so the system can be demonstrated before it is trusted with real data | `manage.py seed_demo --reset` | 12 weeks, 32.5 s |
| A repeatable verification run | `scripts/verify_e2e.py`, `scripts/sweep_urls.py` | 23/23 checks; 615 requests, zero 5xx |
| Celery schedule for the daily jobs | `config/settings.py` | `generate-daily-forecasts` every 24 h, `dispatch-preparation-guidance` every 24 h, `flag-missing-actuals` hourly |
| Management commands for every scheduled job | `apps/core/management/commands/` | `run_forecasts`, `build_plans`, `run_baseline_measurement`, `import_erp` |
| Database indexes on the reporting paths | the migrations | the reporting queries are index-backed, not sequential scans |

### Outstanding — and why it cannot be closed here

| Item | What it needs | Who |
|---|---|---|
| **Kitchen screen usability test with actual staff** | a kitchen, a tablet, and the people who will use it. The specification asks for "a usability test with actual staff" — that is a field activity, not a test case. This is the one acceptance criterion in section 22 that is **not yet met**, and it is the one most likely to change the design | the team, on site |
| **Baseline measurement on the real mess** | 4 weeks of pre-deployment waste weighing. The seed's 4-week baseline is a simulation; the real one has to be measured by the kitchen | the kitchen, over 4 weeks |
| **ERP extract** | the student register in the expected CSV shape | the ERP owner |
| **Email credentials** | an SMTP endpoint, to turn the notification outbox into sent email | the IT department |
| **Hardware procurement decision** | RFID readers, tablet mounts, and a decision on whether the tablet has its own data plan or shares the mess Wi-Fi | the mess manager |

The build is ready for the campus to take over. What it is *not* ready for is a production
claim, because a production claim about a mess kitchen needs a mess kitchen.

---

## The critical path

If this were run again, these are the items that cost the most time or nearly went wrong:

| Item | Why it was on the critical path |
|---|---|
| Deciding the cost-per-portion rule (gross, including trim loss) before writing the waste module | Every cost figure depends on it. Changing it later would have meant rewriting the waste arithmetic, the plan costing and the seed |
| Getting the offline sync right in M1, not M5 | The UUID, the batch endpoint and the exact duplicate accounting had to exist before the PWA was built, not after |
| Making the forecaster a standalone module with no third-party imports | It is what makes the "learned model after a term of data" upgrade path real rather than aspirational |
| The route sweep | Three 500s survived until the very end because the happy path was the only path exercised. One sweep found all three |
| The seed | Without 12 weeks of realistic data, every claim about the saving would have been an estimate instead of a measurement |

---

## A note on effort

The specification estimates *"500–650 hours"* for a team of four over one semester, with the note
that *"add a second semester if a learned model is wanted after a term of data"*. The build in
this repository covers the first semester: the baseline model, the full loop, the offline
capture, the measurement and the reporting. The second semester — the learned model — is
deliberately absent, and the code is shaped so that adding it does not disturb anything else.
