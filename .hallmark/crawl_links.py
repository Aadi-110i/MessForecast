"""Walk every page a role can reach and check every link on it.

The rail is guarded, but a page can also link to another surface - the
dashboard links to the waste report, the kitchen links to the indent. A link
that answers 403 for the person clicking it is a broken promise, and this
finds them all.
"""

import os
import re
import sys

sys.path.insert(0, r"D:\Haswanth\college\assignments\MessForecast")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from django.test import Client
from django.urls import get_resolver

from apps.accounts.models import User

RESOLVER = get_resolver()
HREF = re.compile(r'href="([^"#]+)"')

SKIP_PREFIX = ("http", "mailto:", "tel:", "javascript:", "/static/", "/media/", "data:")

def internal_paths():
    """Every path the URL configuration can serve."""
    seen = set()
    for pattern in RESOLVER.url_patterns:
        try:
            matcher = pattern.resolve("")
        except Exception:
            continue
        if not matcher:
            continue
        route = getattr(pattern, "_route", None)
        if route and "<" not in route and "{" not in route:
            seen.add("/" + route)
    return sorted(seen)


ROLES = [
    ("STUDENT", "crawl_student"),
    ("KITCHEN STAFF", "crawl_kitchen"),
    ("FINANCE", "crawl_finance"),
    ("MESS MANAGER", "crawl_manager"),
    ("MESS ADMIN", "crawl_messadmin"),
    ("ADMIN", "crawl_admin"),
]

from apps.accounts.models import User as U

ROLE_BY_NAME = {
    "STUDENT": U.Role.STUDENT,
    "KITCHEN STAFF": U.Role.KITCHEN_STAFF,
    "FINANCE": U.Role.FINANCE_OFFICER,
    "MESS MANAGER": U.Role.MESS_MANAGER,
    "MESS ADMIN": U.Role.MESS_ADMIN,
    "ADMIN": U.Role.ADMINISTRATOR,
}

total_broken = 0
for label, username in ROLES:
    u, _ = User.objects.get_or_create(
        username=username, defaults={"role": ROLE_BY_NAME[label]}
    )
    u.role = ROLE_BY_NAME[label]
    u.set_password("pass12345")
    u.save()

    c = Client()
    c.force_login(u)

    # Start at the role's own landing page.
    landing = c.get("/dashboard/")
    if landing.status_code == 302:
        landing = c.get(landing["Location"])

    pages = {"/dashboard/", landing.request.get("PATH_INFO", "")}
    queue = [(landing.request.get("PATH_INFO", ""), "/dashboard/")]
    seen = set(queue[0][0])
    source = {}
    while queue:
        path, came_from = queue.pop(0)
        try:
            r = c.get(path)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        if not hasattr(r, "content"):
            continue  # a file download, not a page
        for href in HREF.findall(r.content.decode()):
            if href.startswith(SKIP_PREFIX):
                continue
            if not href.startswith("/") or "/" not in href[1:]:
                continue  # not a path into this application
            clean = href.split("?")[0]
            if clean in seen:
                continue
            seen.add(clean)
            source[clean] = path
            queue.append((clean, path))

    broken = []
    for path in sorted(seen):
        if not path.startswith("/"):
            continue  # not a path into this application
        try:
            r = c.get(path)
        except Exception as exc:
            broken.append((path, type(exc).__name__))
            continue
        if r.status_code == 403:
            broken.append((path, "403"))
        elif r.status_code == 404:
            broken.append((path, "404"))

    print(f"\n=== {label} === reached {len(seen)} links, {len(broken)} broken")
    for path, why in broken:
        print(f"    BROKEN  {path}  -> {why}   (linked from {source.get(path, '?')})")
    total_broken += len(broken)

print(f"\n{total_broken} broken links in total")
