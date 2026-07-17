import logging
from functools import wraps

from django.conf import settings
from django.contrib.auth import logout
from django.http import JsonResponse
from django.shortcuts import redirect

logger = logging.getLogger(__name__)


def _parse_x_forwarded_for(xff_value: str) -> list[str]:
    if not xff_value:
        return []
    return [ip.strip() for ip in xff_value.split(",") if ip.strip()]


def get_client_ip(request):
    remote_addr = request.META.get("REMOTE_ADDR", "")
    xff_value = request.META.get("HTTP_X_FORWARDED_FOR", "")

    if (
        getattr(settings, "TRUST_X_FORWARDED_FOR", False)
        and remote_addr
        and remote_addr in getattr(settings, "TRUSTED_PROXY_IPS", [])
        and xff_value
    ):
        forwarded_ips = _parse_x_forwarded_for(xff_value)
        if forwarded_ips:
            return forwarded_ips[0]

    return remote_addr


def is_upload_ip_allowed(ip_address: str) -> bool:
    if not ip_address:
        return False
    allowed_ips = getattr(settings, "UPLOAD_ALLOWED_IPS", [])
    return ip_address in allowed_ips


def _unauthorized_upload_response(request, client_ip):
    if request.user.is_authenticated:
        logout(request)

    logger.warning(
        "Blocked unauthorized upload access: remote_addr=%s client_ip=%s path=%s method=%s",
        request.META.get("REMOTE_ADDR"),
        client_ip,
        request.path,
        request.method,
    )

    is_json_request = (
        request.method == "POST"
        and (
            request.headers.get("Accept", "").startswith("application/json")
            or request.content_type == "application/json"
        )
    )

    if is_json_request:
        return JsonResponse(
            {"status": "error", "message": "Unauthorized upload attempt."},
            status=403,
        )

    return redirect(settings.LOGIN_URL)


def upload_ip_restricted(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        client_ip = get_client_ip(request)
        if not is_upload_ip_allowed(client_ip):
            return _unauthorized_upload_response(request, client_ip)

        return view_func(request, *args, **kwargs)

    return _wrapped_view
