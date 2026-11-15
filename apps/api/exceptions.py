"""API error handling.

One rule: a client mistake must come back as a 4xx, never as a 500.

The case that matters here is deletion. The schema protects the rows that
carry history - a dish that has been cooked, a menu that has been served -
so Django raises ``ProtectedError`` rather than silently orphaning the
records. Left alone that reaches the client as a 500, which reads as "the
server is broken" when in fact the server is telling the truth.

So the error is translated into a 409 that says what is still holding the
row, and what to do about it.
"""

from __future__ import annotations

from django.db.models.deletion import ProtectedError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def _describe(exc: ProtectedError) -> str:
    """Name the things that are holding the row, without the object dump.

    ``ProtectedError.protected_objects`` is every related row. A dish that has
    been cooked for twelve weeks has hundreds of them, so they are counted by
    the model that owns them.
    """
    counts: dict[str, int] = {}
    for obj in exc.protected_objects:
        label = obj._meta.verbose_name
        counts[label] = counts.get(label, 0) + 1

    if not counts:
        return "It is still referenced by other records."

    parts = [
        f"{count} {label}{'s' if count != 1 else ''}"
        for label, count in sorted(counts.items(), key=lambda kv: -kv[1])
    ]
    listed = ", ".join(parts)
    return f"It is still used by {listed}."


def api_exception_handler(exc, context):
    """Translate the errors the client can act on."""
    if isinstance(exc, ProtectedError):
        return Response(
            {
                "detail": (
                    "That cannot be deleted. "
                    + _describe(exc)
                    + " Retire it instead, which keeps the history and takes it "
                    "off the menus."
                )
            },
            status=status.HTTP_409_CONFLICT,
        )
    return drf_exception_handler(exc, context)
