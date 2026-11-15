import http.cookiejar
import os
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8414"

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def get(path):
    return opener.open(f"{BASE}{path}", timeout=15).read().decode()


def post(path, data):
    body = urllib.parse.urlencode(data).encode()
    token = next((c.value for c in jar if c.name == "csrftoken"), "")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=body,
        headers={
            "Referer": f"{BASE}{path}",
            "X-CSRFToken": token,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    return opener.open(req, timeout=15).read().decode()


get("/accounts/login/")
post("/accounts/login/", {"username": "sysadmin", "password": "messdemo", "csrfmiddlewaretoken": ""})
print("signed in")

CHECKS = [
    ("/console/dishes/", "What the kitchen can cook"),
    ("/console/menus/", "Create a weekly menu"),
    ("/console/menus/", "Create a daily menu"),
    ("/console/settings/", "Effect on demand"),
    ("/console/recipes/", "Recipes"),
    ("/dashboard/", "Overview"),
]

for path, needle in CHECKS:
    body = get(path)
    ok = needle.lower() in body.lower()
    print(f"  200  {path:22} contains {needle!r}: {'yes' if ok else 'NO'}")
