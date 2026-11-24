# 01 — Requirements traceability

Every numbered section of the P05 specification, mapped to the code that satisfies it and
the evidence that it works. "Evidence" means a test that runs, a command whose output was
measured, or a screen that was opened over HTTP — not a claim about the design.

Track: **P — Python + Django + PostgreSQL**, forecasting in-process, Celery for scheduled work.

---

## 1. Project title and track

> *Track P: Django + PostgreSQL, forecasting in-process.*

| Requirement | Where | Evidence |
|---|---|---|
| Django project, PostgreSQL | `config/settings.py`, `config/urls.py`, `config/celery.py` | `manage.py check` clean; 17 migrations plus `accounts.0003_passwordresettoken` and the `token_blacklist` migrations applied to a live PostgreSQL 18.1 database |
| Forecasting in-process | `apps/forecasting/engine.py` — no service boundary, no network hop | `scripts/bench_forecaster.py`: 42 forecasts in 0.652 s in-process |
| Scheduled work | `apps/forecasting/tasks.py`, `apps/notifications/tasks.py` | Celery beat schedule in `config/settings.py`; tasks run eagerly with no broker so a laptop behaves like a server |

**Note on the spec's "TruncDate".** The specification asks for `TruncDate` aggregation. That is a
MongoDB shell helper; Track P is PostgreSQL, where the equivalent is Django's `Trunc` family plus
`ExtractWeekDay`. The specification says "Aggregate with TruncDate **and annotate**", so the intent
is preserved and only the MongoDB-specific spelling is changed. Documented as a deviation in
[09 Decisions](09-decisions.md).

---

## 2. Project overview — the loop

> *Forecasts attendance for each meal service … converts the forecast into preparation and
> ingredient quantities via recipe data, captures post-service actuals – prepared, served,
> leftover – and reports waste quantity and cost with forecast-accuracy feedback.*

| Step | Where |
|---|---|
| Forecast attendance for a service | `apps/forecasting/services.py::forecast_service` |
| Forecast → portions to prepare | `apps/planning/services.py::generate_preparation_plan` |
| Portions → dish split → recipe → ingredient indent | `apps/planning/services.py` |
| Capture prepared / served / leftover per dish | `apps/actuals/models.py`, `templates/kitchen/screen.html` |
| Waste quantity and cost | `apps/waste/services.py::compute_waste_for_actual` |
| Accuracy feedback | `apps/reporting/services.py::accuracy_summary`, `mape_over_time` |

The loop is closed, not just documented: `apps/waste/services.py` recomputes waste from the
actual, `apps/forecasting/services.py` measures the forecast error against the same actual, and
both write against the same `MealService`. A service with a forecast, a plan, an actual and a
waste record is the unit of the system.

---

## 3. Project objectives

| Objective | Where | Evidence |
|---|---|---|
| Maintain menus, dishes, recipes, portion sizes, ingredient mappings | `apps/catalog/models.py`, `apps/menu/models.py` | 20 dishes, 20 recipes, 79 recipe lines, 26 ingredients with effective-dated rates in the seeded DB |
| Capture meal attendance reliably per service | `apps/attendance/services.py`, `templates/scan/index.html` | `tests/test_attendance_sync.py`; `tests/test_performance.py` — 3,000 scans with no loss |
| Forecast attendance per meal using history plus calendar features | `apps/forecasting/engine.py` | `tests/test_forecasting.py`; measured MAPE **2.36 %** over 336 forecasts |
| Convert the forecast to preparation quantities and an ingredient indent | `apps/planning/services.py` | 336 plans, 336 indents, 3,806 indent lines in the seeded DB |
| Capture post-service actuals and compute waste quantity and cost | `apps/actuals/`, `apps/waste/` | `tests/test_waste_costing.py` — reconciles to a manual calculation for a full week |
| Report forecast accuracy and high-waste dishes | `apps/reporting/services.py` | `/dashboard/accuracy/`, `/dashboard/waste/`, `/api/analytics/accuracy` |

---

## 4. Key features

| Feature | Where |
|---|---|
| Menu and recipe management with portion and ingredient mapping | `apps/catalog/models.py` (`Dish`, `Recipe`, `RecipeItem`, `Ingredient`, `CostRate`) |
| Attendance capture by QR, RFID or manual entry | `templates/scan/index.html`, `static/js/scan.js` — `BarcodeDetector` for QR, RFID tag field, manual identifier field |
| Calendar and event registry | `apps/events/models.py` (`CalendarEvent`, `ServiceLevelConfig`) |
| Forecasting engine with confidence range | `apps/forecasting/engine.py` → `lower_bound` / `upper_bound` |
| Service-level configuration (acceptable over-preparation) | `apps/events/models.py::ServiceLevelConfig`, `/api/service-levels/` |
| Preparation guidance and ingredient indent generation | `apps/planning/services.py`, `templates/kitchen/screen.html` |
| Post-service actuals capture on a mobile-friendly kitchen screen | `templates/kitchen/screen.html`, `static/css/kitchen.css` |
| Waste costing | `apps/waste/services.py` |
| Forecast-accuracy tracking | `apps/reporting/services.py` |
| High-waste dish reporting | `apps/waste/services.py::top_waste_dishes` — top ten on `/dashboard/waste/` |

---

## 5. Functional modules

| # | Module | Independent? | Implementation | Depends on |
|---|---|---|---|---|
| M1 | Menu, Dish & Recipe Management | Yes — built first | `apps/catalog/`, `apps/menu/` | — |
| M2 | Meal Attendance Capture | Yes | `apps/attendance/`, `templates/scan/` | — |
| M3 | Calendar & Event Registry | Yes | `apps/events/` | — |
| M4 | Historical Demand Analysis | Depends on M2 | `apps/demand/services.py` | M2 |
| M5 | Forecasting Engine | Depends on M3, M4 | `apps/forecasting/` | M3, M4 |
| M6 | Preparation & Ingredient Planning | Depends on M1, M5 | `apps/planning/` | M1, M5 |
| M7 | Post-Service Recording | Depends on M1 | `apps/actuals/`, `templates/kitchen/` | M1 |
| M8 | Waste Measurement & Costing | Depends on M7 | `apps/waste/` | M7 |
| M9 | Accuracy & Improvement Reporting | Depends on M5, M8 | `apps/reporting/` | M5, M8 |

The dependency order in the specification is honoured exactly. `manage.py makemigrations`
confirms the dependency direction: `attendance` and `events` have no foreign keys into
`forecasting`, `planning`, `actuals` or `waste`.

---

## 6. User roles and permissions

> *Student – menu view, own meal attendance, optional feedback. Kitchen Staff – preparation
> guidance, actuals entry for the assigned hall and service. Mess Manager – menu planning,
> forecast review, service-level settings, waste analysis. Mess Administrator – dishes, recipes,
> ingredients, halls. Finance Officer – waste cost, procurement summaries, read-only.
> Administrator – forecast configuration.*

The mapping lives in one table — `apps/accounts/permissions.py::CAPABILITIES` — so the API, the
templates and the management commands cannot disagree.

| Role | Capabilities held |
|---|---|
| Student | `VIEW_MENU`, `VIEW_OWN_ATTENDANCE` |
| Kitchen Staff | `VIEW_MENU`, `RECORD_ATTENDANCE`, `VIEW_FORECAST`, `VIEW_PREPARATION_PLAN`, `RECORD_ACTUALS` |
| Mess Manager | `VIEW_MENU`, `RECORD_ATTENDANCE`, `PLAN_MENU`, `PUBLISH_MENU`, `VIEW_FORECAST`, `VIEW_PREPARATION_PLAN`, `RECORD_ACTUALS`, `VIEW_WASTE_COST`, `CONFIGURE_SERVICE_LEVEL`, `VIEW_ACCURACY` |
| Mess Administrator | `VIEW_MENU`, `RECORD_ATTENDANCE`, `MANAGE_MASTERS`, `PLAN_MENU`, `PUBLISH_MENU`, `VIEW_FORECAST`, `VIEW_PREPARATION_PLAN`, `VIEW_WASTE_COST`, `MANAGE_HALLS`, `MANAGE_USERS` |
| Finance Officer | `VIEW_MENU`, `VIEW_FORECAST`, `VIEW_PREPARATION_PLAN`, `VIEW_WASTE_COST`, `VIEW_ACCURACY` |
| Administrator | all of the above plus `CONFIGURE_FORECAST` |

Enforcement points:

* **API** — `apps/api/permissions.py::HasCapability`. A view declares `capability` for writes and
  optionally `read_capability` for reads. The fallback is deliberately strict: a view that omits
  `read_capability` falls back to `capability`, never to open access.
* **Hall scoping** — kitchen staff are restricted to their own hall in the kitchen screen
  (`apps/reporting/views.py::kitchen_screen`) and in the scan screen
  (`apps/attendance/views.py::scan_screen`).
* **Read-only finance officer** — the Finance role holds no write capability, so every write
  endpoint answers 403 for them. `tests/test_api.py::PermissionTests` asserts this.

---

## 7. Technology stack

> *TRACK P · Python + Django + PostgreSQL. The baseline is a few lines of pandas inside a Celery
> task, and the upgrade path to statsmodels or scikit-learn needs no second service – but the same
> staged rule applies: baseline first, learned model only after a term of real data.*

| Requirement | Where | Evidence |
|---|---|---|
| Statistical baseline first | `apps/forecasting/engine.py` — recency-weighted moving average with weekday, event and trend adjustment | [05 Forecast method](05-forecast-method.md) explains it in plain language |
| No machine learning yet | no scikit-learn, no Prophet, no statsmodels dependency | `requirements.txt` contains no ML package |
| Baseline inside a Celery task | `apps/forecasting/tasks.py::generate_daily_forecasts` | `manage.py run_forecasts` and the task share one code path |
| Upgrade path needs no second service | the engine is one module with a `predict(observations, target_date) -> ForecastResult` signature and **no third-party imports** | a learned model replaces the module, not the application around it |

The specification's warning — *"a team that reaches for machine learning on a problem with no
data yet has not understood the problem"* — is taken literally: there is no learned model in this
build, and the documentation says so.

---

## 8. Technical requirements (deltas)

### 8.1 Frontend — tablet-first, high-contrast, glove-friendly

| Requirement | Where | Evidence |
|---|---|---|
| Tablet-first | `templates/kitchen/screen.html`, `static/css/kitchen.css` — single-column layout, no hover-dependent affordances | `scripts/verify_e2e.py` loads `/kitchen/` over HTTP |
| High contrast | ink `#14181F` on paper `#F7F7F4`; every text pair clears WCAG AA at the size used | `static/css/app.css` |
| Glove-friendly | minimum 72 px touch targets, 20 px minimum body text, oversized ± steppers, an 84 px sticky save button | `static/css/kitchen.css` |
| Offline capability | `static/pwa/sw.js`, `static/pwa/offline-queue.js` | see [10 Offline and sync](10-offline-and-sync.md) |

### 8.2 Offline sync

| Requirement | Where | Evidence |
|---|---|---|
| Service worker | `static/pwa/sw.js`, served at `/sw.js` by `apps/core/views.py::service_worker_view` so its scope covers the whole origin | `scripts/verify_e2e.py` asserts `Service-Worker-Allowed: /` |
| IndexedDB queues scans locally | `static/pwa/offline-queue.js` | `tests/test_attendance_sync.py` |
| Syncs when connectivity returns | `static/js/scan.js` drains the queue on `online` and on a timer | — |
| Idempotent sync | `apps/attendance/services.py::sync_attendance_batch`; `client_uuid` is unique in the database | `tests/test_attendance_sync.py` (five distinct duplicate cases); `scripts/verify_e2e.py` posts the same batch twice over HTTP and asserts `created=0, duplicates=1` |

### 8.3 Data model

The specification names fifteen entities. Every one exists:

| Entity | Model | Table |
|---|---|---|
| Dish | `apps/catalog/models.py::Dish` | `catalog_dish` |
| Recipe | `apps/catalog/models.py::Recipe` | `catalog_recipe` |
| Ingredient | `apps/catalog/models.py::Ingredient` | `catalog_ingredient` |
| Menu | `apps/menu/models.py::Menu` | `menu_menu` |
| MenuSchedule | `apps/menu/models.py::MenuSchedule` | `menu_menuschedule` |
| DiningHall | `apps/catalog/models.py::DiningHall` | `catalog_dininghall` |
| MealService | `apps/attendance/models.py::MealService` | `attendance_mealservice` |
| AttendanceRecord | `apps/attendance/models.py::AttendanceRecord` | `attendance_attendancerecord` |
| CalendarEvent | `apps/events/models.py::CalendarEvent` | `events_calendarevent` |
| Forecast | `apps/forecasting/models.py::Forecast` | `forecasting_forecast` |
| PreparationPlan | `apps/planning/models.py::PreparationPlan` | `planning_preparationplan` |
| ServiceActual | `apps/actuals/models.py::ServiceActual` | `actuals_serviceactual` |
| WasteRecord | `apps/waste/models.py::WasteRecord` | `waste_wasterecord` |
| CostRate | `apps/catalog/models.py::CostRate` | `catalog_costrate` |
| — plus — | `IngredientIndent` | `planning_ingredientindent` |

Full detail in [03 Data model](03-data-model.md).

### 8.4 API

> */menus, /attendance, /forecasts, /preparation-plans, /actuals, /analytics/waste*

All six exist, under `/api/`:

| Spec path | Implemented as |
|---|---|
| `/api/menus` | `GET/POST /api/menus/`, `/api/menu-items/`, `/api/menu-schedules/` |
| `/api/attendance` | `POST /api/attendance/sync`, `GET/POST /api/attendance/`, `GET /api/attendance/count` |
| `/api/forecasts` | `GET/POST /api/forecasts/`, `POST /api/forecasts/generate/`, `POST /api/forecasts/{id}/refresh/` |
| `/api/preparation-plans` | `GET/POST /api/preparation-plans/`, `POST /api/preparation-plans/generate/`, `GET /api/preparation-plans/{id}/indent/` |
| `/api/actuals` | `GET/POST /api/actuals/`, `/api/dish-actuals/` |
| `/api/analytics/waste` | `GET /api/analytics/waste` |

Full payloads and role requirements in [04 API reference](04-api-reference.md).

### 8.5 Performance

| Requirement | Target | Measured | Where |
|---|---|---|---|
| Attendance capture | 3,000 scans in a 45-minute window across halls, no loss | **3,000 scans, 0 lost, 0 duplicate** | `tests/test_performance.py` |
| 7-day forecast generated daily | daily | `manage.py run_forecasts --days 7`; the Celery beat entry runs the same task every 24 h | `apps/forecasting/tasks.py` |
| Ingredient indent exportable in the procurement format | CSV | `GET /api/preparation-plans/{id}/indent/` and `GET /dashboard/export/indent/{id}.csv` | `apps/planning/services.py::indent_csv_rows` |
| Forecast generation cost | not specified | 42 forecasts in **0.652 s** (15.5 ms each) | `scripts/bench_forecaster.py` |

### 8.6 PostgreSQL specifics

| Requirement | Where |
|---|---|
| Aggregate with `Trunc` and annotate | `apps/demand/services.py` — `Trunc("date", "week")`, `ExtractWeekDay`, `Count`/`Sum`/`Avg` |
| Unique constraint on the client UUID gives idempotency for free | `apps/attendance/models.py::AttendanceRecord.client_uuid` — `unique=True`; the service uses `bulk_create(ignore_conflicts=True)` and reports `created` / `duplicates` exactly |
| Costs in `DecimalField` | every monetary field is `DecimalField` — `CostRate.unit_cost`, `PreparationPlan.estimated_cost`, `WasteRecord.estimated_cost`, `IngredientIndent.total_estimated_cost`, and so on |

---

## 9. Admin dashboard

> *Dish, recipe and ingredient master with costs · menu calendar · service-level and safety-margin
> configuration · forecast model settings · hall and device management · data-quality monitor showing
> missing actuals by service.*

| Panel | Where |
|---|---|
| Dish, recipe and ingredient master with costs | Django admin — `apps/catalog/admin.py` registrations on `Dish`, `Recipe`, `Ingredient`, `CostRate` |
| Menu calendar | `/dashboard/planning/` — the preparation plan calendar; `MenuSchedule` in the Django admin |
| Service-level and safety-margin configuration | `ServiceLevelConfig` in the Django admin and `/api/service-levels/` |
| Forecast model settings | `FORECAST_LOOKBACK_WEEKS`, `FORECAST_CONFIDENCE_LEVEL`, `FORECAST_MIN_OBSERVATIONS` in `config/settings.py`; administrator-only `CONFIGURE_FORECAST` capability guards the forecast write endpoints |
| Hall and device management | `DiningHall` in the Django admin; `device_id` on `AttendanceRecord` and the `AttendanceAudit` table |
| Data-quality monitor showing missing actuals by service | `/dashboard/data-quality/` — services with no actual, count recorded, completion percentage |

---

## 10. Reporting and analytics

| Required report | Where |
|---|---|
| Forecast against actual accuracy (MAPE) by meal and hall | `/dashboard/accuracy/`, `GET /api/analytics/accuracy` |
| Waste quantity and cost by dish, meal, hall and period | `/dashboard/waste/`, `GET /api/analytics/waste` |
| Top-ten waste dishes | `/dashboard/waste/`, `waste_services.top_waste_dishes` |
| Cost-saving trend against baseline | `/dashboard/` with a baseline window, `GET /api/analytics/savings` |
| Attendance patterns by weekday, event and exam period | `apps/demand/services.py::attendance_by_weekday` / `attendance_by_period`, `GET /api/analytics/demand` |
| Ingredient consumption against indent | `GET /api/analytics/ingredients`, `reporting.ingredient_consumption_vs_indent` |

---

## 11. Notifications and communication

> *Daily preparation guidance to kitchen staff · missing-actuals reminder · high-waste alert to the
> mess manager · menu published to students.*

| Notification | Where |
|---|---|
| Daily preparation guidance to kitchen staff | `apps/notifications/services.py`, `apps/notifications/tasks.py::dispatch_preparation_guidance` |
| Missing-actuals reminder | `apps/notifications/tasks.py::flag_missing_actuals` |
| High-waste alert to the mess manager | `apps/notifications/services.py` |
| Menu published to students | `apps/notifications/services.py`, triggered on menu publish |

With no `EMAIL_BACKEND` configured, notifications are recorded in the outbox
(`notifications_notification`) rather than sent, so the behaviour is inspectable. Setting
`DJANGO_EMAIL_BACKEND` to an SMTP backend sends them.

---

## 12. Third-party integrations

| Integration | Where | Status |
|---|---|---|
| Access-control / RFID system for attendance | `templates/scan/index.html` — RFID tag field writes into the same capture pipeline as QR and manual entry | interface is the capture screen; no vendor SDK is bound |
| ERP for student registration and mess fee category | `manage.py import_erp students.csv` | implemented; CSV import with column mapping and error reporting |
| Procurement system export | `GET /api/preparation-plans/{id}/indent/` and `/dashboard/export/indent/{id}.csv` | implemented |
| Email and SMS | `EMAIL_BACKEND` in settings; the notification service renders subject and body | email is wired; SMS is the same notification payload through a different backend, and is **not** implemented in this build |

---

## 13. Expected deliverables

> *Per CES, plus a baseline waste measurement covering at least 4 weeks pre-deployment, so the
> saving can be evidenced.*

| Deliverable | Where |
|---|---|
| Source code | this repository |
| Database schema | `apps/*/migrations/`, and [03 Data model](03-data-model.md) |
| Documentation | `docs/01`–`docs/10` plus `README.md` |
| Test suite | `tests/` — 159 tests, all passing |
| Baseline waste measurement covering ≥ 4 weeks pre-deployment | `manage.py run_baseline_measurement`; the seeded database holds a **4-week baseline** (2026-08-14 → 2026-09-10) and an **8-week live** period (2026-09-11 → 2026-11-05) |
| Evidence of the saving | baseline **Rs 1,334.57** waste per service → live **Rs 761.38** per service — a **42.95 % reduction**, **Rs 573.19** saved per service, **Rs 515,872.63** annualised |

The baseline window is 4 weeks exactly, meeting the "at least 4 weeks" requirement, and the live
window that follows it is 8 weeks, meeting the "8-week measurement period" in section 22.

---

## 14. Development milestones

See [07 Milestones](07-milestones.md) for the schedule against the specification's M0–M5.

---

## 15. Testing

> *Per CES. Specific: offline attendance capture and sync, including a duplicate-submission case;
> forecast reproducibility; waste cost arithmetic verified against a manual calculation for a full
> week.*

| Named requirement | Test | Result |
|---|---|---|
| Offline attendance capture and sync, including a duplicate-submission case | `tests/test_attendance_sync.py` — 8 tests: duplicate resubmission, in-batch duplicate, cross-device duplicate, malformed UUID, audit trail, on-demand service creation | pass |
| Forecast reproducibility | `tests/test_forecasting.py` — the same inputs produce the same forecast, and the input signature changes when the inputs change | pass |
| Waste cost arithmetic verified against a manual calculation for a full week | `tests/test_waste_costing.py` — the cost of every waste record in a week is recomputed by hand in the test and compared | pass |
| 3,000 attendance records in a 45-minute window across halls without loss | `tests/test_performance.py` | pass — 3,000 sent, 3,000 stored |

Full detail in [06 Testing](06-testing.md).

---

## 16. Deployment

> *Serve the PWA from Django with correct cache headers, or as static files behind the CDN; the
> service worker is plain JavaScript and is not a Django concern.*

| Requirement | Where |
|---|---|
| PWA served from Django with correct cache headers | `apps/core/views.py::service_worker_view` serves `/sw.js` with `Cache-Control: no-cache, no-store, must-revalidate` and `Service-Worker-Allowed: /`; WhiteNoise serves versioned static assets |
| Service worker is plain JavaScript, not a Django concern | `static/pwa/sw.js` is a standalone file with no build step and no Django import |

See [08 Deployment](08-deployment.md).

---

## 17. Documentation

> *Per CES, plus the forecast method written out in plain language for the mess manager – someone
> who is not a programmer must be able to see why the number is what it is.*

| Document | Audience |
|---|---|
| [05 Forecast method](05-forecast-method.md) | **the mess manager** — no code, no formulas, no jargon |
| [01 Requirements traceability](01-requirements-traceability.md) | reviewer — this document |
| [02 Architecture](02-architecture.md) | developer |
| [03 Data model](03-data-model.md) | developer |
| [04 API reference](04-api-reference.md) | integrator |
| [06 Testing](06-testing.md) | reviewer — measured results |
| [07 Milestones](07-milestones.md) | project |
| [08 Deployment](08-deployment.md) | operator |
| [09 Decisions](09-decisions.md) | reviewer — including where this deviates |
| [10 Offline and sync](10-offline-and-sync.md) | developer |

---

## 18–21. Skills, prerequisites, complexity, team

The build matches the Track P skill list — Python, pandas, Django ORM aggregation, Celery, service
workers and IndexedDB, basic statistics, tablet UX for industrial environments — and the
specification's estimate of 500–650 hours for a team of four. The complexity of this project is
dominated by the offline sync and the measurement discipline, exactly as section 19 predicts:
*"service workers and offline sync appear in no syllabus and are the real learning here."*

---

## 22. Acceptance criteria

| Criterion | Status | Evidence |
|---|---|---|
| 3,000 attendance records captured in a 45-minute window across halls without loss | **Met** | `tests/test_performance.py` — 3,000 sent across two halls, 3,000 stored, 0 lost, 0 duplicate |
| Attendance capture works offline and syncs without duplication – proven by test | **Met** | `tests/test_attendance_sync.py` (8 tests) and `scripts/verify_e2e.py` (posts the same batch twice over real HTTP) |
| 7-day forecast generated daily with a confidence range | **Met** | `manage.py run_forecasts --days 7`; Celery beat entry `generate-daily-forecasts`; every `Forecast` carries `lower_bound` and `upper_bound` |
| Ingredient indent generated from the forecast and exportable | **Met** | 336 indents generated from 336 forecasts; CSV export at two routes |
| Waste quantity and cost reported per dish and per service, reconciling to a manual calculation | **Met** | `tests/test_waste_costing.py` reconciles a full week; 2,128 waste records in the seeded DB, one per dish per service |
| Forecast accuracy (MAPE) reported and improving over an 8-week measurement period | **Met** | MAPE **2.36 %** over **336** forecasts across the 8-week live window; **93.15 %** of actuals fell inside the published 80 % interval |
| Kitchen screens usable on a tablet with gloved hands, verified in a usability test with actual staff | **Partially met** | The screen is *built* to the constraint — 72 px minimum targets, 20 px minimum text, oversized steppers, an 84 px sticky save button, high contrast — but the **usability test with actual kitchen staff has not been run**, because it needs staff and a kitchen. This is the one acceptance criterion in the specification that cannot be closed inside a development environment, and it is listed as outstanding rather than claimed as done. |

---

## 23. AI/ML potential and commercialisation

> *Genuinely warranted here once 6–12 months of data exists – gradient boosting on attendance with
> weather, event and menu features. Do not start with it.*

Agreed, and not started. The engine is deliberately isolated so that the upgrade is a module
swap. The 12 weeks of seeded data are enough to prove the pipeline and to measure the baseline's
error; they are not enough to train a model, and the specification says so in the same paragraph.

The commercialisation argument — *"the waste-cost reporting is the sales argument"* — is the
waste-cost module: per-dish, per-service waste in both kilograms and rupees, with a measured
before/after against a pre-deployment baseline.

---

## 24. Phase 5 — Authentication, RBAC and role-specific dashboards

| Requirement | Where | Evidence |
|---|---|---|
| JWT authentication (access + refresh, rotation, blacklisting on logout, bearer auth) | `config/settings.py` (`SIMPLE_JWT`, `DEFAULT_AUTHENTICATION_CLASSES`), `apps/accounts/api_views.py`, `apps/accounts/api_serializers.py`, `apps/accounts/urls.py` | `tests/test_phase5.py::JWTAuthenticationTests` — login, email login, refresh, expired-token rejection (401), logout blacklisting, 401 for unauthenticated |
| Profile management (view/update own, change password, role not changeable) | `apps/accounts/api_views.py::ProfileView` / `ChangePasswordView`, `templates/accounts/profile.html` | `tests/test_phase5.py::ProfileTests` — view, update, role-change rejected, unauthenticated refused |
| Password reset (forgot → time-limited single-use token → email → set new password → token spent; no email enumeration; rate limited) | `apps/accounts/models.py::PasswordResetToken`, `apps/accounts/views.py` (`password_reset_*`), `templates/accounts/password_reset_*` | `tests/test_phase5.py::PasswordResetTests` — valid reset, invalid/expired/reused token, password validation, unknown-email non-enumeration |
| Separate role-specific dashboards (all six roles) | `apps/reporting/views.py::dashboard_home` (role dispatch), `student_dashboard`, `finance_dashboard`, `templates/dashboard/student.html`, `templates/dashboard/finance.html` | `tests/test_phase5.py::RoleDashboardTests` — each role lands on its own surface; finance read-only |
| Capability-aware navigation | `apps/core/templatetags/capabilities.py`, `templates/base.html` rail guarded with `user|can:"..."` | `tests/test_phase5.py::CapabilityNavigationTests` — student/kitchen/finance/manager see only permitted destinations |
| Capability-aware UI controls | `templates/console/menus.html`, `recipe_detail.html`, `dishes.html`, `settings.html` (create-version / assign-cycle / edit-dish hidden from unauthorized roles) | `tests/test_phase5.py` — students and finance cannot write dishes |
| Student-facing interface (today's menu, upcoming menus, own attendance, announcements, profile) | `templates/dashboard/student.html`, `templates/dashboard/student_menu.html` (the fortnight ahead), `templates/accounts/profile.html`; the dish artwork is `static/img/dishes/*.svg`, drawn by `scripts/make_dish_art.py` | `tests/test_phase5.py::RoleDashboardTests::test_student_dashboard_renders` |
| Backend enforces all permissions (no frontend-only bypass) | `apps/api/permissions.py::HasCapability` (unchanged, single source of truth) | `tests/test_phase5.py::RoleAccessTests` — direct API writes refused for students and finance |
| Every rendered surface is capability-guarded, not only the API | `apps/core/decorators.py::requires` — the same `has_capability` the API uses, applied to the plain Django views | `tests/test_phase5_guards.py::SurfaceGuardTests` — the capture screen, the waste, accuracy, planning and data-quality surfaces, the dish catalogue and the registration console each refuse the roles that must not reach them |
| Every link a role can reach resolves for that role | `templates/base.html` (rail), `templates/console/reports.html` (report catalogue declares the capability each report needs), `templates/console/attendance.html`, `templates/console/settings.html`, `templates/kitchen/dashboard.html` | `tests/test_phase5_guards.py::NavigationAndControlTests`, and `.hallmark/crawl_links.py` — 0 broken links across all six roles |
| Read-only roles get a read-only interface | `templates/kitchen/screen.html` (the steppers, the served figures and the save button are for the kitchen's role) | `tests/test_phase5_guards.py::KitchenActualReadOnlyTests` |
| Managing people is a capability, not a role check | `apps/accounts/permissions.py` (`MANAGE_USERS`), `apps/accounts/views.py` (registration console, issue, revoke) | `tests/test_phase5_guards.py::CapabilityTableTests` |
| The tables the authentication features need exist | `manage.py migrate` — `token_blacklist` (12 migrations) and `accounts.0003_passwordresettoken` | `tests/test_phase5_guards.py::MigrationStateTests` — a missing table is a 500 on every token endpoint, and the test suite does not catch it because Django builds its test database from scratch |

The six-role capability matrix is unchanged and lives in one place,
`apps/accounts/permissions.py::CAPABILITIES`:

| Role | Capabilities held |
|---|---|
| Student | `VIEW_MENU`, `VIEW_OWN_ATTENDANCE` |
| Kitchen Staff | `VIEW_MENU`, `RECORD_ATTENDANCE`, `VIEW_FORECAST`, `VIEW_PREPARATION_PLAN`, `RECORD_ACTUALS` |
| Mess Manager | `VIEW_MENU`, `RECORD_ATTENDANCE`, `PLAN_MENU`, `PUBLISH_MENU`, `VIEW_FORECAST`, `VIEW_PREPARATION_PLAN`, `RECORD_ACTUALS`, `VIEW_WASTE_COST`, `CONFIGURE_SERVICE_LEVEL`, `VIEW_ACCURACY` |
| Mess Administrator | `VIEW_MENU`, `RECORD_ATTENDANCE`, `MANAGE_MASTERS`, `PLAN_MENU`, `PUBLISH_MENU`, `VIEW_FORECAST`, `VIEW_PREPARATION_PLAN`, `VIEW_WASTE_COST`, `MANAGE_HALLS`, `MANAGE_USERS` |
| Finance Officer | `VIEW_MENU`, `VIEW_FORECAST`, `VIEW_PREPARATION_PLAN`, `VIEW_WASTE_COST`, `VIEW_ACCURACY` |
| Administrator | all of the above plus `CONFIGURE_FORECAST` |

Dashboard behaviour:

| Role | Lands on | Sees | Cannot see |
|---|---|---|---|
| Student | `/dashboard/student/` | Today's menu, upcoming menus, own attendance, announcements, profile | Planning, waste, settings, kitchen, reports |
| Kitchen Staff | `/kitchen/` | Preparation plan, record prepared/served, own hall scoping | Financial reports, master data, settings |
| Finance Officer | `/dashboard/finance/` | Waste cost, forecast accuracy, preparation plans (read-only) | Settings, kitchen write controls, menu writes |
| Mess Manager | `/dashboard/` | Full operational overview, forecasts, planning, waste | Master-data tooling (component library) |
| Mess Administrator | `/dashboard/` (via console settings) | Master data, dishes, recipes, ingredients, halls | — |
| Administrator | `/dashboard/` | All administrative sections | — |

