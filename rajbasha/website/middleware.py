from urllib import response

from bs4 import BeautifulSoup, Comment
from deep_translator import GoogleTranslator
from django.http import HttpResponseBadRequest
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
import hashlib
import re


class RejectQueryStringParametersMiddleware(MiddlewareMixin):
    """Reject POST/PUT/PATCH requests with query string parameters to prevent parameter pollution.
    
    This middleware ensures that only GET requests and DELETE requests can have query parameters.
    POST, PUT, and PATCH requests must send their parameters in the request body, not the URL.
    This prevents parameter pollution attacks and confusion about parameter sources.
    """
    
    def process_request(self, request):
        """Check if POST/PUT/PATCH requests have query string parameters and reject them."""
        # Only check methods that should never have query parameters for data
        if request.method in ['POST', 'PUT', 'PATCH'] and request.GET:
            # Some legitimate use cases (like filtering) may require query params,
            # but body parameters should never be in the query string
            # Return 400 Bad Request if query params are present
            return HttpResponseBadRequest(
                "Request parameters must be sent in the request body, not the query string. "
                "POST, PUT, and PATCH requests should not include parameters in the URL."
            )
        return None


class EnforceCookieSameSiteMiddleware(MiddlewareMixin):
    """Enforce SameSite=Strict on all cookies to prevent cross-site cookie access."""
    
    def process_response(self, request, response):
        """Add SameSite=Strict to all Set-Cookie headers that don't already have it."""
        if 'Set-Cookie' in response:
            cookie_header = response['Set-Cookie']
            # Add SameSite=Strict if not already present
            if 'SameSite' not in cookie_header:
                # Append SameSite=Strict to the cookie
                response['Set-Cookie'] = f"{cookie_header}; SameSite=Strict"
        return response


class PathDisclosurePreventionMiddleware(MiddlewareMixin):
    """Strip path disclosure patterns from response content to prevent information leakage."""
    
    # Common path patterns to strip from responses
    PATH_PATTERNS = [
        r'/home/[a-zA-Z0-9_\-\.]+/',  # Unix home directories
        r'/root/',                     # Linux root directory
        r'/var/www/',                  # Web server directories
        r'/opt/[a-zA-Z0-9_\-\.]+/',   # Optional software directories
        r'/srv/[a-zA-Z0-9_\-\.]+/',   # Service directories
        r'C:\\(?:[a-zA-Z0-9_\-\.]+\\)+',  # Windows absolute paths
        r'[A-Z]:\\(?:[a-zA-Z0-9_\-\.]+\\)+',  # Windows drive letters
    ]
    
    def process_response(self, request, response):
        """Remove sensitive path information from response content."""
        # Only process text-based responses
        content_type = response.get('Content-Type', '')
        if 'application/json' not in content_type and 'text/' not in content_type:
            return response
        
        # Skip if content is not readable
        if not hasattr(response, 'content') or response.streaming:
            return response
        
        try:
            content = response.content.decode('utf-8', errors='ignore')
            original_length = len(content)
            
            # Replace path patterns with generic placeholders
            for pattern in self.PATH_PATTERNS:
                content = re.sub(pattern, '[REDACTED_PATH]', content, flags=re.IGNORECASE)
            
            # Only update if content changed
            if len(content) != original_length:
                response.content = content.encode('utf-8')
                # Update Content-Length if present
                if 'Content-Length' in response:
                    response['Content-Length'] = len(response.content)
        except (AttributeError, UnicodeDecodeError):
            # If we can't process the content, leave it as-is
            pass
        
        return response


class DynamicTranslationMiddleware(MiddlewareMixin):
    # Added more technical artifacts to prevent them from showing as "एचटीएमएल"
    BLACKLIST = ['HTML', 'html', 'Banner carousel', 'csrfmiddlewaretoken', 'doctype', 'DOCTYPE']
    
    # Task Requirement: Keep these fields UNCHANGED even in Hindi
    # Add the exact field names/labels you want to lock here
    LOCKED_FIELDS = ['Empcode', 'Superannuation Date'] 

    MANUAL_MAP = {
        'hi': {
            'Select': 'चुनना',
            'Actions': 'कार्रवाई',
            'Drafts': 'ड्राफ्ट',
            'Submitted Records': 'प्रस्तुत अभिलेख',
            'Back to Drafts': 'ड्राफ्ट पर वापस जाएँ',
            'Back to Form': 'फॉर्म पर वापस जाएँ',
            'Prabodh': 'प्रबोध',
            'Praveen': 'प्रवीण',
            'Pragya': 'प्रज्ञा',
            'Parangat': 'पारंगत',
            'Typing': 'टाइपिंग',
            'Hindi Proficiency': 'हिंदी प्रवीणता',
            'Gazetted': 'राजपत्रित',
            'Non-Gazetted': 'अराजपत्रित',
            'Passed': 'उत्तीर्ण',
            'Did not Appear': 'उपस्थित नहीं हुए',
            'Senior Assistant': 'सहायक अनुभाग अधिकारी',
            'Section Officer': 'अनुभाग अधिकारी'
        }
    }

    def process_response(self, request, response):
        if request.method != "GET":
             
             return response
        target_lang = request.GET.get('lang')
        
        if request.method == "GET" and target_lang and target_lang != 'en' and "text/html" in response.get('Content-Type', ''):
            try:
                content = response.content.decode('utf-8')
                soup = BeautifulSoup(content, 'html.parser')

                # 1. Strip comments immediately
                for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
                    comment.extract()

                translator = GoogleTranslator(source='auto', target=target_lang)

                # 2. Optimized Text Node Processing
                for element in soup.find_all(string=True):
                    # Skip code-heavy tags
                    if element.parent.name in ['script', 'style', 'code', 'head', 'title', 'meta']:
                        continue

                    original_text = element.strip()
                    
                    # Skip empty strings, purely numeric data, or Locked Fields
                    if not original_text or original_text.isdigit() or original_text in self.LOCKED_FIELDS:
                        continue

                    # FIX: Check Blacklist (Case-Insensitive)
                    if original_text.upper() in [x.upper() for x in self.BLACKLIST]:
                        # Do not replace with translated text; just leave it as is or clear if it's a ghost tag
                        continue

                    # 3. Manual Mapping
                    if target_lang in self.MANUAL_MAP and original_text in self.MANUAL_MAP[target_lang]:
                        element.replace_with(self.MANUAL_MAP[target_lang][original_text])
                        continue

                    # 4. Dynamic Translation with Cache
                    if len(original_text) > 1:
                        cache_key = hashlib.sha256(f"{target_lang}_{original_text}".encode(), usedforsecurity=False).hexdigest()
                        translated_text = cache.get(cache_key)
                        
                        if not translated_text:
                            try:
                                # Final safety check: Don't translate if it looks like a tag
                                if '<' in original_text or '>' in original_text:
                                    continue
                                    
                                translated_text = translator.translate(original_text)
                                if translated_text:
                                    cache.set(cache_key, translated_text, 86400)
                            except:
                                translated_text = original_text
                        
                        if translated_text:
                            element.replace_with(translated_text)
                
                # Use 'html.parser' or 'lxml' to avoid extra <html> tags being added at the top
                response.content = soup.encode('utf-8')
            except Exception:
                return response
        return response


class SecurityHeadersMiddleware(MiddlewareMixin):
    SENSITIVE_QUERY_PARAMS = {
        "empcode",
        "emp_code",
        "employee_code",
        "username",
        "password",
        "phone",
        "email",
        "alternate_email",
        "office_code",
        "office_name",
        "office_state",
        "ip_number",
        "hod_name",
        "designation",
        "hindi_exam",
    }
    SENSITIVE_QUERY_PATHS = {
        "/profile/",
        "/qpr/profile/update/",
        "/qpr/admin/api/office-create/",
        "/qpr/admin/create-hod/",
        "/manager/employees/master/add/",
        "/logout/",
    }
    SENSITIVE_QUERY_PREFIXES = (
        "/qpr/admin/form",
    )

    def process_request(self, request):
        is_sensitive_path = (
            request.path in self.SENSITIVE_QUERY_PATHS
            or any(request.path.startswith(prefix) for prefix in self.SENSITIVE_QUERY_PREFIXES)
        )
        if is_sensitive_path and request.GET:
            return HttpResponseBadRequest("Sensitive parameters must be sent in the request body.")
        return None

    def process_response(self, request, response):
        # Preserve any stronger upstream setting while preventing an explicit disable state.
        response.setdefault("X-XSS-Protection", "1; mode=block")
        response.setdefault("X-Content-Type-Options", "nosniff")
        response.setdefault("X-Frame-Options", "SAMEORIGIN")  # Fallback for older browsers
        
        # HSTS: Enforce HTTPS for all future requests (1 year, include subdomains)
        response.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
        
        # Cross-Origin Policy headers
        response.setdefault("Cross-Origin-Embedder-Policy", "require-corp")
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        
        response.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        
        # Comprehensive Content-Security-Policy
        csp_directives = [
            "default-src 'self'",
            # Scripts: self + unsafe-inline (required for Django templates); consider moving to nonce in future
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
            # Styles: self + unsafe-inline (Bootstrap requires); consider using hashes
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
            # Fonts from CDN and system
            "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com data:",
            # Images: allow data URIs, blobs, and self
            "img-src 'self' data: blob: https:",
            # Media: restrict to same-origin only
            "media-src 'self'",
            # Form submissions: restrict to same-origin
            "form-action 'self'",
            # Frame ancestors: restrict embedding to same-origin only
            "frame-ancestors 'self'",
            # Objects and embeds: none allowed
            "object-src 'none'",
            "embed-src 'none'",
            # Base URI: restrict to same-origin
            "base-uri 'self'",
            # Connections: self only (no external APIs)
            "connect-src 'self' https:",
            # Frames: self only
            "frame-src 'self'",
            # Manifest files: self only
            "manifest-src 'self'",
            # Worker scripts: self only
            "worker-src 'self'",
            # Upgrade insecure requests to HTTPS
            "upgrade-insecure-requests",
            # Block all mixed content
            "block-all-mixed-content",
        ]
        
        response.setdefault("Content-Security-Policy", "; ".join(csp_directives))
        
        response.setdefault(
            "Permissions-Policy",
            ", ".join([
                "accelerometer=()",
                "camera=()",
                "geolocation=()",
                "gyroscope=()",
                "magnetometer=()",
                "microphone=()",
                "payment=()",
                "usb=()",
            ]),
        )
        
        # Prevent caching of sensitive responses
        # Static assets can be cached, but disable for dynamic content paths
        if not request.path.startswith('/static/'):
            response.setdefault("Cache-Control", "private, no-store, max-age=0, no-cache, must-revalidate")
            response.setdefault("Pragma", "no-cache")
            response.setdefault("Expires", "0")
        
        # Remove ETag to prevent path disclosure through inode-based ETags
        if "ETag" in response:
            del response["ETag"]
        
        # Remove headers that may leak sensitive information about the server/framework
        headers_to_remove = [
            "Server",                   # Reveals web server type and version
            "X-Powered-By",            # Reveals technology stack
            "X-AspNet-Version",        # Reveals ASP.NET version (if applicable)
            "X-Runtime",               # Reveals runtime environment
            "X-Frame-Options",         # Will use CSP instead
            "X-XSS-Protection",        # Will use CSP instead (kept above for older browsers)
        ]
        
        for header in headers_to_remove:
            if header in response:
                del response[header]
        
        return response
