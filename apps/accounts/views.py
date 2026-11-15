"""Sign in and registration.

Registration is by code. The mess office issues a code to the person who
will use the account, and the code carries the role. That keeps a student
from registering themselves as an administrator, and it means the platform
knows who vouched for an account before it was created.
"""

from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.contrib.auth import login, password_validation, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import User, PasswordResetToken
from apps.accounts.permissions import has_capability
from apps.accounts.registration import RegistrationCode


@login_required
@require_GET
def registration_console(request):
    """Issue and revoke registration codes.

    Only the roles that manage people may issue them. The rule is the
    ``MANAGE_USERS`` capability, so the console, the navigation and the
    API all read the same table.
    """
    if not has_capability(request.user, "MANAGE_USERS"):
        return JsonResponse({"detail": "Not permitted"}, status=403)

    from apps.catalog.models import DiningHall

    codes = RegistrationCode.objects.select_related("hall", "redeemed_by").order_by(
        "-created_at"
    )[:100]

    context = {
        "codes": codes,
        "roles": User.Role.choices,
        "halls": DiningHall.objects.all().order_by("name"),
        "open_count": sum(1 for c in codes if c.is_usable),
        "today": dt.date.today(),
        "figures": [
            {
                "label": "Codes issued",
                "value": len(codes),
                "note": "The 100 most recent",
            },
            {
                "label": "Still open",
                "value": sum(1 for c in codes if c.is_usable),
                "note": "Not yet redeemed, not expired",
            },
            {
                "label": "Redeemed",
                "value": sum(1 for c in codes if c.status == RegistrationCode.Status.REDEEMED),
                "note": "Each one created exactly one account",
            },
            {
                "label": "Revoked",
                "value": sum(1 for c in codes if c.status == RegistrationCode.Status.REVOKED),
                "note": "Withdrawn before use",
            },
        ],
    }
    return render(request, "console/registration_codes.html", context)


@login_required
@require_POST
def registration_code_issue(request):
    """Issue a code."""
    if not has_capability(request.user, "MANAGE_USERS"):
        return JsonResponse({"detail": "Not permitted"}, status=403)

    role = request.POST.get("role") or ""
    hall_id = request.POST.get("hall") or None
    full_name = (request.POST.get("full_name") or "").strip()
    student_identifier = (request.POST.get("student_identifier") or "").strip()
    notes = (request.POST.get("notes") or "").strip()

    try:
        code = RegistrationCode.issue(
            role,
            hall_id=hall_id,
            full_name=full_name,
            student_identifier=student_identifier,
            notes=notes,
        )
    except ValueError:
        return JsonResponse({"detail": "That role cannot be granted"}, status=400)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "code": code.code, "id": code.id})
    return redirect("registration-console")


@login_required
@require_POST
def registration_code_revoke(request, code_id: int):
    """Revoke a code that has not been used."""
    if not has_capability(request.user, "MANAGE_USERS"):
        return JsonResponse({"detail": "Not permitted"}, status=403)

    code = RegistrationCode.objects.get(pk=code_id)
    if code.status != RegistrationCode.Status.OPEN:
        return JsonResponse({"detail": "That code is not open"}, status=400)

    code.status = RegistrationCode.Status.REVOKED
    code.save(update_fields=["status", "updated_at"])
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect("registration-console")


@require_GET
def register(request):
    """The registration screen."""
    if request.user.is_authenticated:
        return redirect("dashboard-home")

    context = {
        "role_labels": dict(User.Role.choices),
        "today": dt.date.today(),
    }
    return render(request, "registration/register.html", context)


@require_POST
def register_submit(request):
    """Redeem a registration code and create the account."""
    code_text = (request.POST.get("code") or "").strip().upper()
    username = (request.POST.get("username") or "").strip()
    password = request.POST.get("password") or ""
    confirm = request.POST.get("password_confirm") or ""

    if not code_text:
        return JsonResponse({"detail": "Enter the code from the mess office", "field": "code"}, status=400)
    if not username:
        return JsonResponse({"detail": "Choose a username", "field": "username"}, status=400)
    if len(password) < 8:
        return JsonResponse({"detail": "Use at least 8 characters", "field": "password"}, status=400)
    if password != confirm:
        return JsonResponse({"detail": "The two passwords do not match", "field": "password_confirm"}, status=400)
    if User.objects.filter(username__iexact=username).exists():
        return JsonResponse({"detail": "That username is taken", "field": "username"}, status=400)

    try:
        code = RegistrationCode.objects.get(code=code_text)
    except RegistrationCode.DoesNotExist:
        return JsonResponse({"detail": "That code was not recognised", "field": "code"}, status=400)

    if not code.is_usable:
        if code.status == RegistrationCode.Status.REDEEMED:
            return JsonResponse({"detail": "That code has already been used", "field": "code"}, status=400)
        if code.status == RegistrationCode.Status.REVOKED:
            return JsonResponse({"detail": "That code was revoked", "field": "code"}, status=400)
        return JsonResponse({"detail": "That code has expired", "field": "code"}, status=400)

    name_parts = (code.full_name or "").strip().split(None, 1)
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    user = User.objects.create_user(
        username=username,
        password=password,
        first_name=first_name,
        last_name=last_name,
        role=code.role,
        hall=code.hall,
        student_identifier=code.student_identifier or None,
    )
    code.redeem(user)

    login(request, user)
    return JsonResponse({"ok": True, "redirect": "/dashboard/"})


@login_required
@require_GET
def profile_page(request):
    """The user-friendly profile page integrated into the interface."""
    return render(request, "accounts/profile.html")


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

def _rate_limited(ident: str, limit: int = 5, window: int = 3600) -> bool:
    """Allow ``limit`` reset requests per ``window`` seconds per identifier."""
    key = f"pwreset:{ident}"
    count = cache.get(key, 0)
    if count >= limit:
        return True
    cache.set(key, count + 1, window)
    return False


@require_GET
def password_reset_forgot(request):
    """The forgot-password screen."""
    if request.user.is_authenticated:
        return redirect("dashboard-home")
    return render(request, "accounts/password_reset_forgot.html")


@require_POST
def password_reset_request(request):
    """Accept an email and, if an account matches, send a reset link.

    Whether the email is registered is never confirmed or denied.
    """
    email = (request.POST.get("email") or "").strip().lower()

    email_limited = _rate_limited(f"email:{email}", limit=3, window=3600) if email else True
    ip_limited = _rate_limited(
        f"ip:{request.META.get('REMOTE_ADDR', 'unknown')}", limit=10, window=3600
    )
    if email_limited or ip_limited:
        return render(
            request,
            "accounts/password_reset_forgot.html",
            {"email": email, "notice": "Too many requests. Try again later."},
        )

    user = User.objects.filter(email__iexact=email).first()
    if user is not None:
        # Only the newest link works; older unredeemed tokens are spent.
        PasswordResetToken.objects.filter(user=user, used_at__isnull=True).delete()
        reset = PasswordResetToken.create_for_user(user)

        link = request.build_absolute_uri(
            reverse("password-reset-confirm", args=[reset.token])
        )
        subject = render_to_string(
            "accounts/email/password_reset_subject.txt", {"link": link}
        ).strip()
        body = render_to_string(
            "accounts/email/password_reset_body.txt",
            {
                "user": user,
                "link": link,
                "timeout_minutes": settings.PASSWORD_RESET_TIMEOUT // 60,
            },
        )
        html_body = render_to_string(
            "accounts/email/password_reset_body.html",
            {
                "user": user,
                "link": link,
                "timeout_minutes": settings.PASSWORD_RESET_TIMEOUT // 60,
            },
        )
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html_body,
            fail_silently=not settings.DEBUG,
        )

    return render(
        request,
        "accounts/password_reset_done.html",
        {
            "notice": "If an account matches that address, a reset link will be sent to it.",
        },
    )


@require_GET
def password_reset_confirm(request, token: str):
    """Show the reset-password form for a valid, unused, unexpired token."""
    reset = PasswordResetToken.objects.select_related("user").filter(token=token).first()

    if reset is None or reset.used_at is not None or reset.is_expired:
        return render(
            request,
            "accounts/password_reset_done.html",
            {
                "error": "That reset link is invalid or has expired. Request a new one.",
            },
        )

    return render(
        request,
        "accounts/password_reset_confirm.html",
        {"token": token, "email": reset.user.email},
    )


@require_POST
def password_reset_complete(request, token: str):
    """Validate the token and set a new password, then invalidate the token."""
    reset = PasswordResetToken.objects.select_related("user").filter(token=token).first()

    if reset is None or reset.used_at is not None or reset.is_expired:
        return render(
            request,
            "accounts/password_reset_done.html",
            {
                "error": "That reset link is invalid or has expired. Request a new one.",
            },
        )

    new_password = request.POST.get("new_password") or ""
    confirm = request.POST.get("new_password_confirm") or ""
    user = reset.user

    errors = []
    if not new_password:
        errors.append("Choose a new password.")
    else:
        try:
            password_validation.validate_password(new_password, user=user)
        except ValidationError as exc:
            errors.extend(exc.messages)
    if new_password != confirm:
        errors.append("The two passwords do not match.")
    if new_password and user.check_password(new_password):
        errors.append("The new password must differ from the current one.")
    if errors:
        return render(
            request,
            "accounts/password_reset_confirm.html",
            {"token": token, "email": user.email, "errors": errors},
        )

    user.set_password(new_password)
    user.save(update_fields=["password"])
    reset.used_at = timezone.now()
    reset.save(update_fields=["used_at"])

    # Any other outstanding tokens for this user are spent too.
    PasswordResetToken.objects.filter(user=user, used_at__isnull=True).exclude(
        pk=reset.pk
    ).delete()

    # Revoke all outstanding refresh tokens so a stolen refresh token cannot
    # keep working after the password changes.
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

    OutstandingToken.objects.filter(user=user).delete()

    login(request, user)
    update_session_auth_hash(request, user)

    return render(
        request,
        "accounts/password_reset_done.html",
        {"notice": "Your password was changed. You are signed in."},
    )
