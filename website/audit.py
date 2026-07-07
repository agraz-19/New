from .models import AuditTrail

def get_client_ip(request):
    """Get the client's IP address from the request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def log_audit(request, action, model, description, status='success'):
    """Log an audit trail"""
    ip_address = get_client_ip(request)
    AuditTrail.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action,
        model=model,
        description=description,
        ip_address=ip_address,
        status=status
    )