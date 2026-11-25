# MessForecast

Meal demand forecasting and food-waste tracking platform for campus messes, built with Python, Django, and PostgreSQL.

It forecasts meal attendance, generates kitchen preparation plans and ingredient indents, captures attendance (QR/manual), and tracks post-service leftovers and waste cost.

## Setup & Run

```bash
# 1. Create virtual environment and install dependencies
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# 2. Configure PostgreSQL in .env
# POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT

# 3. Apply migrations and seed demo data (optional)
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py seed_demo --reset
.\.venv\Scripts\python manage.py seed_forward --days 21

# 4. Start the server
.\.venv\Scripts\python manage.py runserver
```

Open `http://127.0.0.1:8000/` (demo manager login: `manager` / `messdemo`).

## Main Routes

- `/` — Public landing page
- `/accounts/login/` — Sign in
- `/dashboard/` — Manager overview, waste, accuracy, planning
- `/dashboard/student/` — Student menu, notices, and QR attendance check-in
- `/kitchen/` — Kitchen tablet screen for preparation & actuals
- `/scan/` — Counter attendance scanner
- `/console/menus/`, `/console/recipes/`, `/console/forecast/` — Management console
- `/api/` — REST API (Session & JWT auth)

## Tests

```bash
.\.venv\Scripts\python manage.py test
```
