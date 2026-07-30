"""
Локализация интерфейса: поддерживаемые языки, загрузка переводов из
translations/*.json, определение языка системы, HTTP/JS-настройки локали,
которые пробрасываются в саму веб-страницу.
"""

import json
import os

from PyQt6.QtCore import QLocale

from .config import TRANSLATIONS_DIR

# ---------------------------------------------------------------------------
# Поддерживаемые языки интерфейса
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

# Заголовок Accept-Language, который реально уходит в HTTP-запросы к сайту
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

# BCP47-тег, который страница увидит через navigator.language/languages
NAVIGATOR_LOCALE_MAP = {
    "en": "en-US", "ru": "ru-RU", "uk": "uk-UA", "zh": "zh-CN", "ko": "ko-KR",
    "ja": "ja-JP", "es": "es-ES", "fr": "fr-FR", "ar": "ar-SA", "pt": "pt-PT", "hi": "hi-IN",
    "de": "de-DE",
}


def load_translations(lang_code: str) -> dict:
    """
    Загружает JSON-файл перевода из translations/<lang>.json.
    Если файла нет или каких-то ключей не хватает — недостающее
    подтягивается из английского (базового) файла, чтобы интерфейс
    никогда не показывал пустые подписи.
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
    """Определяет язык ОС и сопоставляет его с поддерживаемыми."""
    try:
        locale_name = QLocale.system().name()  # напр. "ru_RU", "zh_CN"
        code = locale_name.split("_")[0].lower()
        if code in SUPPORTED_LANGUAGES:
            return code
        if code.startswith("zh"):
            return "zh"
    except Exception:
        pass
    return "en"
    