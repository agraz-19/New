from bs4 import BeautifulSoup, Comment
from deep_translator import GoogleTranslator
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
import hashlib

class DynamicTranslationMiddleware(MiddlewareMixin):
    # ✅ Blacklist words to COMPLETELY REMOVE from the page
    BLACKLIST = ['HTML', 'Banner carousel']
    
    # Manual map for technical terms
    MANUAL_MAP = {'hi': {'Prabodh': 'प्रबोध', 'Parangat': 'पारंगत', 'Empcode': 'कर्मचारी कोड'}}

    def process_response(self, request, response):
        target_lang = request.GET.get('lang')
        if target_lang and target_lang != 'en' and "text/html" in response.get('Content-Type', ''):
            try:
                content = response.content.decode('utf-8')
                soup = BeautifulSoup(content, 'html.parser')

                # 1. Clean up comments
                for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
                    comment.extract()

                translator = GoogleTranslator(source='auto', target=target_lang)

                for element in soup.find_all(string=True):
                    if element.parent.name not in ['script', 'style', 'code', 'head', 'title', 'meta']:
                        original_text = element.strip().replace(':', '')
                        
                        if not original_text: continue

                        # ✅ NEW: If the text is in the blacklist, DELETE it (Removes एचटीएमएल)
                        if original_text in self.BLACKLIST:
                            element.replace_with('')
                            continue

                        # Check Manual Map first
                        if target_lang in self.MANUAL_MAP and original_text in self.MANUAL_MAP[target_lang]:
                            element.replace_with(self.MANUAL_MAP[target_lang][original_text])
                            continue

                        # Standard translation with None-check to fix the ValueError
                        if len(original_text) > 1 and not original_text.isdigit():
                            cache_key = hashlib.md5(f"{target_lang}_{original_text}".encode()).hexdigest()
                            translated_text = cache.get(cache_key) or translator.translate(original_text)
                            
                            if translated_text: # ✅ FIX: Ensures None is never inserted
                                cache.set(cache_key, translated_text, 86400)
                                element.replace_with(translated_text)
                            else:
                                element.replace_with(original_text)
                
                response.content = str(soup).encode('utf-8')
            except Exception:
                return response
        return response