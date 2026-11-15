"""Point the remaining templates at the new kitchen route names."""

import pathlib

ROOT = pathlib.Path(r"D:\Haswanth\college\assignments\MessForecast\templates")
TARGETS = ["base.html", "landing/index.html", "dashboard/waste.html", "dashboard/home.html"]

OLD_URL = "{% url 'kitchen-screen' %}"
NEW_URL = "{% url 'kitchen-dashboard' %}"
OLD_NAME = "request.resolver_match.url_name == 'kitchen-screen'"
NEW_NAME = "request.resolver_match.url_name == 'kitchen-dashboard'"


def main() -> int:
    for name in TARGETS:
        path = ROOT / name
        source = path.read_text(encoding="utf-8")
        fixed = source.replace(OLD_URL, NEW_URL).replace(OLD_NAME, NEW_NAME)
        if fixed != source:
            path.write_text(fixed, encoding="utf-8")
            print("updated", name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
