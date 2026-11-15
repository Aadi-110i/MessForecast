# 04 — API reference

Every response body below was captured from the running server against the seeded
database — `python scripts/sample_api.py http://127.0.0.1:8013` reproduces them. Nothing here
is a hand-written guess.

---

## Conventions

| | |
|---|---|
| Base URL | `http://<host>/api/` |
| Authentication | Django session cookie (`POST /accounts/login/`), HTTP Basic, or a JWT bearer token (`POST /api/auth/token/`) |
| Content type | `application/json` for writes, `application/json` for reads |
| CSRF | session-authenticated writes must send `X-CSRFToken` with the `csrftoken` token. Bearer-token requests are exempt from CSRF. |
| Timestamps | ISO-8601 with the campus offset, e.g. `2026-11-05T19:16:06.596268+05:30` |
| Dates | `YYYY-MM-DD` |
| Money and quantities | **strings**, never JSON numbers — `DecimalField` values keep their precision |
| Pagination | `?page=N`, `?limit=N` (default 50). The envelope is `{count, next, previous, results}` |
| Filtering | `?start=YYYY-MM-DD&end=YYYY-MM-DD`, `?hall=<id>`, `?meal=<BREAKFAST\|LUNCH\|DINNER>` |
| Errors | `{"detail": "..."}` or `{"field": ["message"]}` with a 4xx status |

Money and quantities are strings on purpose. A JSON number is a float, and a float cannot hold
`Rs 6.9005000000` exactly — so a client that parses them as numbers silently loses money.

### Status codes

| Code | Meaning |
|---|---|
| 200 | success |
| 400 | the request is wrong — a missing or malformed parameter, or a payload that fails validation |
| 401 | unauthenticated — missing, invalid or expired bearer token |
| 403 | the request is valid but the role does not hold the required capability |
| 404 | the resource does not exist |
| 405 | wrong method for the route |
| 500 | a server fault — a bug; every 500 found during the build is now a regression test |

---

## Roles and capabilities

The capability table lives in `apps/accounts/permissions.py`. Each endpoint below names the
capability it requires for reads and for writes.

| Capability | Student | Kitchen Staff | Mess Manager | Mess Admin | Finance | Admin |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| `VIEW_MENU` | ● | ● | ● | ● | ● | ● |
| `VIEW_OWN_ATTENDANCE` | ● | | | | | |
| `RECORD_ATTENDANCE` | | ● | ● | ● | | ● |
| `MANAGE_MASTERS` | | | | ● | | ● |
| `PLAN_MENU` | | | ● | ● | | ● |
| `PUBLISH_MENU` | | | ● | ● | | ● |
| `VIEW_FORECAST` | | ● | ● | ● | ● | ● |
| `VIEW_PREPARATION_PLAN` | | ● | ● | ● | ● | ● |
| `RECORD_ACTUALS` | | ● | ● | | | ● |
| `VIEW_WASTE_COST` | | | ● | ● | ● | ● |
| `CONFIGURE_SERVICE_LEVEL` | | | ● | | | ● |
| `MANAGE_HALLS` | | | | ● | | ● |
| `VIEW_ACCURACY` | | | ● | | ● | ● |
| `CONFIGURE_FORECAST` | | | | | | ● |
| `MANAGE_USERS` | | | | ● | | ● |

---

## 1. The six endpoints the specification names

### 1.1 `/api/menus` — M1

| Method | Path | Read capability | Write capability |
|---|---|---|---|
| GET | `/api/menus/` | `VIEW_MENU` | — |
| POST | `/api/menus/` | — | `PLAN_MENU` |
| GET/PUT/PATCH/DELETE | `/api/menus/{id}/` | `VIEW_MENU` | `PLAN_MENU` |

```json
{
  "id": 37,
  "name": "Menu Cycle A",
  "code": "MENU_A",
  "cycle_label": "Week A",
  "description": "Light veg cycle with paneer on the dinner turn.",
  "is_active": true,
  "items": [
    {
      "id": 812,
      "menu": 37,
      "meal": "LUNCH",
      "dish": 251,
      "dish_name": "Aloo Gobi",
      "sequence": 1,
      "expected_share": "0.25"
    }
  ]
}
```

`expected_share` is the portion of the meal this dish should supply. It is what the dish-split
step in the preparation planner uses.

#### Companion routes

| Method | Path | Purpose | Read | Write |
|---|---|---|---|---|
| GET/POST | `/api/menu-items/` | a dish inside a menu | `VIEW_MENU` | `PLAN_MENU` |
| GET/POST | `/api/menu-schedules/` | which menu runs where, on which day, for which meal | `VIEW_MENU` | `PLAN_MENU` |

`/api/menu-schedules/` response:

```json
{
  "id": 3109,
  "menu": 37,
  "menu_name": "Menu Cycle A",
  "hall": 25,
  "hall_name": "North Block Mess",
  "date": "2026-08-14",
  "meal": "BREAKFAST",
  "is_published": true,
  "published_at": "2026-11-05T19:15:38.298896+05:30",
  "notes": "",
  "dishes": [{ "dish": 251, "code": "ALOO_GOBI", "meal": "BREAKFAST" }]
}
```

---

### 1.2 `/api/attendance` — M2

#### `POST /api/attendance/sync` — the endpoint the offline queue drains into

**Capability:** `RECORD_ATTENDANCE`

This is the idempotency guarantee the specification asks for. Every record carries a
client-generated UUID; a UUID the server already holds is ignored.

Request:

```json
{
  "device_id": "tablet-north-01",
  "records": [
    {
      "client_uuid": "63790909-b3a7-4767-a283-b4db0a9611e0",
      "service_id": 3609,
      "hall_id": 25,
      "date": "2026-11-05",
      "meal": "BREAKFAST",
      "student_identifier": "N978963",
      "method": "QR",
      "captured_at": "2026-11-05T17:00:00+05:30",
      "device_id": "tablet-north-01",
      "captured_offline": true
    }
  ]
}
```

Response:

```json
{
  "received": 1,
  "created": 1,
  "duplicates": 0,
  "failed": 0,
  "rejected": [],
  "audit_id": 5
}
```

| Field | Meaning |
|---|---|
| `received` | how many records arrived in the batch |
| `created` | how many were new and were stored |
| `duplicates` | how many carried a UUID the server already held, and were dropped |
| `failed` | how many were rejected outright |
| `rejected` | up to 50 of the rejected records, each with `client_uuid` and `reason` |
| `audit_id` | the `AttendanceAudit` row for this batch |

Sending the identical batch again returns `created: 0, duplicates: 1` — verified over real HTTP
in `scripts/verify_e2e.py`, not only in a unit test.

`method` is one of `QR`, `RFID`, `MANUAL`. `captured_offline` records whether the tablet had a
connection at the moment of the scan.

#### `GET /api/attendance/`

**Capability:** `RECORD_ATTENDANCE`

```json
{
  "count": 5613,
  "next": "http://127.0.0.1:8013/api/attendance/?limit=1&page=2",
  "previous": null,
  "results": [
    {
      "id": 32208,
      "client_uuid": "63790909-b3a7-4767-a283-b4db0a9611e0",
      "service": 3609,
      "student": 4327,
      "student_identifier": "N978963",
      "method": "QR",
      "captured_at": "2026-11-05T17:00:00+05:30",
      "device_id": "tablet-north-01",
      "captured_offline": false,
      "synced_at": "2026-11-05T17:00:00+05:30"
    }
  ]
}
```

#### `GET /api/attendance/count?service=<id>` — the live count the scan screen polls

**Capability:** `RECORD_ATTENDANCE`

```json
{
  "service": 3609,
  "hall": "North Block Mess",
  "date": "2026-11-05",
  "meal": "BREAKFAST",
  "attendance_count": 260,
  "registered_strength": 620
}
```

Omitting `service` returns `400 {"detail": "service query parameter is required"}`.

---

### 1.3 `/api/forecasts` — M5

| Method | Path | Read capability | Write capability |
|---|---|---|---|
| GET | `/api/forecasts/` | `VIEW_FORECAST` | — |
| POST | `/api/forecasts/` | — | `CONFIGURE_FORECAST` |
| GET | `/api/forecasts/{id}/` | `VIEW_FORECAST` | — |
| POST | `/api/forecasts/generate/` | — | `PLAN_MENU` |
| POST | `/api/forecasts/{id}/refresh/` | — | `PLAN_MENU` |

```json
{
  "id": 2019,
  "service": 3612,
  "service_date": "2026-11-05",
  "hall_name": "South Block Mess",
  "meal": "LUNCH",
  "method": "recency_weighted_ma_weekday_event_trend",
  "model_version": "baseline-v1",
  "generated_at": "2026-11-05T19:16:06.596268+05:30",
  "horizon_days": 7,
  "predicted_attendance": "327.50",
  "lower_bound": "309.59",
  "upper_bound": "345.40",
  "confidence_level": "0.800",
  "base_level": "336.24",
  "weekday_factor": "0.9738",
  "event_factor": "1.0000",
  "trend_pct": "0.02",
  "rmse": "13.97",
  "mape": "3.40",
  "input_signature": "5f9a097739ba369ef54ce481864ef1db0553090debf73f8ec46d82b7e241bbd7",
  "explanation": "Lunch at South Block Mess on Thursday 05 Nov 2026: we expect about 327 students. Working: over the last 9 weeks this service has been running at roughly 336 students once festivals and exam weeks are removed. Thursdays specifically run 3% quieter than that average, so the weekday has been taken into account. Uncertainty: our forecasts for this hall have been out by about 14 portions on a typical day recently (average error 3.4%), so a sensible planning range is 310 to 345 portions.",
  "is_fallback": false,
  "observations_used": 56,
  "actual_attendance": 319,
  "absolute_percentage_error": "2.664576802507836990595611285"
}
```

The five fields that make the forecast auditable:

| Field | Why it is there |
|---|---|
| `predicted_attendance` | the number the kitchen cooks to |
| `lower_bound` / `upper_bound` | the confidence interval, at `confidence_level` |
| `base_level`, `weekday_factor`, `event_factor`, `trend_pct` | the four adjustments that produced it — shown so a human can check the arithmetic |
| `rmse`, `mape` | how wrong this forecaster has recently been for this service |
| `input_signature` | SHA-256 of every input. Same signature → same forecast, always. A different signature means the inputs changed. |

`explanation` is written for the mess manager in plain language. See
[05 Forecast method](05-forecast-method.md) for what each sentence means.

`actual_attendance` and `absolute_percentage_error` are present once the service has been
recorded; before that they are `null`.

#### `POST /api/forecasts/generate/`

Body (both optional; the defaults are today and today + 7 days):

```json
{ "start": "2026-11-05", "end": "2026-11-12" }
```

```json
{ "forecasts": 42, "start": "2026-11-05", "end": "2026-11-12" }
```

A malformed date returns `400`, not a 500 — there is a regression test for this.

#### `POST /api/forecasts/{id}/refresh/`

Recomputes one forecast from current data and returns it. Useful after a menu change or a new
actual has landed.

---

### 1.4 `/api/preparation-plans` — M6

| Method | Path | Read capability | Write capability |
|---|---|---|---|
| GET | `/api/preparation-plans/` | `VIEW_PREPARATION_PLAN` | — |
| POST | `/api/preparation-plans/generate/` | — | `CONFIGURE_SERVICE_LEVEL` |
| GET | `/api/preparation-plans/{id}/indent/` | `VIEW_PREPARATION_PLAN` | — |

```json
{
  "id": 1344,
  "service": 3612,
  "hall_name": "South Block Mess",
  "service_date": "2026-11-05",
  "meal": "LUNCH",
  "forecast": 2019,
  "generated_at": "2026-11-05T19:16:06.603307+05:30",
  "status": "DRAFT",
  "attendance_target": "329.03",
  "safety_margin_pct": "8.00",
  "portions_to_prepare": 924,
  "over_preparation_pct": "8.01",
  "estimated_cost": "14437.72",
  "guidance_text": "Lunch - South Block Mess - 05 Nov 2026\n\nExpected turnout: 329 students (likely between 313 and 344).\nCook 924 portions - that is 8.0% above the forecast, which is the margin this hall allows.\n\nPortions to prepare:\n  - Steamed Rice: 307 portions\n  ...",
  "notes": "",
  "lines": [
    {
      "id": 4102,
      "dish": 247,
      "dish_name": "Steamed Rice",
      "portions": 307,
      "expected_share": "0.33",
      "estimated_cost": "3373.00",
      "notes": ""
    }
  ]
}
```

`attendance_target` is the forecast; `portions_to_prepare` is the number the kitchen cooks. The
gap between them is the safety margin the hall allows — 8 % here, from `ServiceLevelConfig`.

#### `POST /api/preparation-plans/generate/`

```json
{ "service": 3612 }
```

Returns the plan. Calling it twice for the same service reuses the existing plan rather than
creating a second one.

#### `GET /api/preparation-plans/{id}/indent/` — the procurement export

Returns a CSV download:

```
Ingredient Code,Ingredient,Quantity,Unit,Packs,Unit Cost,Estimated Cost,Source Dishes
RICE,Rice,55.260,kg,2.21,45.00,2486.70,"Steamed Rice (307 portions)"
```

The friendly browser route is `GET /dashboard/export/indent/{id}.csv`, which sets a filename.
The API route sets `Content-Type: text/csv`.

---

### 1.5 `/api/actuals` — M7

| Method | Path | Read capability | Write capability |
|---|---|---|---|
| GET | `/api/actuals/` | `VIEW_WASTE_COST` | — |
| POST | `/api/actuals/` | — | `RECORD_ACTUALS` |
| GET | `/api/actuals/{id}/` | `VIEW_WASTE_COST` | — |
| PUT/PATCH/DELETE | `/api/actuals/{id}/` | — | `RECORD_ACTUALS` |
| POST | `/api/actuals/{id}/recompute-waste/` | — | `RECORD_ACTUALS` |

```json
{
  "id": 3070,
  "service": 3612,
  "hall_name": "South Block Mess",
  "service_date": "2026-11-05",
  "meal": "LUNCH",
  "recorded_by": null,
  "recorded_at": "2026-11-05T19:16:06.627168+05:30",
  "prepared_portions_total": 931,
  "served_portions_total": 829,
  "leftover_portions_total": 102,
  "prep_mode": "FORECAST_GUIDED",
  "attendance_actual": 319,
  "notes": "",
  "dish_actuals": [
    {
      "id": 9114,
      "dish": 247,
      "dish_name": "Steamed Rice",
      "prepared_portions": 310,
      "served_portions": 276,
      "leftover_portions": 34,
      "notes": ""
    }
  ],
  "waste_cost": "1602.73"
}
```

`prep_mode` is `REGISTERED_STRENGTH` (the old habit) or `FORECAST_GUIDED` (cooked to the
forecast). The mix of the two across the seeded history is what makes the before/after
comparison meaningful.

`POST /api/actuals/{id}/recompute-waste/` recalculates the waste records for that actual. It is
idempotent — running it twice leaves the same numbers.

---

### 1.6 `/api/analytics/waste` — M8

**Capability:** `VIEW_WASTE_COST`

Query: `?start=YYYY-MM-DD&end=YYYY-MM-DD&hall=<id>`. Defaults to the last 28 days.

```json
{
  "start": "2026-10-08",
  "end": "2026-11-05",
  "hall": "all halls",
  "totals": {
    "waste_cost": 121437.37,
    "waste_quantity_kg": 1748.79,
    "records": 734
  },
  "by_week": [
    { "week": "2026-10-05", "waste_cost": 18205.21, "waste_quantity_kg": 258.99, "services": 24 }
  ],
  "by_meal": [
    { "meal": "BREAKFAST", "waste_cost": 16864.15, "waste_quantity_kg": 337.8, "records": 212 }
  ],
  "by_hall": [
    { "hall_id": 25, "hall": "North Block Mess", "code": "NORTH", "waste_cost": 69309.74, "records": 367 }
  ],
  "top_dishes": [
    {
      "dish_id": 254,
      "dish": "Chicken Curry",
      "code": "CHICKEN_CURRY",
      "waste_cost": 28696.55,
      "waste_quantity_kg": 166.4,
      "leftover_portions": 832,
      "services": 40
    }
  ]
}
```

`top_dishes` is the specification's "top-ten waste dishes" report.

---

## 2. The other analytics endpoints

### `GET /api/analytics/accuracy` — M9

**Capability:** `VIEW_ACCURACY`

```json
{
  "start": "2026-10-08",
  "end": "2026-11-05",
  "summary": {
    "forecasts": 174,
    "mape_pct": 2.3,
    "mean_bias": -0.55,
    "coverage_pct": 93.1,
    "within_range": 162
  },
  "exact_mape_pct": "2.30",
  "by_meal_and_hall": [
    { "meal": "BREAKFAST", "hall": "North Block Mess", "hall_code": "NORTH",
      "forecasts": 29, "avg_predicted": 235.73, "avg_actual": 234.76, "mape_pct": 0.41 }
  ],
  "over_time": [
    { "week": "2026-10-05", "forecasts": 24, "avg_predicted": 369.5, "avg_actual": 371.92, "mape_pct": 0.65 }
  ],
  "rows": [
    {
      "date": "2026-10-08",
      "hall": "North Block Mess",
      "meal": "BREAKFAST",
      "predicted": 255.66,
      "lower_bound": 241.74,
      "upper_bound": 269.57,
      "actual": 244,
      "error": -11.66,
      "ape_pct": 4.778688524590164,
      "within_range": true,
      "explanation": "Breakfast at North Block Mess on Thursday 08 Oct 2026: ..."
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `mape_pct` | mean absolute percentage error across the window |
| `mean_bias` | mean signed error. Negative means the forecast runs **below** the actual |
| `coverage_pct` | share of actuals that landed inside the published interval |
| `within_range` | how many actuals fell inside the interval |

`mape_pct` is rounded for display; `exact_mape_pct` is the unrounded value, kept as a string.

### `GET /api/analytics/savings`

**Capability:** `VIEW_ACCURACY`

**All four dates are required.** Omitting one returns `400` with the offending field named —
not a 500.

```
GET /api/analytics/savings?baseline_start=2026-08-14&baseline_end=2026-09-10&live_start=2026-09-11&live_end=2026-11-05
```

```json
{
  "baseline_start": "2026-08-14",
  "baseline_end": "2026-09-10",
  "live_start": "2026-09-11",
  "live_end": "2026-11-05",
  "comparison": { "...": "baseline and live totals side by side" },
  "trend": [{ "week": "2026-09-07", "...": "saving trend by week" }]
}
```

### `GET /api/analytics/demand` — M4

**Capability:** `VIEW_FORECAST`

```json
{
  "start": "2026-10-08",
  "end": "2026-11-05",
  "summary": {
    "services": 174,
    "total_attendance": 51689,
    "avg_attendance": 297.1,
    "registered_strength": 91350,
    "attendance_rate_pct": 56.6
  },
  "by_weekday": [
    { "weekday": "Sunday", "services": 0, "total_attendance": 0, "avg_attendance": 0.0 }
  ],
  "by_meal": [
    { "meal": "BREAKFAST", "services": 58, "total_attendance": 11522, "avg_attendance": 198.7 }
  ],
  "by_week": [
    { "week": "2026-10-05", "services": 24, "total_attendance": 8926, "avg_attendance": 371.9 }
  ],
  "by_period": {
    "exam_services": 72,
    "exam_total": 30431,
    "exam_avg": 422.7,
    "normal_services": 102,
    "normal_total": 21258,
    "normal_avg": 208.4,
    "exam_lift_pct": 102.8
  },
  "dish_demand": [
    { "dish": "Chapati", "code": "CHAPATI", "services": 96,
      "prepared_portions": 22622, "served_portions": 20885, "leftover_portions": 1737 }
  ]
}
```

`by_weekday` always returns all seven days so a chart has a stable axis.

`by_period` is the exam-period comparison: in this window, exam services ran at **422.7** students
against **208.4** on ordinary days — a **102.8 %** lift. This is the single biggest driver of
mess demand on a campus, which is why the forecaster treats the academic calendar as a first-class
feature rather than a note in a comment.

### `GET /api/analytics/ingredients`

**Capability:** `VIEW_PREPARATION_PLAN`

Ingredient consumption against the indent:

```json
{
  "start": "2026-10-08",
  "end": "2026-11-05",
  "rows": [
    { "indent_id": 1173, "ingredient_id": 313, "ingredient": "Rice",
      "indented": 6.96, "consumed": 6.12, "variance": 0.84, "variance_pct": 12.07 }
  ]
}
```

---

## 3. Master-data endpoints

| Endpoint | Read | Write | Notes |
|---|---|---|---|
| `/api/halls/` | `VIEW_MENU` | `MANAGE_HALLS` | dining halls |
| `/api/ingredients/` | `VIEW_MENU` | `MANAGE_MASTERS` | includes `current_unit_cost` |
| `/api/dishes/` | `VIEW_MENU` | `MANAGE_MASTERS` | includes `cost_per_portion` |
| `/api/recipes/` | `VIEW_MENU` | `MANAGE_MASTERS` | versioned recipes |
| `/api/cost-rates/` | `VIEW_WASTE_COST` | `MANAGE_MASTERS` | effective-dated rates |
| `/api/events/` | `VIEW_MENU` | `PLAN_MENU` | calendar and event registry |
| `/api/service-levels/` | `VIEW_FORECAST` | `CONFIGURE_SERVICE_LEVEL` | service-level configuration |
| `/api/indents/` | `VIEW_PREPARATION_PLAN` | `CONFIGURE_SERVICE_LEVEL` | ingredient indents |
| `/api/dish-actuals/` | `VIEW_WASTE_COST` | `RECORD_ACTUALS` | per-dish actuals |
| `/api/waste/` | `VIEW_WASTE_COST` | `CONFIGURE_FORECAST` | waste records |
| `/api/notifications/` | `VIEW_MENU` | `CONFIGURE_FORECAST` | the notification outbox |

`/api/ingredients/` returns the current rate:

```json
{
  "id": 338, "name": "Banana", "code": "BANANA",
  "base_unit": "piece", "purchase_pack_size": "60.000", "purchase_pack_unit": "60 piece",
  "category": "Fruit", "is_active": true, "current_unit_cost": "6.0000"
}
```

`/api/dishes/` returns the cost per portion:

```json
{
  "id": 251, "name": "Aloo Gobi", "code": "ALOO_GOBI", "category": "VEG",
  "serving_size_g": "200.00", "direct_unit_cost": null, "is_active": true,
  "cost_per_portion": "6.9005000000"
}
```

`/api/events/` — the event registry, with the impact factor that feeds the forecaster:

```json
{
  "id": 57,
  "name": "Winter Vacation",
  "event_type": "VACATION",
  "start_date": "2026-10-24",
  "end_date": "2026-11-01",
  "impact_factor": "0.300",
  "affects_meals": "",
  "affects_halls": [],
  "description": "Most students have gone home. The mess serves a reduced roll.",
  "is_active": true
}
```

`impact_factor` multiplies the base level: `0.300` means 30 % of normal attendance. The
forecaster clamps this factor to a sane range so one mis-typed event cannot empty a forecast.

---

## 4. A worked example

Fetch the forecast, turn it into a plan, and export the indent:

```bash
# 1. Today's lunch services
curl -b cookies.txt "http://127.0.0.1:8013/api/services/?date=2026-11-05&meal=LUNCH"

# 2. Generate the plan for one of them
curl -b cookies.txt -X POST \
  -H "Content-Type: application/json" -H "X-CSRFToken: <token>" \
  -d '{"service": 3612}' \
  "http://127.0.0.1:8013/api/preparation-plans/generate/"

# 3. Download the procurement indent
curl -b cookies.txt "http://127.0.0.1:8013/api/preparation-plans/1344/indent/" -o indent.csv
```

---

## 5. Errors

**401 / 403.** Session authentication is listed first, and Django's session backend does not
advertise a challenge header, so DRF answers **403** rather than 401 for an anonymous request.
The body says which:

```json
{ "detail": "Authentication credentials were not provided." }
```

```json
{ "detail": "Your role does not allow this action." }
```

**400.** The body names the field:

```json
{ "baseline_start": ["This date parameter is required."] }
```

```json
{ "start": ["'13/11/2026' is not an ISO date (YYYY-MM-DD)."] }
```

**404.** `{"detail": "Not found."}`

Every error path above was exercised: `scripts/sweep_urls.py` requests every route as every role
and fails on any 5xx, and `tests/test_regressions.py` pins the 400-versus-500 behaviour of the
date endpoints.

---

## 6. Authentication (JWT)

The API accepts a JWT bearer token issued by
[`rest_framework_simplejwt`](https://django-rest-framework-simplejwt.readthedocs.io).
Session authentication remains available for the rendered web application; the two auth
mechanisms are independent and a request authenticated either way is subject to the same
role-based capability checks.

| Setting | Environment variable | Default |
|---|---|---|
| Signing key | `JWT_SIGNING_KEY` | `SECRET_KEY` |
| Access token lifetime | `JWT_ACCESS_TOKEN_LIFETIME_MINUTES` | `15` |
| Refresh token lifetime | `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | `7` |
| Rotate refresh tokens | `JWT_ROTATE_REFRESH_TOKENS` | `true` |
| Blacklist after rotation | `JWT_BLACKLIST_AFTER_ROTATION` | `true` |

### `POST /api/auth/token/` — obtain a pair

Body: `{"username": "<email or username>", "password": "<password>"}`. Either the username or
the email address may be supplied as `username`.

Response `200`:
```json
{
  "access": "<JWT access token>",
  "refresh": "<JWT refresh token>",
  "user": { "id": 3, "username": "manager", "email": "manager@mess.example",
            "name": "Manager", "role": "MESS_MANAGER",
            "role_display": "Mess Manager", "student_identifier": null }
}
```

Invalid or missing credentials return `401`.

### `POST /api/auth/token/refresh/` — refresh

Body: `{"refresh": "<refresh token>"}`. Returns a new `access` token. With rotation enabled the
old refresh token is blacklisted and a new refresh token is returned.

Missing or blacklisted refresh token returns `401`.

### `POST /api/auth/logout/` — logout

Body: `{"refresh": "<refresh token>"}`. Blacklists the refresh token so it can no longer be
used or rotated. Requires an authenticated session or bearer token. Returns `204`.

### `GET /api/auth/me/` — the authenticated user

Returns the calling user's profile and sorted `capabilities` list (derived from
`apps/accounts/permissions.py`). Requires authentication. Returns `401` when no valid
token or session is present.

### `GET/PATCH /api/accounts/profile/` — own profile

`GET` returns the caller's profile. `PATCH` updates `first_name`, `last_name` and `email`.
`username`, `role` and `student_identifier` are read-only — a user can never promote
themselves. Returns `403` when unauthenticated.

### `POST /api/accounts/change-password/` — change password

Body: `{"old_password": "...", "new_password": "...", "new_password_confirm": "..."}`.
Validates the current password and runs Django's password validators. Returns `200` on success.

### Password reset

| Method | Path | Purpose |
|---|---|---|
| GET | `/accounts/password-reset/` | Forgot-password form |
| POST | `/accounts/password-reset/request/` | Accept an email and, if an account matches, send a one-time reset link |
| GET | `/accounts/password-reset/confirm/<token>/` | Reset-password form for a valid link |
| POST | `/accounts/password-reset/confirm/<token>/complete/` | Set a new password and spend the token |

- Whether an email is registered is never confirmed or denied.
- Tokens are single-use, time-limited (`PASSWORD_RESET_TIMEOUT_SECONDS`, default 1 hour), and
  are revoked on use — a captured link cannot be replayed.
- Changing a password deletes all of the user's outstanding refresh tokens.
- Rate limited: 3 requests per email per hour, 10 per IP per hour.
- Email is sent through the configured `DJANGO_EMAIL_BACKEND`; the console backend is used
  for local development so reset links are printed to the terminal.

## 7. Capability-aware navigation and controls

The rendered navigation rail (`templates/base.html`) hides any destination the session's user
does not hold the required capability for, and the write controls on the console screens
(create recipe version, assign a cycle, edit a dish) are shown only to roles that hold
`MANAGE_MASTERS` or `PLAN_MENU`. The backend enforces the same capabilities on every API
request, so a frontend-only bypass is not possible.

