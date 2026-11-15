# Architecture

## The shape of it

```
                    ┌─────────────────────────────────────────────┐
                    │              Django / DRF                   │
                    │                                             │
  browser ────────►│  HTML surfaces (dashboard, kitchen, scan)   │
  tablet           │  REST API   /api/...                        │
                    │                                             │
                    │  ┌───────────────────────────────────────┐  │
                    │  │  Domain apps (one per functional area) │  │
                    │  │                                       │  │
                    │  │  accounts  catalog  menu              │  │
                    │  │  attendance  events  demand          │  │
                    │  │  forecasting  planning  actuals      │  │
                    │  │  waste  reporting  notifications      │  │
                    │  └───────────────────────────────────────┘  │
                    │                     │                       │
                    │              service layer                    │
                    │        (the business rules live here)        │
                    │                     │                       │
                    └─────────────────────┼───────────────────────┘
                                          │
                    ┌─────────────────────┼───────────────────────┐
                    │            PostgreSQL 18                    │
                    │  shared-everything, one database, one truth │
                    └─────────────────────────────────────────────┘
```

Celery sits alongside: scheduled forecast generation, preparation guidance, missing-actuals
reminders and high-waste alerts. With no broker configured the tasks run eagerly inside the
calling process, so `manage.py run_forecasts` and the beat schedule behave identically on a
laptop and on a server.

## Layering, and why each layer exists

The rule the codebase follows: **HTTP shapes never contain business rules, and business
rules never touch HTTP.**

| Layer | Where | Rule |
|---|---|---|
| View / serializer | `apps/*/views.py`, `apps/api/views.py` | Parse, validate, authorise, delegate, format. No arithmetic. |
| Service | `apps/*/services.py` | The business rules. No request objects, no `Response`. |
| Model | `apps/*/models.py` | The shape of the data and the constraints that protect it. |

Two concrete examples of the rule earning its keep:

* **`sync_attendance_batch`** (`apps/attendance/services.py`) knows about UUIDs, duplicate
  suppression, in-batch collapsing and the denormalised attendance counter. The API view
  knows about JSON. Neither knows about the other.
* **`generate_preparation_plan`** (`apps/planning/services.py`) knows the arithmetic from
  forecast to indent. The API view knows that a plan needs a service id. A Celery task
  knows neither of those things, and can call the service directly.

## The functional modules, mapped to the specification

| Spec module | Django app | Main models |
|---|---|---|
| M1 Menu, dish and recipe management | `catalog`, `menu` | `DiningHall`, `Ingredient`, `Dish`, `Recipe`, `RecipeItem`, `CostRate`, `Menu`, `MenuItem`, `MenuSchedule` |
| M2 Meal attendance capture | `attendance` | `MealService`, `AttendanceRecord`, `AttendanceAudit` |
| M3 Calendar and event registry | `events` | `CalendarEvent`, `ServiceLevelConfig` |
| M4 Historical demand analysis | `demand` (service layer only) | — |
| M5 Forecasting engine | `forecasting` | `Forecast` |
| M6 Preparation and ingredient planning | `planning` | `PreparationPlan`, `PreparationLine`, `IngredientIndent`, `IndentLine` |
| M7 Post-service recording | `actuals` | `ServiceActual`, `DishActual` |
| M8 Waste measurement and costing | `waste` | `WasteRecord` |
| M9 Accuracy and improvement reporting | `reporting` (service layer only) | — |
| Notifications | `notifications` | `Notification` |
| Roles and permissions | `accounts` | `User` |

`demand` and `reporting` have no models of their own: they are queries over the facts other
modules recorded. Giving them tables would mean maintaining a second copy of the truth.

## The flow, end to end

This is the path a single meal takes through the system.

```
1. PLANNING THE MENU                    menu.MenuSchedule
   A menu is assigned to a hall for a date and meal. That row is what makes
   the service exist: the kitchen cannot plan a meal that has no schedule.

2. CAPTURING ATTENDANCE                 attendance.AttendanceRecord
   The tablet scans students. Each scan carries a client UUID. The server
   ignores a UUID it already holds. The service's attendance_count is kept
   in step so the forecaster can read demand without a COUNT per service.

3. FORECASTING                          forecasting.Forecast
   The engine takes the event-adjusted history, the moving average, the
   weekday factor, the trend and the calendar. It stores the answer, the
   range, the workings and a plain-language explanation, plus a hash of the
   inputs so the forecast can be proved reproducible.

4. PLANNING PREPARATION                 planning.PreparationPlan
   Forecast -> students -> portions (using portions-per-student) -> a
   margin -> split across the dishes by what students actually eat ->
   ingredient quantities -> a procurement indent with a cost.

5. COOKING AND RECORDING                actuals.ServiceActual
   On the kitchen screen: what was prepared, what was served, what was left
   over, per dish. Recorded offline if the network is down.

6. COSTING THE WASTE                    waste.WasteRecord
   Leftovers become kilograms and rupees, using the same recipe and the
   same prices that produced the indent. The forecast is stored alongside so
   over-preparation can be told apart from a busy day.

7. LEARNING                             reporting, planning
   The forecast is scored against the actual turnout (MAPE). The dish
   shares are re-learned from what was actually served. The next plan is
   better than the last one.
```

## The forecasting engine is deliberately isolated

`apps/forecasting/engine.py` has no Django import and no database access. It takes a list
of `Observation` objects and returns a `ForecastResult`.

That isolation buys three things:

1. **It is testable without a database.** The arithmetic is checked directly.
2. **It is reproducible.** There is no randomness and no wall-clock dependence; the same
   history always yields the same numbers, and `input_signature` records a hash of
   everything that was used.
3. **It is replaceable.** When a term of data justifies gradient boosting or Prophet, this
   module is the thing that gets swapped. The call site already speaks in observations and
   results, so nothing else has to change.

## Query discipline

The application works on a whole service at a time: several dishes, their recipes, the
recipe lines and the ingredient prices. Fetching each of those one at a time is the classic
N+1 problem, and it dominated the runtime when a twelve-week history was processed service
by service.

`apps/catalog/models.py` therefore carries three batch helpers that are used everywhere a
set of dishes is processed:

| Helper | Replaces |
|---|---|
| `active_recipes_for(dishes, on_date)` | one query per dish |
| `recipe_items_for(recipes)` | one query per recipe |
| `cost_map(ingredients, on_date, hall)` | one query per ingredient |

The same pattern appears in the event calendar (`EventCalendar` resolves each event's hall
scope once, in memory) and in the waste service (one query for the plan's expected
portions rather than one per dish).

## The offline path

The tablet and the server are separated by a queue, and the queue is the only thing that
has to survive a disconnection.

```
 tablet                              server
 ──────                              ──────
 scan ──► IndexedDB queue
            │
            ├── online ─────────────► POST /api/attendance/sync
            │                         (client UUID decides what is new)
            │
            └── offline ── wait ──► (drains automatically on reconnect)
```

The service worker handles the shell; IndexedDB handles the data; the unique constraint on
`client_uuid` handles the duplication. See
[`10-offline-and-sync.md`](10-offline-and-sync.md).

## Security and permissions

Six roles, one capability table (`apps/accounts/permissions.py`). Every API view declares
the capability it needs; `HasCapability` turns that into a check, splitting reads from
writes so that, for example, a finance officer can read waste cost without being able to
change a recipe.

| Role | Capabilities |
|---|---|
| Student | view menu, view own attendance |
| Kitchen staff | record attendance, view forecast and plan, record actuals |
| Mess manager | plan menus, publish, view forecast, plan, waste, accuracy, set service levels |
| Mess administrator | manage masters, dishes, recipes, halls, plan menus, view waste |
| Finance officer | view forecast, plan, waste cost, accuracy — read only |
| Administrator | everything, including forecast configuration |

Kitchen staff are additionally scoped to their own hall.
