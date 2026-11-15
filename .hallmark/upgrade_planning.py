"""Upgrade the preparation planning screen to the console shell.

The screen is the same information, ordered the way a manager works it:
upcoming plans first, and only a dozen of them on the page at a time.
"""

import pathlib

PATH = pathlib.Path(r"D:\Haswanth\college\assignments\MessForecast\templates\dashboard\planning.html")

OLD_HEAD = """{% extends "base.html" %}
{% load static %}

{% block title %}Preparation planning \u00b7 {{ app_name }}{% endblock %}

{% block content %}
<div class="pagehead">
  <div>
    <h1>Preparation plans</h1>"""

NEW_HEAD = """{% extends "console/base_console.html" %}
{% load static %}

{% block title %}Preparation planning \u00b7 {{ app_name }}{% endblock %}

{% block console_content %}
{% include "components/page_head.html" with title="Preparation planning" lede="What the kitchen should cook and what it should buy. The portion count comes from the forecast plus the over-preparation margin this hall allows; the ingredient list comes from the recipes behind each dish." %}

<div class="pagehead-side">
  <span class="chip">{{ hall.name|default:"All halls" }}</span>
  <span class="hint">{{ upcoming_count }} upcoming, {{ past_count }} already cooked</span>
</div>
{PLACEHOLDER_HEAD}"""

OLD_FILTERS = """  <div class="toolbar-actions">
    <button class="btn" type="submit">Apply</button>
  </div>
</form>"""

NEW_FILTERS = """  <div class="toolbar-actions">
    <button class="btn" type="submit">Apply</button>
    <a class="btn btn-ghost" href="{% url 'dashboard-planning' %}?when=upcoming{% if hall %}&amp;hall={{ hall.id }}{% endif %}">Upcoming</a>
    <a class="btn btn-ghost" href="{% url 'dashboard-planning' %}?when=past{% if hall %}&amp;hall={{ hall.id }}{% endif %}">Already cooked</a>
  </div>
</form>"""

OLD_TALLY = """      <section class="tally" aria-label="Plan figures">
        <div class="tally-item">
          <span class="tally-label">Expected turnout</span>
          <span class="tally-value">{{ plan.attendance_target|floatformat:0 }}</span>
          <span class="tally-note">the forecast this plan was built from</span>
        </div>
        <div class="tally-item">
          <span class="tally-label">Portions to prepare</span>
          <span class="tally-value">{{ plan.portions_to_prepare }}</span>
          <span class="tally-note">{{ plan.over_preparation_pct|floatformat:1 }}% above the forecast</span>
        </div>
        <div class="tally-item">
          <span class="tally-label">Over-preparation</span>
          <span class="tally-value">{{ plan.over_preparation_pct|floatformat:1 }}%</span>
          <span class="tally-note">the margin this hall allows</span>
        </div>
        <div class="tally-item">
          <span class="tally-label">Estimated food cost</span>
          <span class="tally-value">\u20b9{{ plan.estimated_cost|floatformat:0 }}</span>
          <span class="tally-note">at current ingredient prices</span>
        </div>
      </section>"""

NEW_TALLY = """      <div class="c-figrow">
        <div class="c-fig">
          <span class="c-fig-label">Expected turnout</span>
          <span class="c-fig-value">{{ plan.attendance_target|floatformat:0 }}</span>
          <span class="c-fig-note">The forecast this plan was built from</span>
        </div>
        <div class="c-fig">
          <span class="c-fig-label">Portions to prepare</span>
          <span class="c-fig-value">{{ plan.portions_to_prepare }}</span>
          <span class="c-fig-note">{{ plan.over_preparation_pct|floatformat:1 }}% above the forecast</span>
        </div>
        <div class="c-fig">
          <span class="c-fig-label">Over-preparation</span>
          <span class="c-fig-value is-loss">{{ plan.over_preparation_pct|floatformat:1 }}%</span>
          <span class="c-fig-note">The margin this hall allows</span>
        </div>
        <div class="c-fig">
          <span class="c-fig-label">Estimated food cost</span>
          <span class="c-fig-value">\u20b9{{ plan.estimated_cost|floatformat:0 }}</span>
          <span class="c-fig-note">At current ingredient prices</span>
        </div>
      </div>"""


def main() -> int:
    source = PATH.read_text(encoding="utf-8")

    if OLD_HEAD in source:
        source = source.replace(OLD_HEAD, NEW_HEAD, 1)
        # Drop the rest of the old pagehead block, which ran to the toolbar.
        start = source.find("{PLACEHOLDER_HEAD}")
        end = source.find('<form class="toolbar" method="get">', start)
        if start != -1 and end != -1:
            source = source[:start] + source[end:]
    else:
        print("head block not found")

    source = source.replace(OLD_FILTERS, NEW_FILTERS, 1)
    source = source.replace(OLD_TALLY, NEW_TALLY, 1)

    PATH.write_text(source, encoding="utf-8")
    print("planning.html upgraded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
