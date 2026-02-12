import hashlib
from django import template
from django.core.cache import cache
from deep_translator import GoogleTranslator


register = template.Library()

@register.filter(name='t')
def translate_text(text, lang):
    if lang == 'en' or not text:
        return text
    if not text:
        return ""
    text_str = str(text)
    cache_key = f"trans_{lang}_{hashlib.md5(text_str.encode()).hexdigest()}"
    
    try:
        return cache.get_or_set(
            cache_key,
            lambda: GoogleTranslator(source='en', target=lang).translate(text_str),
            86400
        )
    except Exception as e:
        print(f"Translation failed: {e}")
        return text_str