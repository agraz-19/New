def global_settings(request):
    if not hasattr(request, 'session'):
        return {}
        
    user_state = ''
    user_office = ''
    user_roles = []
    
    if request.user.is_authenticated:
        profile = getattr(request.user, 'profile', None)
        if profile:
            user_state = getattr(profile, 'office_state', '')
            user_office = getattr(profile, 'office_name', '')
            
        u_roles = list(request.user.roles.values_list('name', flat=True))
        p_roles = list(profile.roles.values_list('name', flat=True)) if profile else []
        
        user_roles = list(set(u_roles + p_roles))

    return {
        'current_lang': request.session.get('lang', 'en'),
        'user_roles': user_roles, 
        'user_state': user_state,
        'user_office': user_office
    }
