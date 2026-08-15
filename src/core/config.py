"""
Shared paths and constants for the application.

BUNDLE_DIR — read-only application code/assets (translations/,
resources/): wherever the package folder lives (a dev checkout, or the
PyInstaller bundle folder for a frozen build).

APP_DIR — writable user data (settings.ini, scenarios/, the DB): ALWAYS
a proper per-user OS data folder (%LOCALAPPDATA%\\WAT Pro on Windows,
~/Library/Application Support/WAT Pro on macOS, an XDG data dir on
Linux), regardless of whether this is a dev checkout or a packaged
build. This keeps user data completely independent of wherever the
source/package folder happens to be — renaming or moving the package
folder (e.g. qt_test_tool/ renamed to src/) no longer has any effect on
where your scenarios/settings live, and the source tree stays free of
runtime-generated files.

Previously, user data lived in the project root (one level above the
package folder) for a dev run, or next to the .exe for a non-MSIX frozen
build — _migrate_legacy_user_data() below moves any data found there
into the new location once, automatically, so existing scenarios/
settings aren't lost by this change.
"""

import os
import platform
import sys


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _user_data_dir() -> str:
    app_name = "WAT Pro"
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    elif system == "Darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, app_name)


if _is_frozen():
    BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
else:
    # the package folder itself (one level above core/) — read-only
    # application code/assets, wherever it's named (qt_test_tool/, src/, ...)
    BUNDLE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

APP_DIR = _user_data_dir()
os.makedirs(APP_DIR, exist_ok=True)

TRANSLATIONS_DIR = os.path.join(BUNDLE_DIR, "translations")
ICON_PATH = os.path.join(BUNDLE_DIR, "resources", "icon.png")
CHEVRON_DOWN_ICON_PATH = os.path.join(BUNDLE_DIR, "resources", "chevron_down.png")

SETTINGS_PATH = os.path.join(APP_DIR, "settings.ini")
SCENARIOS_DIR = os.path.join(APP_DIR, "scenarios")
DB_PATH = os.path.join(APP_DIR, "app_data.sqlite3")

os.makedirs(SCENARIOS_DIR, exist_ok=True)


def _migrate_legacy_user_data():
    """
    One-time migration for existing checkouts: until this change, user
    data lived in the project root (one level above the package folder)
    for a dev run, or next to the .exe for a non-MSIX frozen build. Move
    it over to the new location so nothing appears to have been lost.
    Safe to call every startup — once a file has moved, its legacy path
    no longer exists, so there's nothing left to re-migrate.
    """
    if _is_frozen():
        legacy_dir = os.path.dirname(sys.executable)
    else:
        legacy_dir = os.path.dirname(BUNDLE_DIR)

    if os.path.abspath(legacy_dir) == os.path.abspath(APP_DIR):
        return

    import shutil

    legacy_settings = os.path.join(legacy_dir, "settings.ini")
    if os.path.exists(legacy_settings) and not os.path.exists(SETTINGS_PATH):
        try:
            shutil.move(legacy_settings, SETTINGS_PATH)
        except OSError:
            pass

    legacy_db = os.path.join(legacy_dir, "app_data.sqlite3")
    if os.path.exists(legacy_db) and not os.path.exists(DB_PATH):
        try:
            shutil.move(legacy_db, DB_PATH)
        except OSError:
            pass

    legacy_scenarios = os.path.join(legacy_dir, "scenarios")
    if os.path.isdir(legacy_scenarios):
        for filename in os.listdir(legacy_scenarios):
            src_path = os.path.join(legacy_scenarios, filename)
            dst_path = os.path.join(SCENARIOS_DIR, filename)
            if os.path.isfile(src_path) and not os.path.exists(dst_path):
                try:
                    shutil.move(src_path, dst_path)
                except OSError:
                    pass


_migrate_legacy_user_data()


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
