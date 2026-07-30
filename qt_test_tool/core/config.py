"""
Общие пути и константы приложения.

В обычном запуске (python run.py) всё — translations/, settings.ini,
scenarios/ — живёт рядом с пакетом qt_test_tool/.

В собранном PyInstaller-приложении это разделяется:
- APP_DIR (пользовательские данные: settings.ini, scenarios/, БД) —
  папка РЯДОМ С САМИМ .exe, чтобы данные не терялись между запусками
  (--onefile каждый раз распаковывает бандл во временную папку —
  писать туда что-то постоянное нельзя, она удаляется после выхода).
- BUNDLE_DIR (только для чтения: translations/, resources/) — папка,
  куда PyInstaller распаковал сами файлы приложения (sys._MEIPASS для
  --onefile, папка рядом с exe для --onedir).

Если приложение упаковано в MSIX (Desktop Bridge) — папка установки
доступна ТОЛЬКО ДЛЯ ЧТЕНИЯ, писать туда вообще нельзя (Windows исторически
подставляет скрытый редирект для классических Win32-приложений, но это
устаревший механизм, полагаться на него не стоит). В этом случае
APP_DIR принудительно переезжает в %LOCALAPPDATA%\\WAT Pro — это и есть
официально рекомендованное место для данных упакованного приложения.
"""

import os
import platform
import sys


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _packaged_app_data_dir():
    """
    Если процесс запущен из MSIX-пакета — вернуть %LOCALAPPDATA%\\WAT Pro,
    иначе None. Определяется через GetCurrentPackageFullName (стандартный
    способ для классических Win32-приложений узнать, что их запустили
    через Desktop Bridge/MSIX identity).
    """
    if platform.system() != "Windows":
        return None
    try:
        import ctypes
        length = ctypes.c_uint32(0)
        res = ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None)
        APPMODEL_ERROR_NO_PACKAGE = 15700
        if res == APPMODEL_ERROR_NO_PACKAGE:
            return None  # обычный (не MSIX) запуск
        buf = ctypes.create_unicode_buffer(length.value)
        ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), buf)
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            return None
        return os.path.join(local_appdata, "WAT Pro")
    except Exception:
        return None


if _is_frozen():
    BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    _packaged_dir = _packaged_app_data_dir()
    if _packaged_dir:
        APP_DIR = _packaged_dir
        os.makedirs(APP_DIR, exist_ok=True)
    else:
        APP_DIR = os.path.dirname(sys.executable)
else:
    # Папка пакета qt_test_tool/ (на уровень выше core/)
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    BUNDLE_DIR = APP_DIR

TRANSLATIONS_DIR = os.path.join(BUNDLE_DIR, "translations")
ICON_PATH = os.path.join(BUNDLE_DIR, "resources", "icon.png")

SETTINGS_PATH = os.path.join(APP_DIR, "settings.ini")
SCENARIOS_DIR = os.path.join(APP_DIR, "scenarios")

os.makedirs(SCENARIOS_DIR, exist_ok=True)

APP_NAME = "WAT Pro"
APP_FULL_NAME = "WAT Pro (Web Automation Tools)"


DEVICE_PRESETS = {
    "Mobile S — 320×568": (320, 568),
    "Mobile M — 375×667": (375, 667),
    "Mobile L — 414×896": (414, 896),
    "Tablet — 768×1024": (768, 1024),
    "Laptop — 1366×768": (1366, 768),
    "Laptop L — 1536×864": (1536, 864),
    "Desktop — 1920×1080": (1920, 1080),
    "4K — 3840×2160": (3840, 2160),
}
