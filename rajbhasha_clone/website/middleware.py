from bs4 import BeautifulSoup, Comment
from deep_translator import GoogleTranslator
from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
import hashlib

class DynamicTranslationMiddleware(MiddlewareMixin):
    # ✅ Removes technical artifacts like the 'HTML' bug from the top left
    BLACKLIST = ['HTML', 'Banner carousel']
    
    # ✅ Comprehensive map for UI elements and departmental proficiency levels
    MANUAL_MAP = {
        'hi': {
            # Navigation & UI Headers
            'Select': 'चुनना',
            'Actions': 'कार्रवाई',
            'Drafts': 'ड्राफ्ट',
            'Submitted Records': 'प्रस्तुत अभिलेख',
            'Back to Drafts': 'ड्राफ्ट पर वापस जाएँ',
            'Back to Form': 'फॉर्म पर वापस जाएँ',
            
            # Proficiency Field Headers
            'Prabodh': 'प्रबोध',
            'Praveen': 'प्रवीण',
            'Pragya': 'प्रज्ञा',
            'Parangat': 'पारंगत',
            'Typing': 'टाइपिंग',
            'Hindi Proficiency': 'हिंदी प्रवीणता',
            
            # Database Results & User-entered data
            'Gazetted': 'राजपत्रित',
            'Non-Gazetted': 'अराजपत्रित',
            'Passed': 'उत्तीर्ण',
            'Did not Appear': 'उपस्थित नहीं हुए',
            'passed': 'उत्तीर्ण',
            'fluent': 'धाराप्रवाह',
            'good': 'अच्छा',
            'excellent': 'उत्कृष्ट',
            'senior Assistant': 'सहायक अनुभाग अधिकारी',
            'senior officer': 'अनुभाग अधिकारी',
            'clerk': 'लिपिक',
            'Assistant Section Officer': 'सहायक अनुभाग अधिकारी',
            'Section Officer': 'अनुभाग अधिकारी'
        }
    }

    def process_response(self, request, response):
        target_lang = request.GET.get('lang')
        
        # Only process if a non-English language is selected and response is HTML
        if target_lang and target_lang != 'en' and "text/html" in response.get('Content-Type', ''):
            try:
                content = response.content.decode('utf-8')
                soup = BeautifulSoup(content, 'html.parser')

                # 1. Clean up comments to avoid translating developer notes
                for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
                    comment.extract()

                translator = GoogleTranslator(source='auto', target=target_lang)

                # 2. Iterate through all text nodes (captures <td> content and <th> headers)
                for element in soup.find_all(string=True):
                    # Skip technical tags that should not be localized
                    if element.parent.name not in ['script', 'style', 'code', 'head', 'title', 'meta']:
                        original_text = element.strip().replace(':', '')
                        
                        if not original_text or original_text.isdigit():
                            continue

                        # Check Blacklist for 'HTML' bug
                        if original_text in self.BLACKLIST:
                            element.replace_with('')
                            continue

                        # Check Manual Map for high-priority departmental labels
                        if target_lang in self.MANUAL_MAP and original_text in self.MANUAL_MAP[target_lang]:
                            element.replace_with(self.MANUAL_MAP[target_lang][original_text])
                            continue

                        # Dynamic Translation for unique strings (e.g., employee names)
                        if len(original_text) > 1:
                            cache_key = hashlib.md5(f"{target_lang}_{original_text}".encode()).hexdigest()
                            translated_text = cache.get(cache_key)
                            
                            if not translated_text:
                                try:
                                    translated_text = translator.translate(original_text)
                                    if translated_text:
                                        cache.set(cache_key, translated_text, 86400) # Cache for 24 hours
                                except:
                                    translated_text = original_text
                            
                            if translated_text:
                                element.replace_with(translated_text)
                
                response.content = str(soup).encode('utf-8')
            except Exception:
                # Return original response if processing fails to maintain site availability
                return response
        return response