def global_settings(request):
    if not hasattr(request, 'session'):
        return {}
    user_state = ''
<<<<<<< HEAD
    user_office= ''
    if request.user.is_authenticated:
        user_state = getattr(getattr(request.user, 'profile', None), 'office_state', '')
        user_office= getattr(getattr(request.user, 'profile', None), 'office_name', '')
    return {
        'current_lang': request.session.get('lang', 'en'),
        'role': request.session.get('active_role', 'user'),
        'user_state': user_state,
        'user_office':user_office
    }
=======
    if request.user.is_authenticated:
        user_state = getattr(getattr(request.user, 'profile', None), 'office_state', '')
    return {
        'current_lang': request.session.get('lang', 'en'),
        'role': request.session.get('active_role', 'user'),
        'user_state': user_state
    }
>>>>>>> origin/main
