import hashlib
from typing import Optional
from django import template
from django.core.cache import cache
from deep_translator import GoogleTranslator


register = template.Library()

@register.filter(name='t')
def translate_text(text: Optional[str], lang: str) -> str:
    """Translate `text` to `lang` and always return a string.

    Coerce `None` to an empty string so callers (including `messages.error`)
    always receive a `str`.
    """
    text_str = str(text) if text is not None else ""

    if lang == 'en' or text_str == "":
        return text_str

    cache_key = f"trans_{lang}_{hashlib.md5(text_str.encode(), usedforsecurity=False).hexdigest()}"

    try:
        return cache.get_or_set(
            cache_key,
            lambda: GoogleTranslator(source='en', target=lang).translate(text_str),
            86400,
        )
    except Exception as e:
        print(f"Translation failed: {e}")
        return text_str