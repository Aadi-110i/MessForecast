"""Capture real API response shapes for the API reference document.

Signs in over HTTP, requests each endpoint, and prints the JSON with the
dynamic values trimmed, so the documentation quotes what the server actually
returns rather than what the code was expected to return.

    python scripts/sample_api.py http://127.0.0.1:8013
"""

from __future__ import annotations

import http.cookiejar
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8013").rstrip("/")
USERNAME = "manager"
PASSWORD = "messdemo"

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

TARGETS = [
    "/api/services/?limit=1",
    "/api/forecasts/?limit=1",
    "/api/preparation-plans/?limit=1",
    "/api/actuals/?limit=1",
    "/api/menus/?limit=1",
    "/api/menu-schedules/?limit=1",
    "/api/attendance/?limit=1",
    "/api/ingredients/?limit=1",
    "/api/dishes/?limit=1",
    "/api/events/?limit=1",
    "/api/service-levels/?limit=1",
    "/api/indents/?limit=1",
    "/api/waste/?limit=1",
    "/api/notifications/?limit=1",
    "/api/analytics/waste",
    "/api/analytics/accuracy",
    "/api/analytics/demand",
    "/api/analytics/ingredients",
]


def get(path: str):
    request = urllib.request.Request(BASE + path, headers={"User-Agent": "sample/1.0"})
    try:
        with opener.open(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def sign_in() -> None:
    get("/accounts/login/")
    form = urllib.parse.urlencode(
        {
            "username": USERNAME,
            "password": PASSWORD,
            "csrfmiddlewaretoken": next(
                (c.value for c in jar if c.name == "csrftoken"), ""
            ),
            "next": "/dashboard/",
        }
    ).encode()
    request = urllib.request.Request(
        BASE + "/accounts/login/",
        data=form,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": BASE + "/accounts/login/",
        },
        method="POST",
    )
    with opener.open(request, timeout=30) as response:
        response.read()


def shape(value, depth: int = 0):
    """Trim a JSON document so the structure is visible but the data is not."""
    if depth > 4:
        return "..."
    if isinstance(value, dict):
        return {key: shape(item, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        if not value:
            return []
        return [shape(value[0], depth + 1)]
    return value


def main() -> int:
    sign_in()
    for path in TARGETS:
        status, body = get(path)
        print("=" * 78)
        print(f"GET {path}  ->  HTTP {status}")
        if status != 200:
            print(body[:600])
            continue
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            print(body[:600])
            continue
        print(json.dumps(shape(data), indent=2)[:2600])
    return 0


if __name__ == "__main__":
    sys.exit(main())
