"""Template tags for capability-aware navigation and controls.

Usage::

    {% load capabilities %}

    {% if user|can:"VIEW_MENU" %}
      ...
    {% endif %}

Every check reads the single capability table in
``apps.accounts.permissions`` so the frontend never drifts from the backend.
"""

from django import template

from apps.accounts.permissions import has_capability

register = template.Library()


@register.filter(name="can")
def can(user, capability: str) -> bool:
    """True when ``user`` holds ``capability``."""
    return has_capability(user, capability)


@register.simple_tag
def user_capabilities(user) -> set:
    """The set of capabilities the authenticated user holds."""
    from apps.accounts.permissions import CAPABILITIES

    if user is None or not getattr(user, "is_authenticated", False):
        return set()
    return CAPABILITIES.get(user.role, set())
