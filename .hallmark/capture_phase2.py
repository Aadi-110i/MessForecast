"""Capture every Phase 2 screen at the three widths that matter.

The capture tier of the sweep uses the browser; this does the same job for
the screens the console introduces, so the deliverable has a picture of
every screen in the system rather than of the landing page alone.

Console screens are 1440 wide, which is the width a manager reads at. The
kitchen tablet is captured at 1024, the size of the wall-mounted screen in
the kitchen, because that is the width its layout is designed for.
"""

from __future__ import annotations

import pathlib
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8412"
OUT = pathlib.Path(r"D:\Haswanth\college\assignments\MessForecast\.hallmark\phase2")

CONSOLE_SCREENS = [
    ("login", "/accounts/login/", 1440, 900),
    ("register", "/accounts/register/", 1440, 900),
    ("admin-dashboard", "/dashboard/", 1440, 900),
    ("forecast-dashboard", "/console/forecast/", 1440, 900),
    ("attendance", "/console/attendance/", 1440, 900),
    ("menu-management", "/console/menus/", 1440, 900),
    ("menu-cycle-detail", "/console/menus/46/", 1440, 900),
    ("recipe-management", "/console/recipes/", 1440, 900),
    ("recipe-detail", "/console/recipes/311/", 1440, 900),
    ("preparation-planning", "/dashboard/planning/", 1440, 900),
    ("waste-analytics", "/dashboard/waste/", 1440, 900),
    ("reports", "/console/reports/", 1440, 900),
    ("settings", "/console/settings/", 1440, 900),
    ("registration-codes", "/accounts/codes/", 1440, 900),
    ("component-library", "/console/design-system/", 1440, 900),
    ("data-quality", "/dashboard/data-quality/", 1440, 900),
]

TABLET_SCREENS = [
    ("kitchen-dashboard", "/kitchen/", 1024, 768),
    ("kitchen-actuals", "/kitchen/actuals/5132/", 1024, 768),
    ("capture", "/scan/", 1024, 768),
]

NARROW_SCREENS = [
    ("admin-dashboard-narrow", "/dashboard/", 390, 844),
    ("forecast-narrow", "/console/forecast/", 390, 844),
    ("kitchen-dashboard-narrow", "/kitchen/", 768, 1024),
]


def sign_in(page) -> None:
    page.goto(f"{BASE}/accounts/login/", wait_until="networkidle")
    page.fill("#id_username", "sysadmin")
    page.fill("#id_password", "messdemo")
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")


def capture(page, name: str, path: str, width: int, height: int, full: bool) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{BASE}{path}", wait_until="networkidle")
    page.wait_for_timeout(600)
    target = OUT / f"{name}.png"
    page.screenshot(path=str(target), full_page=full)
    print(f"  {name:<28} {width}x{height} {'full' if full else 'fold'}")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(device_scale_factor=1)
        page = context.new_page()

        print("capturing the console:")
        sign_in(page)
        for name, path, width, height in CONSOLE_SCREENS:
            capture(page, name, path, width, height, full=False)
        for name, path, width, height in CONSOLE_SCREENS[:6]:
            capture(page, f"{name}-full", path, width, height, full=True)

        print("capturing the tablet:")
        for name, path, width, height in TABLET_SCREENS:
            capture(page, name, path, width, height, full=False)

        print("capturing narrow:")
        for name, path, width, height in NARROW_SCREENS:
            capture(page, name, path, width, height, full=False)

        browser.close()
    print(f"done, {len(list(OUT.glob('*.png')))} images in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
