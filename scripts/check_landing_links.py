"""Check every link on the landing page and the root actually resolves."""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from django.test import Client
from django.urls import resolve, NoReverseMatch

client = Client(HTTP_HOST="127.0.0.1")
HREF = re.compile(r'href="([^"#]+)"')

for path in ("/", "/landing/"):
    response = client.get(path)
    body = response.content.decode("utf-8")
    print(f"--- {path} -> {response.status_code} ---")
    for href in sorted(set(HREF.findall(body))):
        if href.startswith(("http", "mailto:", "tel:", "javascript:", "/static/", "/media:", "data:")):
            continue
        # A query string is not part of the route.
        path = href.split("?", 1)[0]
        try:
            match = resolve(path)
            print(f"  ok    {href} -> {match.view_name}")
        except NoReverseMatch:
            print(f"  BROKEN (no such route) {href}")
        except Exception as exc:
            print(f"  BROKEN {href}: {type(exc).__name__}: {exc}")
