from urllib import response

from bs4 import BeautifulSoup, Comment
from deep_translator import GoogleTranslator
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
import hashlib

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
    def process_response(self, request, response):
        # Preserve any stronger upstream setting while preventing an explicit disable state.
        response.setdefault("X-XSS-Protection", "1; mode=block")
        response.setdefault("X-Content-Type-Options", "nosniff")
        response.setdefault("Cross-Origin-Embedder-Policy", "require-corp")
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.setdefault(
            "Content-Security-Policy",
            "; ".join([
                "default-src 'self'",
                "script-src 'self' 'unsafe-inline'",
                "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'",
                "font-src 'self' https://cdn.jsdelivr.net data:",
                "img-src 'self' data: blob:",
                "connect-src 'self'",
                "object-src 'none'",
                "base-uri 'self'",
                "form-action 'self'",
                "frame-ancestors 'self'",
            ]),
        )
        if "Server" in response:
            del response["Server"]
        if "X-Powered-By" in response:
            del response["X-Powered-By"]
        return response
