# 08 — Deployment

How this system is served, and what changes between a laptop and a server.

The specification's deployment requirement for Track P:

> *Serve the PWA from Django with correct cache headers, or as static files behind the CDN; the
> service worker is plain JavaScript and is not a Django concern.*

---

## 1. What is deployed

| Piece | What it is |
|---|---|
| `config/` | the Django project — settings, URLs, Celery, WSGI, ASGI |
| `apps/` | thirteen application packages plus the REST API |
| `templates/`, `static/` | the server-rendered UI and the PWA assets |
| `manage.py` | the management commands the daily operation depends on |

There is **no build step**. The front-end is Django templates, plain CSS and vanilla JavaScript.
There is no npm install, no bundler and no CDN. That is a deliberate choice: the kitchen tablet
may have no internet, and a front-end that depends on a CDN is a front-end that breaks in the one
place it matters.

---

## 2. Configuration

Everything that differs between a laptop and a server is an environment variable. Nothing is
edited in a settings file.

| Variable | Default | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | an insecure development key | **must** be set in production |
| `DJANGO_DEBUG` | `True` | set to `False` in production |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,0.0.0.0` | comma-separated |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | comma-separated; needed behind a proxy |
| `POSTGRES_DB` / `_USER` / `_PASSWORD` / `_HOST` / `_PORT` | `messforecast` / `messforecast` / `messforecast_dev_pw` / `127.0.0.1` / `5432` | |
| `POSTGRES_CONN_MAX_AGE` | `60` | seconds; persistent connections |
| `POSTGRES_TEST_DB` | `test_messforecast` | |
| `DJANGO_TIME_ZONE` | `Asia/Kolkata` | the campus is in IST |
| `CELERY_BROKER_URL` | empty | empty means tasks run eagerly, in-process |
| `CELERY_RESULT_BACKEND` | empty | |
| `CELERY_FORECAST_INTERVAL_SECONDS` | `86400` | the daily forecast job |
| `CELERY_GUIDANCE_INTERVAL_SECONDS` | `86400` | the daily kitchen guidance |
| `CELERY_MISSING_ACTUALS_INTERVAL_SECONDS` | `3600` | the missing-actuals reminder |
| `FORECAST_LOOKBACK_WEEKS` | `8` | how many weeks of history the forecaster reads |
| `FORECAST_CONFIDENCE_LEVEL` | `0.80` | the width of the published interval |
| `FORECAST_MIN_OBSERVATIONS` | `6` | below this the forecaster falls back and says so |
| `MEAL_SERVICES` | `BREAKFAST,LUNCH,DINNER` | comma-separated |
| `DJANGO_EMAIL_BACKEND` | the console backend | set to an SMTP backend to send |
| `DEFAULT_FROM_EMAIL` | `mess-forecast@campus.example` | |
| `LOG_LEVEL` | `INFO` | |

`config/settings.py` reads these with a small helper, so a value that is unset falls back to a
default rather than crashing.

---

## 3. Installing

```bash
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt     # Windows
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # Linux
```

Requirements: Django 6.0, Django REST Framework 3.18, psycopg 3.3, Celery 5.6, pandas 3.1,
numpy 2.5, WhiteNoise 6.12, django-filter 26.2.

### The database

```bash
createuser --pwprompt messforecast
createdb --owner messforecast messforecast
```

The application's role needs to own its schema and be able to create tables, but it does **not**
need superuser rights. The PostgreSQL `pg_hba.conf` should use `scram-sha-256` for the
application's connections.

### Migrations and static files

```bash
python manage.py migrate
python manage.py collectstatic
```

`collectstatic` is required in production: WhiteNoise serves `/static/` from `STATIC_ROOT` with
the right cache headers, and the service worker precaches those URLs.

---

## 4. Serving the application

### Development

```bash
python manage.py runserver 8013 --noreload
```

### Production — the simple shape that is enough

```bash
# Gunicorn, 4 workers, bound to a Unix socket
gunicorn config.wsgi:application \
    --bind 127.0.0.1:8000 \
    --workers 4 \
    --timeout 120 \
    --access-logfile -

# Nginx in front
server {
    listen 80;
    server_name mess.example.edu;

    client_max_body_size 5m;

    location /static/ {
        alias /srv/messforecast/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # The service worker must never be cached, or a stale worker keeps
    # serving an old shell to every tablet on the campus.
    location = /sw.js {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        add_header Service-Worker-Allowed "/";
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

`--timeout 120` is deliberate: a 3,000-scan sync batch takes about 5.5 seconds on the write
path, but a slow client on a poor kitchen network can take much longer, and the default 30-second
timeout would cut it off mid-batch.

### Behind a reverse proxy

Set these when a proxy terminates TLS:

```bash
export DJANGO_CSRF_TRUSTED_ORIGINS="https://mess.example.edu"
```

and leave `SECURE_PROXY_SSL_HEADER` as it is — it is already set to
`("HTTP_X_FORWARDED_PROTO", "https")`.

### What `DEBUG=False` turns on

`config/settings.py` enables these automatically when `DEBUG` is off:

| Setting | Value |
|---|---|
| `SECURE_SSL_REDIRECT` | `True` (unless overridden) |
| `SESSION_COOKIE_SECURE` | `True` |
| `CSRF_COOKIE_SECURE` | `True` |
| `SECURE_HSTS_SECONDS` | one year |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `True` |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `True` |
| `X_FRAME_OPTIONS` | `DENY` |

`SECURE_SSL_REDIRECT` defaults to on. If the deployment terminates TLS somewhere this application
cannot see, set `SECURE_SSL_REDIRECT=False` explicitly — otherwise every request redirects to
`https://` and the kitchen tablet on a captive network loops.

---

## 5. The PWA, and the headers that matter

The specification says the service worker is plain JavaScript and is not a Django concern. It is
— `static/pwa/sw.js` has no build step and no Django import — but it does need two headers, and
Django serves them.

`/sw.js` — `apps/core/views.py::service_worker_view`:

```
Cache-Control: no-cache, no-store, must-revalidate
Service-Worker-Allowed: /
Pragma: no-cache
```

`Service-Worker-Allowed: /` is what lets a worker served from `/sw.js` control the whole origin.
Without it the worker would only control `/sw.js/` and the offline behaviour would silently not
work.

`/manifest.webmanifest` — `apps/core/views.py::manifest_view`:

```
Cache-Control: no-cache
Content-Type: application/manifest+json
```

The service worker serves three different caches, and the strategy for each is deliberate:

| Request | Strategy | Why |
|---|---|---|
| Static assets (`/static/...`) | **cache-first** against a versioned cache | assets are versioned by name, so a new version is a new URL |
| Navigations (HTML) | **network-first**, then the cached page, then the offline notice | fresh data wins when there is a connection; the kitchen still works when there is not |
| API reads (`/api/...`) | **network only** | caching an attendance count would be actively misleading |
| API writes | **never intercepted** | the IndexedDB queue owns those — see [10 Offline and sync](10-offline-and-sync.md) |

Verified by `scripts/verify_e2e.py`:

```
service worker       PASS  HTTP 200, cache-control: no-cache, no-store, must-revalidate
service worker scope PASS  /
manifest             PASS  HTTP 200, application/manifest+json
```

---

## 6. Scheduled work with Celery

The specification puts the forecast in a Celery task. There are three:

| Task | Schedule | What it does |
|---|---|---|
| `forecasting.tasks.generate_daily_forecasts` | every 24 h | forecasts the next 7 days for every upcoming service |
| `notifications.tasks.dispatch_preparation_guidance` | every 24 h | sends the preparation brief to the kitchen staff for the day's services |
| `notifications.tasks.flag_missing_actuals` | every hour | reminds whoever recorded an actual yesterday to record today's |

### Without a broker

`CELERY_TASK_ALWAYS_EAGER` is set when no `CELERY_BROKER_URL` is configured, so a task called
from a management command or from the beat schedule **runs immediately in the calling process**.

This is deliberate. It means the laptop and the server behave identically, and it means the
scheduled work can be exercised without installing and running Redis or RabbitMQ. It also means
the *deployment* must run the schedule somehow:

```bash
# Option A — no broker. Run the work from cron.
python manage.py run_forecasts --days 7
python manage.py build_plans --days 2 --publish
```

```cron
17 5 * * *  cd /srv/messforecast && python manage.py run_forecasts --days 7
22 5 * * *  cd /srv/messforecast && python manage.py build_plans --days 2 --publish
```

```bash
# Option B — with a broker. Celery does the scheduling.
export CELERY_BROKER_URL=redis://localhost:6379/0
celery -A config worker -l info
celery -A config beat -l info
```

Both options run the **same code**. `manage.py run_forecasts` and the Celery task call the same
function; the management command is the task with a date range and a console report.

> **One caveat worth stating plainly.** With `CELERY_TASK_ALWAYS_EAGER` on and no broker, the
> daily job has to be driven by something outside the application — cron, a systemd timer, or a
> Windows scheduled task. The application does not schedule itself. This is the one place where
> the "runs identically on a laptop and a server" convenience costs something, and the cost is
> one cron line.

---

## 7. Database

PostgreSQL 18.1 was used for this build. Any PostgreSQL 13 or newer is fine.

### The role

```sql
CREATE ROLE messforecast LOGIN PASSWORD '...';
CREATE DATABASE messforecast OWNER messforecast;
```

The role owns its schema. It does not need superuser rights, and it should not have them.

### What to back up

`pg_dump` covers everything:

```bash
pg_dump -Fc -U messforecast messforecast > messforecast-$(date +%F).dump
```

The data worth restoring most urgently is the **attendance and actuals history** — that is what
the forecaster learns from. Losing it costs a term of data, not just a day's records.

### Indexes

The migrations create indexes on the paths the reporting actually uses: service date and hall,
forecast service, waste by service and dish, attendance by service and client UUID. The reporting
queries are index-backed; none of them is a sequential scan over the whole history.

---

## 8. The seeded demonstration data

For a demo, a pilot, or a UAT session, the seed builds twelve weeks of realistic history:

```bash
python manage.py seed_demo --reset --weeks 12 --baseline-weeks 4
```

It creates two halls, 26 ingredients, 20 dishes, 20 recipes, 3 menu cycles, 7 calendar events,
504 menu schedules, 504 meal services, 336 walk-forward forecasts, 336 preparation plans,
336 indents, 504 actuals, 2,128 waste records and 5,613 individual attendance records — in
**32.5 seconds**.

`--reset` deletes the existing demo data first. **Never run `--reset` against a database that
holds real records.**

The four baseline weeks model the old habit — cooking to registered strength plus 16 %. The
eight live weeks model the new one — cooking to the forecast plus an 8 % margin. That gives
`run_baseline_measurement` something honest to compare.

### The accounts

One account per role, all with the password `messdemo`:

| Username | Role |
|---|---|
| `manager` | Mess Manager |
| `chef` | Kitchen Staff |
| `admin` | Mess Administrator |
| `finance` | Finance Officer |
| `sysadmin` | Administrator |
| `student` | Student |

**Change every one of these before the system sees real data.** They are demonstration accounts
with a published password.

---

## 9. The daily operation

```bash
# Morning: forecast the next 7 days
python manage.py run_forecasts --days 7

# Turn the forecasts into preparation plans and publish them to the kitchen
python manage.py build_plans --days 2 --publish

# Evidence the saving against the pre-deployment baseline
python manage.py run_baseline_measurement \
    --start 2026-08-14 --end 2026-09-10 \
    --live-start 2026-09-11 --live-end 2026-11-05

# Load the student register from the ERP export
python manage.py import_erp students.csv
```

`run_baseline_measurement --json` emits the figures as JSON, so the saving can be piped into the
monthly report without being retyped.

### A note on the `--reset` flag

`seed_demo --reset` is destructive by design and by name. The other four commands are not:
`run_forecasts` and `build_plans` overwrite the rows they own and nothing else, and
`run_baseline_measurement` only reads.

---

## 10. Verifying a deployment

Three scripts, in increasing depth:

```bash
# 1. Does the application answer at all?
python manage.py check --deploy

# 2. Does every route work, for every role?
python scripts/sweep_urls.py

# 3. Does the whole flow work over real HTTP?
python manage.py runserver 8013 --noreload        # in one shell
python scripts/verify_e2e.py http://127.0.0.1:8013
```

`manage.py check --deploy` reports the security settings that `DEBUG=False` should have turned
on. It is worth running on every deployment.

The expected result of the third:

```
23/23 checks passed
```

and of the second:

```
Swept 615 route requests across 5 roles
Status codes: 200x=448, 400x=10, 403x=106, 404x=5, 405x=46
No 5xx responses.
```

---

## 11. Hardware and network, for the kitchen

The specification is blunt about the environment: *"this is a wet, hot environment, not a desk."*

| Consideration | What was designed for |
|---|---|
| Touch targets | 72 px minimum — a gloved fingertip is about 20 mm across and imprecise |
| Text | 20 px minimum, no thin weights, high contrast on a bright screen |
| The save button | 84 px tall and sticky, so it is always under the thumb and cannot be missed |
| Steppers | oversized, for recording portions with cold or wet hands |
| Navigation | the kitchen screen has no back button to get wrong; it does one job |
| Fonts | Bahnschrift, Segoe UI and Consolas — all locally installed, so nothing is fetched at runtime |
| Connectivity | the tablet works with no connection at all; the queue holds the scans |

**Practical advice for the deployment.** A tablet on the mess Wi-Fi will drop out during service
— that is exactly when the kitchen is busiest and the access point is busiest too. The design
assumes that and treats the network as intermittent, not absent. A dedicated access point near
the serving counter, or a tablet with its own SIM, is worth more than any server-side tuning.

---

## 12. Upgrading

```bash
git pull
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart gunicorn
```

The service worker version is `VERSION = 'v1'` at the top of `static/pwa/sw.js`. **Bump it when
you change a precached asset**, or tablets will keep the old one. The `activate` handler deletes
every cache that is not the current shell or page cache, so the old version is cleaned up on the
next load.

---

## 13. Operational checklist

Before the system goes live:

- [ ] `DJANGO_SECRET_KEY` set to a real secret
- [ ] `DJANGO_DEBUG=False`
- [ ] `DJANGO_ALLOWED_HOSTS` set to the real hostnames
- [ ] `DJANGO_CSRF_TRUSTED_ORIGINS` set if behind a proxy
- [ ] PostgreSQL `pg_hba.conf` uses `scram-sha-256` for the application
- [ ] `python manage.py check --deploy` clean
- [ ] Every demonstration password changed
- [ ] `collectstatic` run, and `/static/` served with a long cache lifetime
- [ ] `/sw.js` served with `no-cache, no-store, must-revalidate` and `Service-Worker-Allowed: /`
- [ ] TLS terminated, and `SECURE_SSL_REDIRECT` consistent with how it is terminated
- [ ] A cron line (or Celery beat) driving the daily forecast and plan
- [ ] Nightly `pg_dump` running, and a restore tested
- [ ] The real recipes loaded, and the portion sizes set on `ServiceLevelConfig`
- [ ] The four-week pre-deployment baseline measured with the real kitchen
- [ ] The usability session with actual kitchen staff scheduled — **this is the one that closes
      the specification's last acceptance criterion**
