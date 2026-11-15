"""End-to-end verification against a running server.

Runs the real HTTP surface — login, the dashboard pages, the kitchen and
capture screens, the REST API and the offline sync endpoint — and reports
what actually came back.

Usage::

    python manage.py runserver 8011
    python scripts/verify_e2e.py http://127.0.0.1:8011
"""

from __future__ import annotations

import http.cookiejar
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8011").rstrip("/")
USERNAME = "manager"
PASSWORD = "messdemo"

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

results: list[tuple[str, str, str]] = []


def record(label: str, ok: bool, detail: str = "") -> None:
    results.append((label, "PASS" if ok else "FAIL", detail))


def csrf() -> str:
    for cookie in jar:
        if cookie.name == "csrftoken":
            return cookie.value
    return ""


def get(path: str):
    request = urllib.request.Request(BASE + path, headers={"User-Agent": "verify/1.0"})
    try:
        with opener.open(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", "replace"), response.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace"), exc.headers


def post(path: str, payload: dict, referer: str | None = None):
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf(),
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "verify/1.0",
    }
    if referer:
        headers["Referer"] = BASE + referer
    request = urllib.request.Request(BASE + path, data=body, headers=headers, method="POST")
    try:
        with opener.open(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def page(label: str, path: str, must_contain: list[str]) -> None:
    status, body, _headers = get(path)
    missing = [needle for needle in must_contain if needle not in body]
    if status == 200 and not missing:
        record(label, True, f"HTTP {status}, {len(body)} bytes")
    else:
        record(
            label,
            False,
            f"HTTP {status}" + (f", missing: {missing}" if missing else ""),
        )


def api(label: str, path: str, checks: list[str] | None = None) -> None:
    status, body, _headers = get(path)
    if status != 200:
        record(label, False, f"HTTP {status}")
        return
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        record(label, False, "response was not JSON")
        return
    missing = [needle for needle in (checks or []) if needle not in body]
    record(label, not missing, f"HTTP {status}" + (f", missing {missing}" if missing else ""))


def main() -> int:
    print(f"Verifying {BASE}\n" + "=" * 72)

    # --- sign in --------------------------------------------------------
    status, body, _ = get("/accounts/login/")
    record(
        "login page",
        status == 200 and "csrfmiddlewaretoken" in body,
        f"HTTP {status}",
    )

    form = urllib.parse.urlencode(
        {"username": USERNAME, "password": PASSWORD, "csrfmiddlewaretoken": csrf(), "next": "/"}
    ).encode()
    request = urllib.request.Request(
        BASE + "/accounts/login/",
        data=form,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": BASE + "/accounts/login/",
            "User-Agent": "verify/1.0",
        },
        method="POST",
    )
    try:
        with opener.open(request, timeout=30) as response:
            signed_in = response.status == 200 and "MessForecast" in response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        signed_in = False
        print("login failed:", exc.code)
    record("sign in as manager", signed_in)

    if not signed_in:
        print("Cannot continue without a session.")
        return 1

    # --- the HTML surfaces ----------------------------------------------
    page("dashboard: overview", "/", ["Waste and forecast overview", "tally", "chart", "Reconciled"])
    page("dashboard: waste", "/dashboard/waste/", ["Waste report", "Total cost of waste"])
    page("dashboard: accuracy", "/dashboard/accuracy/", ["Forecast accuracy", "MAPE"])
    page("dashboard: planning", "/dashboard/planning/", ["Preparation plans"])
    page("dashboard: data quality", "/dashboard/data-quality/", ["Data quality", "Actuals completion"])
    page("kitchen screen", "/kitchen/", ["MessForecast", "Kitchen"])
    page("capture screen", "/scan/", ["Attendance capture", "Turned up"])

    # --- the PWA bootstrap ----------------------------------------------
    status, body, headers = get("/sw.js")
    record(
        "service worker",
        status == 200 and "addEventListener" in body
        and "no-cache" in headers.get("Cache-Control", ""),
        f"HTTP {status}, cache-control: {headers.get('Cache-Control', '?')}",
    )
    record(
        "service worker scope header",
        headers.get("Service-Worker-Allowed") == "/",
        headers.get("Service-Worker-Allowed", "missing"),
    )
    status, body, headers = get("/manifest.webmanifest")
    record(
        "manifest",
        status == 200 and "MessForecast" in body
        and headers.get("Content-Type", "").startswith("application/manifest"),
        f"HTTP {status}, {headers.get('Content-Type', '?')}",
    )

    # --- the REST API ----------------------------------------------------
    api("api: services", "/api/services/", ["attendance_count", "registered_strength"])
    api("api: forecasts", "/api/forecasts/", ["predicted_attendance", "explanation", "input_signature"])
    api("api: preparation plans", "/api/preparation-plans/", ["portions_to_prepare", "guidance_text"])
    api("api: actuals", "/api/actuals/", ["prepared_portions_total", "prep_mode"])
    api("api: menus", "/api/menus/", ["items"])
    api("api: waste analytics", "/api/analytics/waste", ["totals", "by_week", "top_dishes"])
    api("api: accuracy analytics", "/api/analytics/accuracy", ["summary", "exact_mape_pct", "over_time"])
    api("api: demand analytics", "/api/analytics/demand", ["by_weekday", "by_period"])
    api("api: ingredients", "/api/analytics/ingredients", ["rows"])

    # --- offline sync, over HTTP, twice ----------------------------------
    status, body, _headers = get("/api/services/?limit=1")
    service = json.loads(body)["results"][0] if json.loads(body).get("results") else None
    if service is None:
        record("offline sync", False, "no service to scan against")
    else:
        client_uuid = str(uuid.uuid4())
        payload = {
            "records": [
                {
                    "client_uuid": client_uuid,
                    "service_id": service["id"],
                    "hall_id": service["hall"],
                    "date": service["date"],
                    "meal": service["meal"],
                    "student_identifier": "E2E-VERIFY-0001",
                    "method": "QR",
                    "captured_offline": True,
                    "device_id": "verify-tablet",
                }
            ],
            "device_id": "verify-tablet",
        }
        first_status, first_body = post("/api/attendance/sync", payload, referer="/scan/")
        first = json.loads(first_body) if first_status == 200 else {}
        second_status, second_body = post("/api/attendance/sync", payload, referer="/scan/")
        second = json.loads(second_body) if second_status == 200 else {}

        record(
            "offline sync: first send creates the record",
            first.get("created") == 1,
            f"HTTP {first_status}, created={first.get('created')}",
        )
        record(
            "offline sync: re-send is ignored (idempotent)",
            second.get("created") == 0 and second.get("duplicates") == 1,
            f"HTTP {second_status}, created={second.get('created')}, "
            f"duplicates={second.get('duplicates')}",
        )

    # --- report ----------------------------------------------------------
    print()
    width = max(len(row[0]) for row in results)
    failures = 0
    for label, status, detail in results:
        if status != "PASS":
            failures += 1
        print(f"  {label:<{width}}  {status}  {detail}")

    print()
    print("=" * 72)
    print(f"{len(results) - failures}/{len(results)} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
