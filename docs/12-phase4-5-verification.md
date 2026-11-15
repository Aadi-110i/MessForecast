# Phases 4 and 5 — verification against the specification

The specification defines Phase 4 as the database design and Phase 5 as
authentication with role-based access. Both were largely built before this
document existed, so this file is the evidence that they are done, plus an
honest account of the three places where the implementation did not match
the specification's letter.

Read with [03-data-model.md](03-data-model.md) (every table and its keys),
[04-api-reference.md](04-api-reference.md) (what the API exposes) and
[01-requirements-traceability.md](01-requirements-traceability.md) (the full
line-by-line map).

---

## Phase 4 — Database design

### The models, one by one

The specification names fifteen models. All fifteen exist. Four of them
needed more than one table to do their job honestly, and the specification's
own field list is loose in three places.

| Specification model | Specification fields | Where it lives | Assessment |
|---|---|---|---|
| User | name, email, role | `accounts.User` | `name` is `first_name` / `last_name` with `get_full_name()`; `email`, `role` and the six-role enum are as specified |
| DiningHall | name, location | `catalog.DiningHall` | `name`; `location` added in this pass, alongside `code`, `capacity`, `registered_strength` |
| Dish | name, category, portion_size | `catalog.Dish` | `portion_size` is `serving_size_g`, a `Decimal` in grams |
| Ingredient | name, unit, cost_per_unit, stock | `catalog.Ingredient` + `catalog.CostRate` | `unit` is `base_unit`; `cost_per_unit` lives in `CostRate` because prices are effective-dated; `stock_quantity` added in this pass |
| Recipe | dish, ingredients, quantities | `catalog.Recipe` + `catalog.RecipeItem` | The ingredient list is a through-table, so each line carries its own quantity, unit and trim loss |
| Menu | date, meal_type, dining_hall | `menu.Menu` + `menu.MenuSchedule` | **Normalised.** A `Menu` is the cycle; `MenuSchedule` binds a cycle to a hall, a date and a meal |
| MenuItem | menu, dish | `menu.MenuItem` | Adds `meal`, `sequence` and `expected_share` |
| MealService | date, meal_type, hall | `attendance.MealService` | Plus `registered_strength`, `prep_mode` and `attendance_count` |
| AttendanceRecord | user, service, timestamp, client_uuid | `attendance.AttendanceRecord` | `client_uuid` is unique — the specification's flagged decision |
| CalendarEvent | date, event_type, impact | `events.CalendarEvent` | `impact` is `impact_factor`, a `Decimal` |
| Forecast | service, predicted, lower, upper | `forecasting.Forecast` | Plus the decomposition that makes the number arguable: `base_level`, `weekday_factor`, `event_factor`, `trend_pct`, `rmse`, `mape` |
| PreparationPlan | forecast, ingredients | `planning.PreparationPlan` + `PreparationLine` + `IngredientIndent` + `IndentLine` | The plan and the indent are separate tables because they are published separately |
| ServiceActual | service, prepared, served, leftover | `actuals.ServiceActual` + `actuals.DishActual` | The service total and the per-dish breakdown |
| WasteRecord | dish, quantity, cost | `waste.WasteRecord` | Plus the forecast it is measured against |
| CostRate | ingredient, unit_cost | `catalog.CostRate` | Plus `hall`, `effective_from`, `effective_to` and `source` |

Five further tables exist because the work needed them: `MenuSchedule`,
`AttendanceAudit` (the sync batch), `ServiceLevelConfig` (the
over-preparation rules), `Notification`, and `RecipeItem`.

### The four requirements the specification names

**Proper foreign keys.** Every relationship is a real `ForeignKey`, never a
loose integer. `on_delete` is chosen per relationship rather than defaulted:
`PROTECT` where deleting a dish would orphan a published menu, `CASCADE`
where the child has no meaning alone, `SET_NULL` where the parent may
retire without losing history.

**Unique constraints.** Fifteen of them, at two levels.

*Single-column:* `User.student_identifier`, `DiningHall.name`,
`DiningHall.code`, `Ingredient.code`, `Dish.code`, `Menu.name`, `Menu.code`,
and `AttendanceRecord.client_uuid`.

*Composite:* `MealService(hall, date, meal)`, `Recipe(dish, version)`,
`RecipeItem(recipe, ingredient)`, `CostRate(ingredient, hall, effective_from)`,
`MenuItem(menu, meal, dish)`, `MenuSchedule(hall, date, meal)`,
`DishActual(service_actual, dish)`, `PreparationPlan(plan, dish)`,
`IngredientIndent(indent, ingredient)` and `WasteRecord(service_actual, dish)`.

**Indexes.** Declared on the columns that are actually filtered: `User.role`,
`MenuSchedule.date` and `.meal`, `MenuItem.meal`, `AttendanceRecord` on
`(service, method)` and `(service, student_identifier)`, `MealService` on
`(hall, meal, date)` and `(date, meal)`, `Forecast` on `(service,
-generated_at)`, `WasteRecord` on `(hall, service_date)` and `(dish,
-service_date)`, and `CalendarEvent` on `(start_date, end_date)`.

**Decimal fields for money.** Every rupee amount, every percentage and every
quantity is a `DecimalField` — 38 in total. No float holds money anywhere in
the schema. The one deliberate exception is the JSON payload of the
attendance sync endpoint, which is validated into `Decimal` on the way in.

### The one decision the specification singled out

> attendance records must have a client-generated UUID with a unique database
> constraint. This will prevent duplicate records during offline synchronization.

Implemented at `apps/attendance/models.py:73`:

```python
client_uuid = models.UUIDField(default=uuid_lib.uuid4, unique=True, editable=False)
```

The tablet generates the UUID before the record leaves it, so a batch that
is sent twice is rejected by the database, not by application logic. The
measured consequence is in [`docs/06-testing.md`](06-testing.md): 3,000 scans
stored in 5.5 s, and the same 3,000 sent again create **0 rows**.

### Two deviations, both deliberate

**`Menu` is a cycle, not a scheduled meal.** The specification writes
`Menu(date, meal_type, dining_hall)`, which would store the same twelve
dishes once per day. This platform stores a cycle once and binds it to days
through `MenuSchedule` — 3 cycles and 504 schedule rows rather than 504
copies of the same three menus. A dish edited on a cycle reaches every
scheduled date at once.

**`stock` is nullable.** `Ingredient.stock_quantity` was added in this pass
to match the specification's field list. It defaults to null, not zero,
because a zero that was never counted is a lie. The platform measures demand
and waste; it has no stock ledger, so null is the honest answer until the
mess starts counting.

---

## Phase 5 — Authentication and role-based access

### The seven items

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | User registration | **Done** | `apps/accounts/registration.py`, `apps/accounts/views.py`. A code issued by the mess office carries the role, is single use, and expires in fourteen days |
| 2 | Login and logout | **Done** | `django.contrib.auth.urls` at `/accounts/`, with `LOGIN_REDIRECT_URL` pointed at the dashboard |
| 3 | Password hashing | **Done** | Django's default PBKDF2 hasher — `PASSWORD_HASHERS` is deliberately not overridden. Four validators are on: similarity, minimum length, common password, numeric |
| 4 | JWT authentication | **Done** | `rest_framework_simplejwt` added to `DEFAULT_AUTHENTICATION_CLASSES` (first, so bearer tokens are challenged with `WWW-Authenticate: Bearer`); `POST /api/auth/token/`, `POST /api/auth/token/refresh/`, `POST /api/auth/logout/` (blacklists the refresh token), `GET /api/auth/me/`. Session authentication is retained for the web application. `tests/test_phase5.py::JWTAuthenticationTests` |
| 5 | Role-based authorization | **Done** | `apps/accounts/permissions.py` holds the capability table; `apps/api/permissions.py` turns it into `HasCapability` |
| 6 | Profile management | **Done** | `GET/PATCH /api/accounts/profile/`, `POST /api/accounts/change-password/`, rendered page at `/accounts/profile/`. Role and student identifier are read-only. `tests/test_phase5.py::ProfileTests` |
| 7 | Password reset | **Done** | Forgot → time-limited single-use token → email → set new password → token spent. No email enumeration; rate limited. `POST /accounts/password-reset/request/`, `GET/POST /accounts/password-reset/confirm/<token>/`. `tests/test_phase5.py::PasswordResetTests` |
| 8 | Separate role-specific dashboards | **Done** | `dashboard_home` routes each of the six roles to its own surface: student → `/dashboard/student/`, kitchen staff → `/kitchen/`, finance → `/dashboard/finance/`, manager/admin/mess-admin → `/dashboard/`. `tests/test_phase5.py::RoleDashboardTests` |
| 9 | Capability-aware navigation | **Done** | The rail in `templates/base.html` hides any destination the session's user does not hold the capability for (`apps/core/templatetags/capabilities.py`). `tests/test_phase5.py::CapabilityNavigationTests` |
| 10 | Capability-aware UI controls | **Done** | Create-recipe-version, assign-cycle and edit-dish controls are rendered only to roles holding `MANAGE_MASTERS` / `PLAN_MENU`. Backend enforces the same on every API request. `tests/test_phase5.py::RoleAccessTests` |
| 11 | Student-facing interface | **Done** | `/dashboard/student/` shows today's menu, upcoming menus, own attendance and announcements. `tests/test_phase5.py::RoleDashboardTests::test_student_dashboard_renders` |

### The role matrix, and the permissions the specification names

The specification's four examples, checked against the capability table:

| Specification rule | Enforced by |
|---|---|
| Students cannot edit recipes | `STUDENT` holds only `VIEW_MENU` and `VIEW_OWN_ATTENDANCE`; `MANAGE_MASTERS` is admin-only |
| Kitchen staff cannot change ingredient costs | Ingredient costs live behind `MANAGE_MASTERS` (mess admin, administrator). `KITCHEN_STAFF` holds no master-editing capability |
| Finance officers have read-only financial access | `FINANCE_OFFICER` holds `VIEW_WASTE_COST` and `VIEW_ACCURACY` — both read capabilities — and no write capability anywhere |
| Mess managers can manage menus and review forecasts | `MESS_MANAGER` holds `PLAN_MENU`, `PUBLISH_MENU` and `VIEW_FORECAST` |

The specification's illustrative `IsMessManager` permission class is
generalised into `HasCapability`, which reads the capability a view declares
rather than testing one role. A view that forgets to declare a capability is
closed by default, not open.

### Separate dashboards and capability-aware UI (previously the open gap)

The specification's deliverable — *"Working authentication with separate user dashboards"* — is now met.

`dashboard_home` (`apps/reporting/views.py`) routes each role to its own surface on sign-in:

| Role | Lands on | Renders |
|---|---|---|
| Student | `/dashboard/student/` | Today's menu, upcoming menus, own attendance, announcements, profile link |
| Kitchen staff | `/kitchen/` | Today's preparation plan, record prepared/served, hall-scoped |
| Finance officer | `/dashboard/finance/` | Waste cost, forecast accuracy, preparation plans — read only |
| Mess manager | `/dashboard/` | Full operational overview |
| Mess administrator | `/dashboard/` (+ `/console/settings/`) | Master data: dishes, recipes, ingredients, halls |
| Administrator | `/dashboard/` | All administrative sections |

The navigation rail in `templates/base.html` is capability-aware: a student is not
offered Forecast, Settings, Data quality, Kitchen or Capture; kitchen staff are
not offered financial reports or master-data tooling; finance officers are not
offered write controls. Write controls (create recipe version, assign cycle,
edit dish) are rendered only to roles holding `MANAGE_MASTERS` / `PLAN_MENU`.
The backend enforces the same capabilities on every API request, so the
interface never offers a control the server would refuse.

`VIEW_OWN_ATTENDANCE`, previously a declared capability with no page behind it,
now backs the student attendance panel on `/dashboard/student/`.

---

## How this is verified

```bash
manage.py check
manage.py makemigrations --check --dry-run
manage.py test
```

`tests/test_api.py::PermissionTests` covers the role permissions that guard
the API, and `tests/test_regressions.py` covers the console routes a role
must not reach. The role probe above is reproducible with
`.hallmark/probe_roles.py`, which signs in as each role and requests every
console route, and `.hallmark/probe_write.py`, which checks which write
controls each role's pages render.
