"""Template filters shared by the console screens."""

from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Read a named field out of whatever the row happens to be.

    The table and field components take their columns as data, so they need
    to read a field from each row without a template per table. A row may
    be a dict, a model instance, or a plain tuple of choices, so all three
    are handled.
    """
    if dictionary is None:
        return ""

    if hasattr(dictionary, "get"):
        try:
            return dictionary.get(key, "")
        except (TypeError, AttributeError):
            pass

    if isinstance(key, str) and key.lstrip("-").isdigit():
        key = int(key)

    if isinstance(key, int):
        try:
            return dictionary[key]
        except (TypeError, KeyError, IndexError):
            pass
    else:
        try:
            return dictionary[key]
        except (TypeError, KeyError, IndexError):
            pass

    return getattr(dictionary, str(key), "")


@register.filter
def pct(value, digits=1):
    """Format a number as a percentage, tolerating None and strings."""
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


@register.filter
def compact_number(value):
    """Format a number compactly: 1,240 becomes 1.2k."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if abs(number) >= 100000:
        return f"{number / 100000:.1f}L"
    if abs(number) >= 1000:
        return f"{number / 1000:.1f}k"
    return f"{number:.0f}"


@register.filter
def split_money(value):
    """Split a rupee amount into its integer and fractional parts.

    The kitchen tablet sets the cost large and the paise small, so the two
    need to be separate nodes rather than one string.
    """
    try:
        text = f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "0", "00"
    whole, _, fraction = text.partition(".")
    return whole, fraction


@register.filter
def as_list(value):
    """Wrap one value so a component that prints a list can take it.

    The field component joins its errors with commas, and joining a string
    would print it one character at a time. A view holds one message per
    field, so the single message is wrapped here.
    """
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]
