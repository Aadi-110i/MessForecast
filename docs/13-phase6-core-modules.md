# Phase 6 — the core modules

The four modules the specification names: menu management, recipes and
ingredients, attendance, and the calendar. Most of them existed before this
phase. What this phase did was audit them against the specification, fix
the two operations that were broken, and build the three that were missing.

Read with [03-data-model.md](03-data-model.md) (the tables behind them) and
[04-api-reference.md](04-api-reference.md) (the endpoints).

---

## 6.1 Menu management

### What was already there

The whole model was in place. A `Menu` is a cycle: a set of dishes for each
meal. A `MenuSchedule` binds a cycle to a hall, a date and a meal, and the
board on the menu screen is that table read seven days across and four meals
down. The API exposes the endpoints the specification names, and they all
work:

```
GET    /api/menus/
POST   /api/menus/
GET    /api/menus/{id}/
PUT    /api/menus/{id}/
DELETE /api/menus/{id}/
```

### The two operations that were broken

**Replacing a meal that was already scheduled returned a 500.**

The slot is unique on `(hall, date, meal)`. The view looked the row up by
all four fields — including the cycle — so when a slot held a different
cycle it found nothing and tried to insert, which the database refused with
a `UniqueViolation`. The traceback read:

```
psycopg.errors.UniqueViolation: duplicate key value violates unique
constraint "uniq_schedule_slot"
DETAIL:  Key (hall_id, date, meal)=(31, 2026-08-15, BREAKFAST) already exists.
```

This was the *Replace a meal* action on the cycle detail screen, and the
*Assign* link on the board. Both are core Phase 6 operations and both
crashed. The fix is in `apps/menu/services.py`:

```python
def assign_slot(hall, on_date, meal, menu, published=False):
    row, created = MenuSchedule.objects.get_or_create(
        hall=hall, date=on_date, meal=meal,
        defaults={"menu": menu, "is_published": published},
    )
    if not created and row.menu_id != menu.pk:
        row.menu = menu
        row.save(update_fields=["menu", "updated_at"])
    return row
```

The row is found by the three fields that are unique, and the cycle on it is
changed. A row that already existed keeps its published state, because a
schedule the kitchen has already been told about should not quietly become
unpublished because somebody edited it.

**Deleting a dish that had been cooked returned a 500.**

The schema protects the rows that carry history: `MenuItem.dish`,
`PreparationLine.dish`, `DishActual.dish` and `WasteRecord.dish` are all
`on_delete=PROTECT`. Django raises `ProtectedError`, which was reaching the
client as an unhandled 500 — which reads as "the server is broken" when in
fact the server is telling the truth.

The fix is a single exception handler for the whole API,
`apps/api/exceptions.py`, wired through `EXCEPTION_HANDLER` in the REST
framework settings. A protected delete now comes back as a **409** that says
what is holding the row:

> That cannot be deleted. It is still used by 1 menu item, 24 preparation
> plans, 12 service actuals, 128 waste records. Retire it instead, which
> keeps the history and takes it off the menus.

It covers every viewset, so the same protection applies to deleting a menu
that is still scheduled.

### The three operations that were missing

**Daily menus.** One cycle for every meal of one hall on one date. Written
by `menu_services.assign_day`, which writes all four meals — breakfast,
lunch, snacks and dinner.

**Weekly menus.** A rotation of cycles across seven days, written by
`menu_services.assign_week`. The rotation follows the order the cycles are
listed in and then repeats: three cycles give Monday the first, Tuesday the
second, Wednesday the first again. That is how a mess actually rotates its
dishes, and it is the operation the board's one-cell-at-a-time editing was
missing.

Both are on the menu screen, as two panels below the single-meal assign
form. Both write through the same `assign_slot`, so a slot that already
holds a cycle is replaced rather than duplicated, and a published slot stays
published.

**Dish management.** The specification asks for "Add dishes. Edit dishes.
Delete dishes." The API had all three; the console had none — the dish
catalogue was read-only, and dishes could only be created through the API.

There is now a console screen at `/console/dishes/`:

- Every active dish with its code, category, portion size, and how many
  records still mention it.
- **Add a dish**, and **edit a dish** on the same page — the edit form
  loads the dish into the same panel, so a correction is one page and needs
  no JavaScript.
- **Delete a dish.** A dish that has never been cooked is deleted. A dish
  that has been cooked is refused, and the refusal says what is holding it
  and offers to retire it instead. Retiring takes it off the menus and
  keeps the history, which is what a kitchen actually wants when it stops
  cooking something.

The screen is closed to everyone without `MANAGE_MASTERS`, which is the mess
office and the administrators. A mess manager gets a 403, because the
specification's own rule is that kitchen staff cannot change the masters.

### Snacks

The board used to hide the snack row, on the grounds that a row of empty
cells for a service nobody runs is noise. That was right for the seeded
data and wrong for the specification, which asks for all four meals to be
assignable.

The rule is now data-driven rather than a hard-coded exclusion: the snack
row appears when the hall has a snack schedule. A mess that does not run
snacks never sees the row; a mess that does, sees it.

---

## 6.2 Recipes and ingredients

Already built and unchanged. A recipe holds the ingredients and their
quantities per serving, and the cost per serving is worked out from them.

```
gross quantity = quantity / (1 - trim loss)
line cost      = gross quantity x unit cost
portion cost   = line cost summed over the recipe
```

The spec's example — rice 100 g, dal 30 g, oil 10 ml, vegetables 50 g — is
the shape the `RecipeItem` table holds. Trim loss is why two costs exist:
buying 1 kg of onion yields less than 1 kg of usable onion, and the
difference is waste the platform already measures elsewhere.

Recipe versions are dated rather than edited, so the cost of a dish served
in March is still recomputable. The console creates a new version; the API
exposes the same thing.

---

## 6.3 Attendance

Already built. The specification asks for QR scanning, RFID integration,
manual attendance, meal service selection, dining hall selection and
attendance history.

| Requirement | State |
|---|---|
| QR scanning | `static/js/scan.js` reads the camera through `BarcodeDetector`, falling back to a typed credential |
| Manual attendance | The credential number is typed into the capture screen and recorded with `method=MANUAL` |
| Meal service selection | The capture screen is bound to one `MealService` |
| Dining hall selection | The service carries its hall; the hall is part of every record |
| Attendance history | `/console/attendance/`, and `/api/attendance/` |
| RFID | Deferred, as the specification allows |

The RFID button is present but honest: it says *"RFID reader not attached —
type the credential number instead."* It does not pretend to work.

The capture screen writes to a local queue first with a client-generated
UUID, and the queue drains itself when the connection comes back. The
database's unique constraint on `client_uuid` is what makes a re-sent batch
safe: 3,000 scans stored, the same 3,000 sent again, **0 rows created**.

---

## 6.4 Calendar and events

### What was already there

`CalendarEvent` carries a name, a kind, a date range, an impact factor, the
meals it touches and the halls it touches. The kinds cover the
specification's list:

| Specification | Event type |
|---|---|
| Examination schedules | `EXAM` |
| University holidays | `HOLIDAY`, `VACATION` |
| Campus events | `FEST`, `SPORTS`, `GUEST`, `OTHER` |

The API exposes them at `/api/events/` with full CRUD.

### What was missing

**There was no way to add an event from the console.** The settings screen
listed the calendar and read-only.

There is now an event form in the settings screen's context column: name,
kind, first day, last day, the effect on demand, and the meals it touches.
Existing events have an **Edit** link that loads the event into the same
form, and the calendar table carries a **Delete** action.

The effect is a multiplier on expected demand: 1.00 is a normal day, 1.20 is
a fifth more people, 0.30 is almost nobody. Overlapping events multiply.
The form refuses an effect below zero or above five, because a factor of
twelve is a typo rather than a forecast.

### How weekends are modelled

The specification lists "Weekends" alongside the events, and it is worth
saying plainly why a weekend is **not** an event here.

A weekend is not a thing that happens on a date. It is a property of the
weekday, it recurs forever, and it happens at the same strength every week.
An event, by contrast, has a name, a date range and an effect.

So the weekend is carried by the engine's **weekday factor**: the model
learns a separate multiplier for each of the seven days from the history,
and Saturday and Sunday get theirs the same way Tuesday does. An exam week
is an event, because exams have a start and an end and a strength that
varies; the weekend is a factor, because it does not.

This is also why adding a "weekend" event type would be wrong: it would put
a recurring weekly fact into a table meant for dated exceptions, and every
forecast in every weekend week would have to be rebuilt when the weekend
changed.

---

## What was verified

```bash
manage.py check
manage.py makemigrations --check --dry-run
manage.py test
```

`tests/test_phase6_modules.py` holds 37 tests covering this phase: the
schedule replacement, the daily and weekly writes, the dish catalogue and
its refusals, the protected delete on the API, the calendar, and the board's
meal rows.

The two probes behind the audit are runnable:

```bash
python .hallmark/probe_roles.py    # every role against every console route
python .hallmark/probe_write.py    # which write controls each role's pages render
```
