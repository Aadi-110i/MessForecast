"""Sweep every registered route and report any 5xx.

The HTML dashboard is easy to break in one place and miss in another: a view
that calls a helper on the wrong service module raises ``AttributeError`` at
request time and returns a 500. This script walks the whole URL tree, signs in
as each role, requests every GET route it can build, and prints the full
traceback for anything that fails.

URLs are produced with ``reverse()`` so the sweep always matches the routes
Django actually serves, including the DRF router's own patterns, and real
primary keys are used so the detail routes render actual data instead of
404-ing straight away.

Run it against the seeded database::

    python scripts/sweep_urls.py
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.test import Client  # noqa: E402
from django.urls import (  # noqa: E402
    URLPattern,
    URLResolver,
    get_resolver,
    reverse,
)

from apps.actuals.models import DishActual, ServiceActual  # noqa: E402
from apps.attendance.models import AttendanceRecord, MealService  # noqa: E402
from apps.catalog.models import (  # noqa: E402
    CostRate,
    DiningHall,
    Dish,
    Ingredient,
    Recipe,
)
from apps.events.models import CalendarEvent, ServiceLevelConfig  # noqa: E402
from apps.forecasting.models import Forecast  # noqa: E402
from apps.menu.models import Menu, MenuItem, MenuSchedule  # noqa: E402
from apps.notifications.models import Notification  # noqa: E402
from apps.planning.models import IngredientIndent, PreparationPlan  # noqa: E402
from apps.waste.models import WasteRecord  # noqa: E402

ROLES = [
    ("manager", "messdemo"),
    ("chef", "messdemo"),
    ("admin", "messdemo"),
    ("finance", "messdemo"),
    ("student", "messdemo"),
]

# The Django admin is a large surface of its own; it is covered by the
# functional tests, not by this sweep.
SKIP_PREFIXES = ("/admin/",)


def _latest(model):
    """The most recent row of a model, or None when the table is empty."""
    return model.objects.order_by("-pk").first()


def _sample_ids() -> dict[str, int]:
    """Real primary keys, keyed by the DRF router basename."""
    models = {
        "hall": DiningHall,
        "ingredient": Ingredient,
        "dish": Dish,
        "recipe": Recipe,
        "costrate": CostRate,
        "menu": Menu,
        "menuitem": MenuItem,
        "menuschedule": MenuSchedule,
        "mealservice": MealService,
        "attendance": AttendanceRecord,
        "event": CalendarEvent,
        "servicelevel": ServiceLevelConfig,
        "forecast": Forecast,
        "preparationplan": PreparationPlan,
        "indent": IngredientIndent,
        "actual": ServiceActual,
        "dishactual": DishActual,
        "waste": WasteRecord,
        "notification": Notification,
    }
    ids: dict[str, int] = {}
    for basename, model in models.items():
        row = _latest(model)
        if row is not None:
            ids[basename] = row.pk
    return ids


def _walk(resolver, prefix: str = "", namespace: str = "") -> list[tuple[str, object]]:
    """Return (url_name, pattern) for every concrete pattern in the tree."""
    found: list[tuple[str, object]] = []
    for entry in resolver.url_patterns:
        if isinstance(entry, URLResolver):
            child_ns = namespace
            if entry.namespace:
                child_ns = f"{namespace}:{entry.namespace}" if namespace else entry.namespace
            found.extend(_walk(entry, prefix, child_ns))
        elif isinstance(entry, URLPattern):
            name = entry.name
            if namespace and name:
                name = f"{namespace}:{name}"
            found.append((name, entry.pattern))
    return found


def _required_kwargs(pattern) -> list[str]:
    """Names of the URL parameters a pattern needs, ignoring the format suffix."""
    converters = getattr(pattern, "converters", None)
    if converters:
        names = list(converters)
    else:
        regex = getattr(pattern, "regex", None)
        names = list(regex.groupindex) if regex is not None and hasattr(regex, "groupindex") else []
    # DRF's router adds a "format" group for the .json style suffix; it is
    # optional and is not something we want to sweep.
    return [name for name in names if name != "format"]


def _kwargs_for(name: str, pattern, ids: dict[str, int]) -> dict[str, int] | None:
    """Build the kwargs reverse() needs, using a real id for the resource."""
    required = _required_kwargs(pattern)
    if not required:
        return {}
    if len(required) != 1:
        return None  # e.g. password_reset_confirm needs uid+token
    key = required[0]
    if key == "pk":
        # The router basename is the longest known basename the route name
        # starts with ("preparationplan-indent-csv" -> "preparationplan").
        for basename in sorted(ids, key=len, reverse=True):
            if name.startswith(basename):
                return {"pk": ids[basename]}
        return None
    if key in ("plan_id", "service_id"):
        # Each keyword names its own model: a preparation plan is not a meal
        # service, so handing a plan id to /kitchen/guidance/<service_id> only
        # proves the route 404s.
        candidate = {"plan_id": "preparationplan", "service_id": "mealservice"}[key]
        if candidate in ids:
            return {key: ids[candidate]}
    return None


# Routes that only accept POST, with a body each one can accept.
POST_TARGETS = {
    "forecast-generate": {},
    "forecast-refresh": {},
    "preparationplan-generate": {"service": "mealservice"},
    "actual-recompute-waste": {},
    "attendance-sync": {"records": [], "device_id": "sweep"},
    "attendance-count": {"service": "mealservice"},
}


def main() -> int:
    ids = _sample_ids()
    routes = _walk(get_resolver())
    route_by_name = {name: pattern for name, pattern in routes}

    failures: list[tuple[str, str, str]] = []
    statuses: dict[int, int] = {}
    checked = 0
    unresolved: list[str] = []

    for username, password in ROLES:
        # The default "testserver" host is not in ALLOWED_HOSTS, so every
        # request would be rejected with a 400 and the sweep would pass vacuously.
        client = Client(headers={"host": "127.0.0.1"})
        client.login(username=username, password=password)

        for name, pattern in routes:
            if not name or name.startswith("admin:"):
                continue
            kwargs = _kwargs_for(name, pattern, ids)
            if kwargs is None:
                unresolved.append(name)
                continue
            try:
                path = reverse(name, kwargs=kwargs or None)
            except Exception:
                unresolved.append(name)
                continue
            if path.startswith(SKIP_PREFIXES):
                continue

            checked += 1
            try:
                response = client.get(path)
            except Exception:
                failures.append((username, path, traceback.format_exc()))
                continue
            statuses[response.status_code] = statuses.get(response.status_code, 0) + 1
            if response.status_code >= 500:
                failures.append(
                    (username, path, f"HTTP {response.status_code}\n{_traceback_from(response)}")
                )

    # --- the routes that only answer POST -------------------------------
    for username, password in ROLES:
        client = Client(headers={"host": "127.0.0.1"})
        client.login(username=username, password=password)

        for name, template in POST_TARGETS.items():
            pattern = route_by_name.get(name)
            if pattern is None:
                unresolved.append(name)
                continue
            kwargs = _kwargs_for(name, pattern, ids)
            if kwargs is None:
                continue
            try:
                path = reverse(name, kwargs=kwargs or None)
            except Exception:
                unresolved.append(name)
                continue

            body = {}
            for key, value in template.items():
                # A string value names a key in the sample-id table; anything
                # else is a literal body fragment.
                body[key] = ids.get(value, value) if isinstance(value, str) else value

            checked += 1
            try:
                response = client.post(path, data=json.dumps(body), content_type="application/json")
            except Exception:
                failures.append((username, f"POST {path}", traceback.format_exc()))
                continue
            statuses[response.status_code] = statuses.get(response.status_code, 0) + 1
            if response.status_code >= 500:
                failures.append(
                    (username, f"POST {path}", f"HTTP {response.status_code}\n{_traceback_from(response)}")
                )

    print(f"Swept {checked} route requests across {len(ROLES)} roles")
    print("Status codes: " + ", ".join(f"{code}x={count}" for code, count in sorted(statuses.items())))
    if unresolved:
        unique = sorted(set(unresolved))
        print(f"Skipped {len(unresolved)} route requests ({len(unique)} distinct):")
        print("    " + ", ".join(unique))
    print("=" * 72)

    if not failures:
        print("No 5xx responses.")
        return 0

    for username, path, detail in failures:
        print(f"\n--- {username}  GET {path} ---")
        print(detail[-4000:])
    print(f"\n{len(failures)} failing route(s).")
    return 1


def _traceback_from(response) -> str:
    """Pull the traceback out of Django's debug page when there is one."""
    import html
    import re

    try:
        body = response.content.decode("utf-8", "replace")
    except Exception:  # pragma: no cover - defensive
        return "(no body)"
    match = re.search(r'<div id="traceback">(.*?)</div>\s*</div>', body, re.S)
    if not match:
        return "(no traceback in body)"
    text = html.unescape(re.sub(r"<[^>]+>", "", match.group(1)))
    return text.strip()


if __name__ == "__main__":
    sys.exit(main())
