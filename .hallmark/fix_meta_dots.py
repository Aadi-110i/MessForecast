"""Fix the two middle-dot-joined meta strings and the inline spacing styles.

The Floor forbids a middle dot joining metadata, so a row that reads
"date, hall, meal" is the shape. The catalogue's inline spacing becomes a
class, so no screen carries a raw style declaration.
"""

import pathlib

ROOT = pathlib.Path(r"D:\Haswanth\college\assignments\MessForecast\templates")

EDITS = [
    (
        ROOT / "console" / "forecast.html",
        '{{ r.service.date|date:"D d M" }} \u00b7 {{ r.service.hall.code }} \u00b7 {{ r.service.get_meal_display }}',
        '{{ r.service.date|date:"D d M" }}, {{ r.service.hall.code }}, {{ r.service.get_meal_display }}',
    ),
    (
        ROOT / "console" / "settings.html",
        '{{ c.hall.code|default:"All halls" }} \u00b7 {{ c.meal|default:"All meals"|title }}',
        '{{ c.hall.code|default:"All halls" }}, {{ c.meal|default:"All meals"|title }}',
    ),
    (
        ROOT / "design_system" / "index.html",
        '<div class="k-day" style="margin-top: var(--space-lg);">',
        '<div class="k-day c-spaced">',
    ),
    (
        ROOT / "design_system" / "index.html",
        '<div class="k-services" style="margin-top: var(--space-lg);">',
        '<div class="k-services c-spaced">',
    ),
]


def main() -> int:
    for path, old, new in EDITS:
        source = path.read_text(encoding="utf-8")
        if old not in source:
            print("not found in", path.name, "->", old[:60])
            continue
        path.write_text(source.replace(old, new), encoding="utf-8")
        print("fixed", path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
