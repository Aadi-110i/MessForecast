# Data model

PostgreSQL 18. Every table is created by a Django migration; the schema is in
`apps/*/migrations/`.

## The relationship picture

```
 accounts.User ──────────────┐
        │                    │ recorded_by
        │                    ▼
        │            actuals.ServiceActual ◄──────┐
        │                    │ 1:N                │ service_actual
        │                    ▼                    │
        │            actuals.DishActual ──────────┘
        │                    │                    │
        │                    │ (waste computed)  │
        │                    ▼                    │
        │             waste.WasteRecord           │
        │                                         │
        │                                         │
 catalog.DiningHall ──┬─────────────────────────┘
        │              │ hall
        │              ▼
        │      attendance.MealService ────1:1────► forecasting.Forecast
        │              │  │                        │
        │              │  │ 1:1                    │
        │              │  ▼                        ▼
        │              │  planning.PreparationPlan ──1:1──► planning.IngredientIndent
        │              │      │ 1:N                             │ 1:N
        │              │      ▼                                 ▼
        │              │  PreparationLine                  IndentLine
        │              │
        │              │ 1:N
        │              ▼
        │      attendance.AttendanceRecord
        │
        ├──────► catalog.Ingredient ──1:N──► catalog.CostRate
        │                     ▲
        │                     │ recipe_items
        │              catalog.RecipeItem
        │                     │
        │                     └── catalog.Recipe ──N:1──► catalog.Dish
        │
        └──────► menu.MenuSchedule ──N:1──► menu.Menu ──1:N──► menu.MenuItem ──N:1──► catalog.Dish

 events.CalendarEvent  ──────────── affects dates and meals (multiplier on demand)
 events.ServiceLevelConfig ───────── per hall + meal (over-preparation allowance)
```

## The tables

### Master data — `catalog`

| Table | Key fields | Notes |
|---|---|---|
| `DiningHall` | `code` (unique), `name`, `capacity`, `registered_strength` | `registered_strength` is the number the kitchen used to cook against. It is the yardstick the platform is measured against. |
| `Ingredient` | `code` (unique), `base_unit`, `purchase_pack_size` | `base_unit` is kg / l / piece / etc. Everything downstream is expressed in base units so quantities add up. |
| `CostRate` | `ingredient`, `hall?`, `unit_cost`, `effective_from`, `effective_to?` | Effective-dated. A null `hall` is the campus-wide rate; a hall-scoped rate overrides it. **This is where money enters the system** — no cost is stored on a dish. |
| `Dish` | `code` (unique), `category`, `serving_size_g`, `direct_unit_cost?` | `serving_size_g` converts portions to kilograms of waste. `direct_unit_cost` overrides the recipe-derived cost for a dish bought ready-made. |
| `Recipe` | `dish`, `version`, `effective_from`, `effective_to?` | Versioned, so a recipe change is a new version rather than an edit of history. |
| `RecipeItem` | `recipe`, `ingredient`, `quantity`, `trim_loss_pct` | Quantity **per portion**. `trim_loss_pct` adds the unusable share (peeling, cleaning) on top of the net quantity, so the indent asks for what must actually be bought. |

A dish's cost is never stored — it is derived:

```
cost per portion = Σ over recipe lines of (quantity × current unit cost of that ingredient)
```

Change one ingredient's price and every dish containing it, every indent and every waste
record moves with it.

### Menu — `menu`

| Table | Key fields | Notes |
|---|---|---|
| `Menu` | `code` (unique), `cycle_label` | A named set of dishes, e.g. "Menu Cycle A". |
| `MenuItem` | `menu`, `meal`, `dish`, `sequence`, `expected_share` | `expected_share` is what fraction of the portions students take that dish. It starts at zero — *unknown* — and is learned from the actuals. |
| `MenuSchedule` | `menu`, `hall`, `date`, `meal` | One row per (hall, date, meal). **This row is what makes a service exist** — there is no service without a schedule. Unique on (hall, date, meal). |

### Services and attendance — `attendance`

| Table | Key fields | Notes |
|---|---|---|
| `MealService` | `hall`, `date`, `meal` | Unique on (hall, date, meal). Carries `registered_strength` (from the ERP) and a denormalised `attendance_count`. |
| `AttendanceRecord` | **`client_uuid` (unique)**, `service`, `student?`, `student_identifier`, `method`, `captured_at`, `device_id`, `captured_offline` | The unique constraint on `client_uuid` **is** the sync idempotency guarantee. |
| `AttendanceAudit` | `device_id`, `received`, `created`, `duplicates`, `failed` | The evidence for "syncs without duplication". |

`attendance_count` is a denormalised counter kept in step with the records by
`_refresh_attendance_counts`. The records remain the source of truth; the counter exists so
the forecaster can read a service's demand without a `COUNT(*)` per service.

### Calendar and configuration — `events`

| Table | Key fields | Notes |
|---|---|---|
| `CalendarEvent` | `name`, `event_type`, `start_date`, `end_date`, `impact_factor`, `affects_meals`, `affects_halls` | `impact_factor` is a multiplier on demand: 1.25 means "a quarter more than a normal day", 0.30 means "a third of a normal day". Overlapping events multiply. |
| `ServiceLevelConfig` | `hall?`, `meal?`, `acceptable_overprep_pct`, `max_overprep_pct`, `min_buffer_portions`, `portions_per_student` | The most specific row wins: (hall, meal) beats (hall, any meal) beats (any hall, meal) beats the global default. |

`portions_per_student` is the bridge between people and food: a student at lunch takes rice,
a dal and a curry, so the kitchen cooks about 2.6 portions per student.

### Forecasting — `forecasting`

| Table | Key fields | Notes |
|---|---|---|
| `Forecast` | `service` (1:1), `predicted_attendance`, `lower_bound`, `upper_bound`, `confidence_level` | One row per service. |
| | `base_level`, `weekday_factor`, `event_factor`, `trend_pct`, `rmse`, `mape` | The workings, kept so the number can be explained rather than trusted blindly. |
| | `input_signature` | A SHA-256 hash of every input that produced the forecast. Two runs over the same history must produce the same signature. |
| | `explanation` | The plain-language sentence shown on the kitchen screen. |

### Planning — `planning`

| Table | Key fields | Notes |
|---|---|---|
| `PreparationPlan` | `service` (1:1), `forecast`, `attendance_target`, `portions_target`, `safety_margin_pct`, `portions_to_prepare`, `over_preparation_pct`, `estimated_cost`, `guidance_text`, `status` | |
| `PreparationLine` | `plan`, `dish`, `portions`, `expected_share`, `estimated_cost` | Unique on (plan, dish). |
| `IngredientIndent` | `plan` (1:1), `hall`, `date`, `total_estimated_cost`, `procurement_text` | The procurement list. `procurement_text` is the rendered format the kitchen already uses. |
| `IndentLine` | `indent`, `ingredient`, `quantity`, `unit_cost`, `estimated_cost`, `source_dishes` | Unique on (indent, ingredient). |

### Actuals and waste — `actuals`, `waste`

| Table | Key fields | Notes |
|---|---|---|
| `ServiceActual` | `service` (1:1), `prepared_portions_total`, `served_portions_total`, `leftover_portions_total`, `prep_mode`, `attendance_actual` | `prep_mode` is the field the before/after comparison turns on: the baseline period used `REGISTERED_STRENGTH`, the live period uses `FORECAST_GUIDED`. |
| `DishActual` | `service_actual`, `dish`, `prepared_portions`, `served_portions`, `leftover_portions` | Unique on (service_actual, dish). |
| `WasteRecord` | `service_actual`, `dish`, `leftover_portions`, `waste_quantity`, `cost_per_portion`, `waste_cost`, `forecast_portions`, `over_prepared_portions`, `cause` | Unique on (service_actual, dish). `service_date` is denormalised so waste can be indexed and aggregated by period without joining through the service. |

### Notifications — `notifications`

| Table | Key fields | Notes |
|---|---|---|
| `Notification` | `kind`, `channel`, `recipient?`, `role_target`, `hall?`, `service?`, `subject`, `body`, `status`, `sent_at`, `meta` | Written to an outbox first and dispatched afterwards, so a failed gateway cannot lose the record that the kitchen was told to prepare 540 portions. |

## Money

Every money field is a `DecimalField`. Every quantity that feeds a money field is a
`DecimalField`. There is no floating point anywhere in the costing path, and the rounding
is explicit:

| Helper | Rule |
|---|---|
| `q2` | two decimal places, half-up — money |
| `q3` | three decimal places, half-up — kilograms |
| `largest_remainder` | splits a whole number of portions across dishes so the parts sum back to the whole |

`largest_remainder` matters more than it looks. You cannot cook half a portion, so the
rounding error has to land *somewhere*. The largest-remainder method puts it on the dishes
with the largest fractional shares, which are the dishes where a portion either way is least
significant — and, critically, the parts always add back to the plan total.

## Constraints that protect the data

| Constraint | Protects against |
|---|---|
| `AttendanceRecord.client_uuid` unique | A duplicate attendance record from a re-sent sync |
| `MealService` unique (hall, date, meal) | Two services for the same slot |
| `MenuSchedule` unique (hall, date, meal) | Two menus for the same slot |
| `PreparationLine` unique (plan, dish) | A dish counted twice in one plan |
| `IndentLine` unique (indent, ingredient) | An ingredient requested twice |
| `DishActual` unique (service_actual, dish) | A dish recorded twice for one service |
| `WasteRecord` unique (service_actual, dish) | Waste counted twice |
| `Recipe` unique (dish, version) | Two recipes claiming to be version 1 |
| `RecipeItem` unique (recipe, ingredient) | An ingredient twice in one recipe |
| `CostRate` unique (ingredient, hall, effective_from) | Two rates starting on the same day |

## Indexes that earn their place

| Index | Serves |
|---|---|
| `idx_service_hall_meal_date` | The forecaster's history query — the hottest read in the system |
| `idx_service_date_meal` | Reporting across all halls |
| `idx_att_service_method` | Attendance by capture method |
| `idx_waste_hall_date` | Waste by period and hall |
| `idx_waste_dish_date` | The top-ten waste dishes report |
| `idx_event_window` | The calendar lookup that feeds every event adjustment |

## One thing worth stating plainly

There is no `DemandAggregate` table and no `AccuracySnapshot` table. Both could be built —
a daily rollup would make the dashboards faster. Neither was built, because a rollup is a
second copy of the truth, and the moment it exists something has to keep it in step. The
reporting queries are computed from the facts on demand, which is a little slower and
cannot drift.
