# hms/decorators.py
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def role_required(*roles):
    """
    Usage:
        @role_required("doctor", "admin")
        def my_view(request): ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):

            # Not logged in
            if not request.user.is_authenticated:
                return redirect("login")

            # Superuser bypasses all role checks
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            # Get role from UserProfile
            try:
                user_role = request.user.profile.role
            except Exception:
                messages.error(request, "Your account has no role assigned. Contact admin.")
                return redirect("hms:dashboard")

            # Check role
            if user_role not in roles:
                messages.error(
                    request,
                    f"Access denied. This page requires: {', '.join(roles)}."
                )
                return redirect("hms:dashboard")

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator