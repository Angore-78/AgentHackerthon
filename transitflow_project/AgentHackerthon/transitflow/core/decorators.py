from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied

def role_required(allowed_roles):
    """
    Decorator for views that checks whether the user has one of the allowed roles.
    Allowed roles can be passed as a list, e.g. ['MANAGER', 'PORTER']
    """
    if isinstance(allowed_roles, str):
        allowed_roles = [allowed_roles]

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')

            user_role = getattr(request.user, 'role', None)
            
            # Superusers always have manager-level access
            if request.user.is_superuser and 'MANAGER' in allowed_roles:
                return view_func(request, *args, **kwargs)

            if user_role in allowed_roles or (request.user.is_manager and 'MANAGER' in allowed_roles):
                return view_func(request, *args, **kwargs)

            messages.error(request, f"Access restricted: Your role ({request.user.get_role_display()}) cannot access this section.")
            return redirect('portal_redirect')

        return _wrapped_view
    return decorator
