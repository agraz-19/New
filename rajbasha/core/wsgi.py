"""
WSGI config for core project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

application = get_wsgi_application()


# WSGI middleware to remove sensitive headers from all responses
class HeaderSanitizationMiddleware:
    """Remove headers that may leak sensitive information about the server/framework."""
    
    def __init__(self, app):
        self.app = app
    
    def __call__(self, environ, start_response):
        def custom_start_response(status, response_headers):
            # Remove headers that expose server information
            sanitized_headers = [
                (header, value) for header, value in response_headers
                if header.lower() not in [
                    'server',              # Web server type and version
                    'x-powered-by',        # Technology stack
                    'x-aspnet-version',    # ASP.NET version
                    'x-runtime',           # Runtime environment
                    'x-django-version',    # Django version (if exposed)
                ]
            ]
            return start_response(status, sanitized_headers)
        
        return self.app(environ, custom_start_response)


# Wrap the Django application with header sanitization middleware
application = HeaderSanitizationMiddleware(application)
