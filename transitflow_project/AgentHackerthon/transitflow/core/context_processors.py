def role_context(request):
    """
    Supplies role helpers, session info, and navigation links to all templates.
    """
    if not request.user.is_authenticated:
        return {
            'is_manager': False,
            'is_porter': False,
            'is_driver': False,
            'is_client': False,
            'user_role': None,
            'portal_url_name': 'login',
        }

    role = getattr(request.user, 'role', 'CLIENT')
    return {
        'current_user': request.user,
        'user_role': role,
        'is_manager': request.user.is_manager,
        'is_porter': request.user.is_porter,
        'is_driver': request.user.is_driver,
        'is_client': request.user.is_client,
        'portal_url_name': request.user.portal_url_name,
        'session_role_label': request.session.get('role_label', request.user.get_role_display()),
        'session_expiry_seconds': request.session.get('role_session_expiry_seconds', 86400),
    }
