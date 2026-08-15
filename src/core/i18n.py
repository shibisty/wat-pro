"""
UI localization: supported languages, loading translations from
translations/*.json, detecting the system language, HTTP/JS locale
settings that get forwarded into the web page itself.
"""

import json
import os

from PyQt6.QtCore import QLocale

from .config import TRANSLATIONS_DIR

# ---------------------------------------------------------------------------
# Supported UI languages
# ---------------------------------------------------------------------------
SUPPORTED_LANGUAGES = {
    "en": "English",
    "ru": "Русский",
    "uk": "Українська",
    "zh": "中文",
    "ko": "한국어",
    "ja": "日本語",
    "es": "Español",
    "fr": "Français",
    "ar": "العربية",
    "pt": "Português",
    "hi": "हिन्दी",
    "de": "Deutsch",
}
RTL_LANGUAGES = {"ar"}

# The Accept-Language header that actually goes out in HTTP requests to the site
ACCEPT_LANGUAGE_MAP = {
    "en": "en-US,en;q=0.9",
    "ru": "ru-RU,ru;q=0.9,en;q=0.8",
    "uk": "uk-UA,uk;q=0.9,en;q=0.8",
    "zh": "zh-CN,zh;q=0.9,en;q=0.8",
    "ko": "ko-KR,ko;q=0.9,en;q=0.8",
    "ja": "ja-JP,ja;q=0.9,en;q=0.8",
    "es": "es-ES,es;q=0.9,en;q=0.8",
    "fr": "fr-FR,fr;q=0.9,en;q=0.8",
    "ar": "ar-SA,ar;q=0.9,en;q=0.8",
    "pt": "pt-PT,pt;q=0.9,en;q=0.8",
    "hi": "hi-IN,hi;q=0.9,en;q=0.8",
    "de": "de-DE,de;q=0.9,en;q=0.8",
}

# The BCP47 tag the page will see via navigator.language/languages
NAVIGATOR_LOCALE_MAP = {
    "en": "en-US", "ru": "ru-RU", "uk": "uk-UA", "zh": "zh-CN", "ko": "ko-KR",
    "ja": "ja-JP", "es": "es-ES", "fr": "fr-FR", "ar": "ar-SA", "pt": "pt-PT", "hi": "hi-IN",
    "de": "de-DE",
}


def load_translations(lang_code: str) -> dict:
    """
    Loads the translation JSON file from translations/<lang>.json.
    If the file is missing or some keys are missing — the gaps are
    filled in from the English (base) file, so the UI never shows blank
    labels.
    """
    def _read(code):
        path = os.path.join(TRANSLATIONS_DIR, f"{code}.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    base = _read("en")
    if lang_code == "en":
        return base
    merged = dict(base)
    merged.update(_read(lang_code))
    return merged


def detect_system_language() -> str:
    """Detects the OS language and maps it to a supported one."""
    try:
        locale_name = QLocale.system().name()  # e.g. "ru_RU", "zh_CN"
        code = locale_name.split("_")[0].lower()
        if code in SUPPORTED_LANGUAGES:
            return code
        if code.startswith("zh"):
            return "zh"
    except Exception:
        pass
    return "en"
    