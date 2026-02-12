def global_settings(request):
    if not hasattr(request, 'session'):
        return {}
    return {
        'current_lang': request.session.get('lang', 'en'),
        'role': request.session.get('active_role', 'user')
    }