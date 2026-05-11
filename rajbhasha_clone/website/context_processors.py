def global_settings(request):
    if not hasattr(request, 'session'):
        return {}
    user_state = ''
    if request.user.is_authenticated:
        user_state = getattr(getattr(request.user, 'profile', None), 'office_state', '')
    return {
        'current_lang': request.session.get('lang', 'en'),
        'role': request.session.get('active_role', 'user'),
        'user_state': user_state
    }