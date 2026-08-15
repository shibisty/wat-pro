"""
Shared paths and constants for the application.

In a normal run (python run.py), everything — translations/,
settings.ini, scenarios/ — lives next to the qt_test_tool/ package.

In a bundled PyInstaller build this is split:
- APP_DIR (user data: settings.ini, scenarios/, DB) — the folder RIGHT
  NEXT TO the .exe itself, so data isn't lost between runs (--onefile
  unpacks the bundle into a temp folder every time — you can't write
  anything persistent there, it gets deleted on exit).
- BUNDLE_DIR (read-only: translations/, resources/) — the folder where
  PyInstaller unpacked the application's own files (sys._MEIPASS for
  --onefile, the folder next to the exe for --onedir).

If the app is packaged as MSIX (Desktop Bridge) — the install folder is
READ-ONLY, you can't write there at all (Windows historically applies a
hidden redirect for classic Win32 apps, but that's a legacy mechanism you
shouldn't rely on). In that case APP_DIR is forced to
%LOCALAPPDATA%\\WAT Pro — this is the officially recommended location for
a packaged app's data.
"""

import os
import platform
import sys


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _packaged_app_data_dir():
    """
    If the process was launched from an MSIX package — return
    %LOCALAPPDATA%\\WAT Pro, otherwise None. Detected via
    GetCurrentPackageFullName (the standard way for a classic Win32 app
    to find out it was launched through Desktop Bridge/MSIX identity).
    """
    if platform.system() != "Windows":
        return None
    try:
        import ctypes
        length = ctypes.c_uint32(0)
        res = ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None)
        APPMODEL_ERROR_NO_PACKAGE = 15700
        if res == APPMODEL_ERROR_NO_PACKAGE:
            return None  # a regular (non-MSIX) run
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
    # The qt_test_tool/ package folder (one level above core/)
    APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    BUNDLE_DIR = APP_DIR

TRANSLATIONS_DIR = os.path.join(BUNDLE_DIR, "translations")
ICON_PATH = os.path.join(BUNDLE_DIR, "resources", "icon.png")
CHEVRON_DOWN_ICON_PATH = os.path.join(BUNDLE_DIR, "resources", "chevron_down.png")

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
