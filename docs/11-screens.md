# Phase 2 — the screens

The screens delivered in Phase 2, what each one is for, and where it lives.
The rules the screens are built against are in
[10-ui-design-system.md](10-ui-design-system.md). This document is the map.

Every screen below is a live Django view wired to the real database. No
screen shows a figure that was not computed from a recorded service.

---

## 1. How the surfaces are organised

The platform has three working surfaces, and each has its own way in.

| Surface | Where | Who |
|---|---|---|
| The console | `/console/` | Mess manager, administrator, finance officer |
| The reporting surface | `/dashboard/` | Mess manager, finance officer |
| The tablet | `/kitchen/` and `/scan/` | Kitchen staff |

The console owns the things that are **edited** — menus, recipes, settings,
registration codes. The reporting surface owns the things that are **read** —
what was thrown away, what the forecast did, what is missing. The split is
by ownership of the data, not by how big the screen is.

Screens are placed in the app that owns the data they show, and mounted
under `/console/`:

| Screen | View | Route |
|---|---|---|
| Menu management | `apps.menu.views.menu_console` | `/console/menus/` |
| Menu cycle detail | `apps.menu.views.menu_cycle_detail` | `/console/menus/<id>/` |
| Recipe management | `apps.catalog.views.recipe_console` | `/console/recipes/` |
| Recipe detail | `apps.catalog.views.recipe_detail` | `/console/recipes/<id>/` |
| Attendance | `apps.attendance.console_views` | `/console/attendance/` |
| Forecast dashboard | `apps.forecasting.console_views` | `/console/forecast/` |
| Reports | `apps.reporting.console_views` | `/console/reports/` |
| Settings | `apps.reporting.console_views` | `/console/settings/` |
| Registration codes | `apps.accounts.views` | `/accounts/codes/` |
| Component library | `apps.reporting.design_system_views` | `/console/design-system/` |

The rule that keeps this honest is the one in
[02-architecture.md](02-architecture.md): **HTTP shapes never contain business
rules, and business rules never touch HTTP.** A view parses, validates,
authorises, delegates and formats. The arithmetic lives in
`apps/*/services.py`. That is why the console views can be read as layout
without reading the domain.

---

## 2. The console

### 2.1 Admin dashboard — `/dashboard/`

The screen a mess manager opens first. It answers one question: *how much
food did this mess throw away, how close did the forecast land, and are the
two getting closer?*

- A window filter (from, to, hall) that every figure respects.
- Four figures: waste cost, forecast error, average turnout, exam-period lift.
- Two charts: weekly waste cost as bars, forecast error by week as a line.
- Today's services reconciled, row by row, against the published band.
- The method well, so the number can be argued with.

### 2.2 Forecast dashboard — `/console/forecast/`

*What does the engine expect for the week ahead, how much room is around each
number, and why does it say what it says?*

- A horizon control (7, 14 or 28 days) and a hall control.
- Four figures: services ahead, expected turnout, widest range, coverage.
- **The band chart.** A forecast is not a number, it is a number with a
  range around it. The band draws the range as an area and the prediction
  as a line, so the reader sees how much room the kitchen has.
- The service ledger: predicted, range, width, portions to cook.
- The events in the window, because an exam week is not a weekday.
- The working of each forecast, one paragraph per service.

### 2.3 Attendance — `/console/attendance/`

*Who turned up, how was it captured, and are the tablets syncing?*

- Four figures: turned up, share of registered strength, scans captured,
  still unsynced.
- Service by service: date, hall, meal, turned up, registered, rate, forecast.
- How it was captured, by method.
- Tablet sync health: scans received, records created, duplicates ignored.
- The sync log as a CSV download.

The rate is always shown against registered strength, because that is what
the forecast is scored against.

### 2.4 Menu management — `/console/menus/`

*What is the kitchen cooking from, and what is scheduled for the week?*

- **The schedule board.** Seven days across, three meals down, one cell per
  hall-meal-date. It is the answer to "what is on tomorrow", so it is a board
  and not a list. A cell shows the cycle label and the dish count; the full
  menu name is on the cell's title. The snack row appears when the hall runs
  a snack service, and stays away when it does not.
- The active cycles, with their dish counts, scheduled rows and published
  rows.
- The detail of one cycle: the dishes for each meal with their expected
  shares, and the published schedule.
- **Three ways to plan**, each in its own panel below the board:
  - *Assign a cycle* — one hall, date and meal, for fixing a single slot.
  - *Create a daily menu* — one cycle for every meal of one hall on one
    date.
  - *Create a weekly menu* — a rotation of cycles across seven days. The
    rotation follows the order the cycles are listed in and then repeats, so
    three cycles give Monday the first, Tuesday the second and Wednesday the
    first again.

A cycle can be published or pulled back, and a meal can be replaced from the
cycle detail.

### 2.5 Recipe management — `/console/recipes/` and `/console/recipes/<id>/`

*The dish, its versions, and what one portion of it costs.*

The list shows every dish, its category, the version in force, the number of
recipe lines, the cost per portion and where it is served.

The detail shows:

- **The recipe in force**, one row per ingredient: quantity, trim loss,
  gross quantity, unit cost and cost. Gross quantity is what has to be
  bought, so it is the column that matters to procurement.
- **The cost of one portion**, with trim loss included.
- **Version history**, effective-dated, with the version in force marked.
- **At a glance**: the code, the category, the serving size, the number of
  versions.
- **A new version**, which starts today and closes the current one.

### 2.6 Dish management — `/console/dishes/`

*What the kitchen can cook, and the one place a dish is added, corrected or
taken off the list.*

- Four figures: dishes on the menus, retired, still in use, and the number of
  categories.
- The catalogue: every active dish with its code, category, portion size and
  how many records still mention it.
- **Add a dish** and **edit a dish**, on the same page. The edit form loads
  the dish into the same panel, so a correction is one page and needs no
  JavaScript.
- **Delete a dish.** A dish that has never been cooked is deleted. A dish
  that has been cooked is refused, and the refusal says what is holding it
  and offers to retire it instead.

Retiring takes a dish off the menus and keeps the history, which is what a
kitchen actually wants when it stops cooking something. The screen is closed
to everyone without `MANAGE_MASTERS`.

### 2.7 Reports — `/console/reports/`

*Everything the platform can produce, and what each report covers.*

- Four figures: services in window, actuals recorded, forecasts to score,
  schedule rows.
- The report catalogue: five reports, each with what it answers, how many
  rows it holds and its format.
- Two CSV exports that pull from the same services the screens read.
- The method, written out, so the export can be checked.

### 2.8 Settings — `/console/settings/`

*The halls, the service levels they cook to, the people who use the platform,
and who is allowed to do what.*

- Dining halls, with capacity, registered strength and state.
- Service levels: over-preparation allowance, ceiling, buffer, portions per
  student, and the date they took effect. The most specific row wins.
- The calendar: events and how much each one moves demand. An event is added, corrected or deleted from the same screen, through a form that takes its name, kind, dates, effect on demand and the meals it touches.
- People: the first sixty accounts, with role, hall and state.
- **Who can do what**: the capability matrix, one row per role.

Every rule the platform applies is set here, so the API, the templates and
the management commands cannot drift apart.

### 2.9 Registration codes — `/accounts/codes/`

*Who may create an account, and with what role?*

Accounts are created against a code issued by the mess office. The code
carries the role, so a student cannot register themselves as an
administrator, and the platform knows who vouched for an account.

- Four figures: issued, still open, redeemed, revoked.
- Every code, with its role, hall, name, expiry and state.
- The issue form, in the context column.

A code is single use and expires in fourteen days.

### 2.10 Login and register — `/accounts/login/` and `/accounts/register/`

Both are signed-out surfaces: no rail, one narrow column, the brand at the
top and a way back in.

The sign-in screen states plainly what each role sees. The register screen
explains how an account is made and posts over `fetch`, so a bad code comes
back as a message beside the form rather than as a page reload.

### 2.11 The component library — `/console/design-system/`

Every component in the product, in every state it has: the type specimens,
the colour contract, the figure row, the banners, the meters, the forms, the
states, the table, the board, the band, the actions and the pager.

It is the living reference. A screen is checked against it, and it is
checked by the same sweep as every other screen.

---

## 3. The reporting surface

### 3.1 Waste analytics — `/dashboard/waste/`

*What was thrown away, how much of it, and what it cost.*

- Four figures: cost, weight, cost per service, and the biggest cause.
- **Why it was thrown away.** Over-preparation is a forecasting problem,
  spoilage is a storage problem and quality rejection is a supplier
  problem. Each is fixed by a different person, so the cause decides who
  owns the fix.
- The weekly trend as bars.
- The top ten dishes by waste cost, each with its share.
- Where it happens, by meal and by hall.
- How the cost is worked out, written out in full.

### 3.2 Preparation planning — `/dashboard/planning/`

*What the kitchen should cook and what it should buy.*

For each plan: the expected turnout the plan was built from, the portions to
prepare, the over-preparation margin, the estimated food cost, the portion
split per dish, and the ingredient indent with packs and cost.

The screen defaults to **upcoming** plans, with a toggle for the plans that
have already been cooked. A hundred plans at once is a page nobody reads.

### 3.3 Accuracy — `/dashboard/accuracy/`

How close the forecast landed, by meal and by hall, and what the platform
saved against the baseline. The baseline is the deliverable, so it is shown
beside the live model rather than buried.

### 3.4 Data quality — `/dashboard/data-quality/`

Waste cannot be measured for a service whose actuals were never recorded,
and a forecast cannot be judged without an actual turnout. This screen lists
the services that are still missing their numbers, with the completion rate
and the missing count.

---

## 4. The tablet

### 4.1 Kitchen dashboard — `/kitchen/`

The tablet's home. Not a console on a small screen: a different interface.

- Today's services, each as a card with the hall, the meal, the turnout so
  far and the portions to cook.
- One large **Start** button per service, 72px tall.
- A status chip on every card: ready to cook, partly written up, or done.

Three decisions per screen. Nothing here needs a keyboard.

### 4.2 Kitchen actuals — `/kitchen/actuals/<id>/`

*What was prepared, what was served, what was left over.*

- Three stamps: expected turnout, cook this much, cost of this service.
- **The entry form comes first.** One row per dish, each with a large
  minus and plus stepper and the number in the middle. No typing.
- Served portions, scans and how the food was prepared.
- Leftover, computed as the difference and shown in the summary.
- The reason for the number, below the work rather than above it.
- The ingredient indent for the service, with a CSV download.
- A sticky action bar holding Back and Save, always in the same place.

### 4.3 Capture — `/scan/`

The attendance capture screen: the service, the student, the scan. It is the
one surface that is offline-first, so the queue and its sync state are always
on screen.

---

## 5. What changed under the console

Three changes to the existing application, each because a screen needed it.

**The rail is now the console's only navigation.** It is grouped as Console,
Administration and Operations, and the component library is listed at the
end of Administration. A screen that also carried a tab strip gave the
reader two places to look for the same thing.

**The kitchen route was split.** `kitchen_screen` became `kitchen_dashboard`
at `/kitchen/` and `kitchen_actuals` at `/kitchen/actuals/<id>/`. The old
name `kitchen-screen` is kept as an alias on the same path, so existing
links keep working.

**Registration codes were added.** `RegistrationCode` carries the role, is
single use, expires in fourteen days, and records who redeemed it. The
migration is `apps/accounts/migrations/0002_registrationcode.py`.

**The attendance models were brought back in line with their migration.** The
`captured_at` and `batch_started_at` defaults had drifted from
`datetime.now` to `timezone.now` without a migration to match. The column
types never changed, so `apps/attendance/migrations/0002_alter_attendanceaudit_batch_started_at_and_more.py`
only records the correction. `manage.py makemigrations --check` is clean
again.

---

## 6. Checking the work

The screens are checked by three things, all of them runnable.

```
manage.py check
manage.py seed_forward --days 21
node .hallmark/audit_layout.mjs
node .hallmark/capture_phase2.mjs
```

`audit_layout.mjs` opens every screen in a real browser at three widths and
reports the defects a screenshot hides: a table wider than its scroll box, an
element spilling past the viewport, text cut off inside its own box, and a
table column whose header and cells disagree about which way they face.

`capture_phase2.mjs` writes a screenshot of every screen to
`.hallmark/phase2/`, at the width a manager works at, the size of the
wall-mounted kitchen tablet, and the width of a phone.

The Hallmark sweep checks the CSS:

```
node scripts/sloplint.mjs static/css/components.css static/css/app.css static/css/kitchen.css --genre modern-minimal
```
