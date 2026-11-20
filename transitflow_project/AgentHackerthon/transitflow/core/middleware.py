from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
import time

ROLE_SESSION_TIMEOUTS = {
    'MANAGER': 14400,   # 4 hours - High security administrative session
    'PORTER': 36000,    # 10 hours - Warehouse shift duration
    'DRIVER': 43200,    # 12 hours - Transit trip shift duration
    'CLIENT': 604800,   # 7 days - Customer tracking convenience
}

class RoleSessionMiddleware:
    """
    Middleware that manages distinct session lifespans, session-level role verification,
    and guarantees strict isolation between Manager, Porter, Driver, and Client portals.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            user_role = getattr(request.user, 'role', 'CLIENT')
            
            # Initialize or refresh role in session
            current_role_in_session = request.session.get('user_role')
            if current_role_in_session != user_role:
                request.session['user_role'] = user_role
                request.session['role_label'] = request.user.get_role_display()
                request.session['session_started_at'] = int(time.time())
                
                # Apply role-specific session lifespan
                session_age = ROLE_SESSION_TIMEOUTS.get(user_role, 86400)
                request.session.set_expiry(session_age)
                request.session['role_session_expiry_seconds'] = session_age

            # Portal path isolation guard
            path = request.path
            
            # Check portal cross-access
            if path.startswith('/portal/manager/') and not (request.user.is_manager or request.user.is_superuser):
                messages.error(request, "Access restricted: You do not have managerial clearance.")
                return redirect(self._get_role_redirect(request.user))
                
            elif path.startswith('/portal/porter/') and not (request.user.is_porter or request.user.is_manager):
                messages.error(request, "Access restricted: Porter terminal clearance required.")
                return redirect(self._get_role_redirect(request.user))
                
            elif path.startswith('/portal/driver/') and not (request.user.is_driver or request.user.is_manager):
                messages.error(request, "Access restricted: Driver transit portal clearance required.")
                return redirect(self._get_role_redirect(request.user))

        response = self.get_response(request)
        return response

    def _get_role_redirect(self, user):
        role = getattr(user, 'role', 'CLIENT')
        if role == 'MANAGER' or user.is_superuser:
            return 'manager_dashboard'
        elif role == 'PORTER':
            return 'porter_dashboard'
        elif role == 'DRIVER':
            return 'driver_dashboard'
        return 'client_dashboard'
