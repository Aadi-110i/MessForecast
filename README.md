# MessForecast — Meal Demand Forecasting and Food-Waste Reduction Platform

**Project P05 · EduRev Project List · Track P (Python + Django + PostgreSQL)**

A campus mess that cooks against a guess throws away food. This platform replaces the
guess with a forecast, turns the forecast into a preparation quantity and an ingredient
indent, and measures what was actually thrown away — in kilograms and in rupees.

```
forecast  ->  portions to prepare  ->  ingredient indent  ->  what the kitchen cooked
                                                              ->  what was served
                                                              ->  what was left over
                                                              ->  waste quantity and cost
                                                              ->  forecast error, fed back
```

---

## What it does

| Module | What it does |
|---|---|
| **M1** Menu, dish and recipe management | Halls, ingredients, dishes, versioned recipes, portion sizes, effective-dated cost rates |
| **M2** Meal attendance capture | QR / RFID / manual entry, offline-tolerant, idempotent sync |
| **M3** Calendar and event registry | Exams, festivals, holidays, vacations, and how much each one moves demand |
| **M4** Historical demand analysis | Attendance by meal, weekday, week, event type, exam period and dish |
| **M5** Forecasting engine | A statistical baseline with a confidence range and a plain-language explanation |
| **M6** Preparation and ingredient planning | Forecast → portions → dishes → recipe → indent → procurement CSV |
| **M7** Post-service actuals | Prepared, served and leftover, per dish, on a tablet-first kitchen screen |
| **M8** Waste measurement and costing | Leftovers in kg and rupees, against the forecast, per dish and service |
| **M9** Accuracy and improvement reporting | MAPE by meal, hall and week; the saving against the baseline; top-ten waste dishes |

## The design decision that shapes everything else

**The baseline statistical model is the deliverable for semester 1.** The specification is
explicit: *"a team that reaches for machine learning on a problem with no data yet has not
understood the problem."*

So the forecaster is a recency-weighted moving average with weekday, event and trend
adjustment — written out in plain language in
[`docs/05-forecast-method.md`](docs/05-forecast-method.md), because a mess manager who
cannot see why the number is what it is will not trust the number.

The engine lives in one dependency-free module ([`apps/forecasting/engine.py`](apps/forecasting/engine.py))
that takes observations and returns a forecast. When a term of real data justifies a learned
model, that module is replaced — not the application around it.

## The interface

The whole application is built on **Hallmark's Dusk theme**: a calm, expensive operations
console on a deep slate ground, with smoked-glass chrome, bone wells for the notes the
product hands to a person, and exactly two signal colours.

| | |
|---|---|
| **Periwinkle** | the model, and anything that matched: a forecast that landed, a service that was recorded |
| **Apricot** | loss and open work: waste, an overflow portion, a service still waiting to be recorded |
| **Bone** | a hand-off: the kitchen brief, the method behind the cost |
| **Figures** | a ruled tally of four, never a grid of stat tiles |
| **Data** | a ledger, never a card grid |

The type is Wix Madefor Display over Wix Madefor Text, **served from this origin** rather than
a font CDN, because the kitchen tablet may have no internet at all. The stylesheet is split
into [`static/css/tokens.css`](static/css/tokens.css) (the theme's palette, type and scale
plus the application's own roles), [`static/css/base.css`](static/css/base.css) (reset and
shared rules) and [`static/css/app.css`](static/css/app.css) (the shell and the dashboard),
with [`static/css/components.css`](static/css/components.css) for the reusable component
library, [`static/css/kitchen.css`](static/css/kitchen.css) for the two tablet screens and
[`static/css/landing.css`](static/css/landing.css) for the public landing page.

### Two experiences, one system

The platform has two audiences, and they do not want the same interface.

| | Console | Tablet |
|---|---|---|
| Who | Mess manager, administrator, finance officer | Kitchen staff, on a wall-mounted tablet |
| Density | Information-rich. Tables before cards. | Three decisions per screen. Large targets. |
| Control height | 32–40 px | 72 px minimum |
| Body text | 14 px and up | 20 px and up |
| Typing | Typing is fine | Typing is a failure state |
| Contrast | Passes AA for body text | Pushed past AA, large type |

They are **not two design systems**. They are one system at two scales: one token file, one
typeface pairing, one component vocabulary, one colour meaning. The same figure — turnout,
portions to cook, leftover, cost — reads in both. The full contract is in
[`docs/10-ui-design-system.md`](docs/10-ui-design-system.md), and every component in it is
rendered, live, at [`/console/design-system/`](apps/reporting/design_system_views.py).

The landing page at `/landing/` is the one surface that is not a work surface, so it carries its
own type scale in the same token file (a display step the dense console does not need). Its
figures are **not typed into the template**: the view reads the baseline and live windows out
of the records, calls the same reporting services the dashboard uses, and prints what it
finds, so re-seeding the demonstration data changes the page rather than falsifying it. GSAP
and ScrollTrigger are vendored into [`static/js/vendor/`](static/js/vendor) for the same reason
the fonts are: no CDN.

Two rules that the rest of the interface follows from:

- **Density is the design.** Controls are 32–40 px on the dashboard, and the kitchen screens
  never go below 72 px on the short edge, because they are worked with wet gloves.
- **One idea per screen.** The overview is a reconciliation: what was forecast, what turned
  up, what was cooked, what was left over, and whether the two agree.

Run the visual sweep and the capture tool with:

```bash
node scripts/hallmark_capture.mjs                 # sign in, walk every route, screenshot
node scripts/capture_landing_shots.mjs              # the landing page's frames, cut from the real app
node scripts/check_landing_motion.mjs                # the landing motion, with and without it
node scripts/measure_overflow.mjs /dashboard/waste/ 375   # what overflows a phone
node .hallmark/audit_layout.mjs                     # every screen, three widths, the defects a screenshot hides
node .hallmark/capture_phase2.mjs                   # a screenshot of every screen, at the three widths that matter
```

## Quick start

```bash
# 1. Dependencies
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# 2. Point at PostgreSQL (defaults are in config/settings.py)
$env:POSTGRES_DB='messforecast'
$env:POSTGRES_USER='messforecast'
$env:POSTGRES_PASSWORD='messforecast_dev_pw'
$env:POSTGRES_HOST='127.0.0.1'

# 3. Schema
.\.venv\Scripts\python manage.py migrate

# 4. A realistic 12-week history: 4 baseline weeks, then 8 forecast-guided weeks
.\.venv\Scripts\python manage.py seed_demo --reset

# 5. Carry the same rotation forward, and run the real engines over it,
#    so the forecast and planning screens have something to show
.\.venv\Scripts\python manage.py seed_forward --days 21

# 6. Run it
.\.venv\Scripts\python manage.py runserver
```

Then open <http://127.0.0.1:8000/> and sign in as `manager` / `messdemo`.

## Authentication

The API accepts JWT bearer tokens in addition to session and basic auth:

```bash
# Obtain an access + refresh token pair (username may be an email)
curl -X POST http://127.0.0.1:8000/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "manager", "password": "messdemo"}'

# Refresh
curl -X POST http://127.0.0.1:8000/api/auth/token/refresh/ \
  -H "Content-Type: application/json" \
  -d '{"refresh": "<refresh token>"}'

# Logout (blacklists the refresh token)
curl -X POST http://127.0.0.1:8000/api/auth/logout/ \
  -H "Authorization: Bearer <access token>" \
  -H "Content-Type: application/json" \
  -d '{"refresh": "<refresh token>"}'

# The authenticated user's profile
curl http://127.0.0.1:8000/api/auth/me/ -H "Authorization: Bearer <access token>"
```

Session authentication is unchanged for the rendered web application.

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `JWT_SIGNING_KEY` | Signs access and refresh tokens | `SECRET_KEY` |
| `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` | Access token lifetime | `15` |
| `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | Refresh token lifetime | `7` |
| `JWT_ROTATE_REFRESH_TOKENS` | Rotate refresh tokens on use | `true` |
| `JWT_BLACKLIST_AFTER_ROTATION` | Blacklist rotated refresh tokens | `true` |
| `DJANGO_EMAIL_BACKEND` | Outbound mail backend | console backend (prints reset links to the terminal) |
| `PASSWORD_RESET_TIMEOUT_SECONDS` | Password-reset link lifetime | `3600` |
| `PASSWORD_RESET_FROM_EMAIL` | From address for reset mail | `mess-forecast@campus.example` |
| `DEFAULT_FROM_EMAIL` | General from address | `mess-forecast@campus.example` |

For local development the console email backend is used, so password-reset links
are written to the terminal instead of being delivered. Set `DJANGO_EMAIL_BACKEND`
to an SMTP backend (with `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
`EMAIL_HOST_PASSWORD`) to send real mail.

## Dashboard routing by role

Every role lands on a different surface after sign-in:

| Role | Dashboard | What it shows |
|---|---|---|
| Student | `/dashboard/student/` | Today's menu, upcoming menus, own attendance, announcements, profile |
| Kitchen staff | `/kitchen/` | Today's preparation plan, record prepared/served (hall-scoped) |
| Finance officer | `/dashboard/finance/` | Waste cost, forecast accuracy, preparation plans — read only |
| Mess manager | `/dashboard/` | Full operational overview |
| Mess administrator | `/console/settings/` + `/dashboard/` | Master data: dishes, recipes, ingredients, halls |
| Administrator | `/dashboard/` | All administrative sections |

The navigation rail hides anything the role is not permitted to use, and write
controls (create recipe version, assign a cycle, edit a dish) render only for
roles holding `MANAGE_MASTERS` / `PLAN_MENU`. The backend enforces the same
capabilities on every API request.


| URL | What it is |
|---|---|
| `/landing/` | The public landing page: what the platform does, measured live from the database |
| `/` | The admin dashboard: waste, accuracy, today's services |
| `/console/menus/` | Menu management: the cycles and the schedule board |
| `/console/menus/` | Create a daily menu or a weekly rotation, one hall at a time |
| `/console/recipes/` | Recipe management: dishes, versions and cost per portion |
| `/console/dishes/` | The dish catalogue: add, correct, retire or delete a dish |
| `/console/attendance/` | Attendance: turnout, capture methods, tablet sync |
| `/console/forecast/` | The forecast dashboard: the week ahead, the band, and why |
| `/console/reports/` | Every report and export the platform produces |
| `/console/settings/` | Halls, service levels, people and the capability matrix |
| `/console/settings/` | The calendar: add an exam period, a holiday or a festival |
| `/accounts/codes/` | Registration codes: who may create an account, and with what role |
| `/accounts/register/` | Create an account against a code issued by the mess office |
| `/console/design-system/` | **The component library**, rendered: every component in every state |
| `/dashboard/waste/` | Waste quantity and cost by dish, meal, hall and period |
| `/dashboard/accuracy/` | MAPE by meal, hall and week |
| `/dashboard/planning/` | Preparation plans and ingredient indents |
| `/dashboard/data-quality/` | Services still missing their actuals |
| `/kitchen/` | The tablet kitchen dashboard (large targets, glove-friendly) |
| `/kitchen/actuals/<id>/` | Writing up one service: prepared, served, leftover |
| `/scan/` | Attendance capture, works offline |
| `/api/` | The REST API |

## Daily operation

```bash
# Every morning: forecast the next 7 days
manage.py run_forecasts --days 7

# Turn the forecasts into preparation plans and indents
manage.py build_plans --days 2 --publish

# Evidence the saving against the pre-deployment baseline
manage.py run_baseline_measurement --start 2026-08-24 --end 2026-09-20 \
    --live-start 2026-09-21 --live-end 2026-11-16

# Load the student register from the ERP export
manage.py import_erp students.csv
```

Both of the first two are also Celery tasks (`apps/forecasting/tasks.py`,
`apps/notifications/tasks.py`). With no broker configured they run eagerly, so a laptop
behaves exactly like a server.

## Tests

```bash
manage.py test
```

**159 tests**, against a real PostgreSQL database. All 159 pass here.

The three the specification calls out by name are covered directly:

| Specification requirement | Test |
|---|---|
| "offline attendance capture and sync, including a duplicate-submission case" | `tests/test_attendance_sync.py` |
| "forecast reproducibility" | `tests/test_forecasting.py` |
| "waste cost arithmetic verified against a manual calculation for a full week" | `tests/test_waste_costing.py` |
| "3,000 attendance records captured in a 45-minute window across halls without loss" | `tests/test_performance.py` |

Two scripts go further than the unit tests:

```bash
# every route, as every role — fails on any 5xx
python scripts/sweep_urls.py

# the whole flow over real HTTP against a running server
python manage.py runserver 8013 --noreload
python scripts/verify_e2e.py http://127.0.0.1:8013
```

## Measured results

Every figure below came from a run of this code against a live PostgreSQL 18.1 database, on the
seeded window 2026-08-14 → 2026-11-05 (four baseline weeks, eight live weeks). Re-seeding the
demo data on a different day shifts the waste and accuracy figures by a fraction of a percent.

| | |
|---|---:|
| Waste per service, baseline (4 weeks, cooking to registered strength) | **Rs 1,334.57** |
| Waste per service, live (8 weeks, cooking to the forecast) | **Rs 761.38** |
| Reduction | **42.95 %** |
| Saving per service | **Rs 573.19** |
| Annualised saving | **Rs 515,872.63** |
| MAPE over the 8-week live period | **2.36 %** (336 forecasts) |
| Actuals inside the published 80 % interval | **93.15 %** |
| 3,000 scans stored, across two halls | **5.5 s** — 541 scans/second, 5× the headroom a 45-minute window needs |
| The same 3,000 scans sent again | **0 rows created**, 0.088 s |
| A 7-day forecast for both halls | **0.65 s** |

Full method and caveats in [`docs/06-testing.md`](docs/06-testing.md).

> **The throughput row is hardware-dependent.** The 5.5 s figure was measured on the
> author's machine. On this Windows workstation with PostgreSQL 18 the same batch of 3,000
> scans through `scripts/bench_sync.py` takes 9.2 s (326 scans/second), and the replay still
> creates nothing — comfortably inside the 45 s ceiling `tests/test_performance.py` asserts.
> The write path is unchanged; it is the disk under it that differs. On a cold disk the same
> batch has been measured at around 70 s, so that one wall-clock assertion is the only one
> sensitive to the machine it runs on.

## Offline behaviour

The kitchen tablet cannot be assumed to have a connection. Scans and actuals are written to
IndexedDB **before** they are sent, each carrying a client-generated UUID. The server stores
that UUID under a unique constraint and ignores one it already holds, so sending the same
batch twice changes nothing. The service worker caches the app shell with versioned assets;
navigations are network-first, static assets cache-first, and API reads are never cached.

See [`docs/10-offline-and-sync.md`](docs/10-offline-and-sync.md).

## Documentation

| Document | Contents |
|---|---|
| [01 Requirements traceability](docs/01-requirements-traceability.md) | Every line of the specification mapped to what implements it |
| [02 Architecture](docs/02-architecture.md) | The modules, the layering, and why it is shaped this way |
| [03 Data model](docs/03-data-model.md) | Every table, its keys, and the relationships |
| [04 API reference](docs/04-api-reference.md) | Endpoints, payloads, and the role that may call each one |
| [05 Forecast method](docs/05-forecast-method.md) | **Written for the mess manager, not the programmer** |
| [06 Testing](docs/06-testing.md) | The test plan and what was actually measured |
| [07 Milestones](docs/07-milestones.md) | M0–M5 against the specification's schedule |
| [08 Deployment](docs/08-deployment.md) | How it is served, and what changes in production |
| [09 Decisions](docs/09-decisions.md) | The choices worth arguing about, including where this deviates from the brief |
| [10 Offline and sync](docs/10-offline-and-sync.md) | The offline design in full |
| [10 UI design system](docs/10-ui-design-system.md) | **The component library in written form**: two experiences, the colour contract, every component |
| [11 Screens](docs/11-screens.md) | Every screen in Phase 2: what it is for, and where it lives |
| [12 Phases 4 and 5 verification](docs/12-phase4-5-verification.md) | The database design and the authentication layer, checked model by model against the specification |
| [13 Phase 6 core modules](docs/13-phase6-core-modules.md) | **Menu management, recipes, attendance and the calendar**: what was broken, what was missing, and how it works now |

## Status

Implemented and verified against a live PostgreSQL 18 database: all nine modules, the REST
API, the offline PWA, the seed pipeline and the test suite. Measured results are in
[`docs/06-testing.md`](docs/06-testing.md) — every figure there came from an actual run of
this code, not from an estimate.

**One acceptance criterion is not yet met, and it needs the campus rather than a developer:**
the specification asks for the kitchen screens to be "verified in a usability test with actual
staff". The screens are built to the constraint — 72 px minimum touch targets, 20 px minimum
text, an 84 px sticky save button, high contrast, fully offline — but the session with real
kitchen staff has not happened. It is listed as outstanding in
[`docs/01-requirements-traceability.md`](docs/01-requirements-traceability.md) rather than
claimed as done.
