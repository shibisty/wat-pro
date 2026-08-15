"""
Detecting the system theme (light/dark) and coloring the window's native
frame (title bar, minimize/close buttons) to match — Windows only, via
the DWM API.
"""

import platform
import subprocess


def detect_system_theme() -> str:
    """
    Detects the current system theme (light/dark).
    Windows — via the registry, macOS — via `defaults read`,
    Linux — via `gsettings` (GNOME/Cinnamon and compatible).
    If it can't be detected — light theme is the default.
    """
    system = platform.system()
    try:
        if system == "Windows":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if value == 1 else "dark"
        elif system == "Darwin":
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True, timeout=2,
            )
            return "dark" if "Dark" in result.stdout else "light"
        elif system == "Linux":
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                capture_output=True, text=True, timeout=2,
            )
            if "dark" in result.stdout.lower():
                return "dark"
            return "light"
    except Exception:
        pass
    return "light"


def apply_native_titlebar_theme(window, dark: bool):
    """
    Colors the window's native frame (title bar, minimize/close buttons)
    dark on Windows 10 (1809+) / Windows 11 via the DWM API.
    On other OSes or older Windows builds it silently does nothing — the
    native frame can't be recolored there with Qt's own tools.
    """
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        hwnd = int(window.winId())
        value = ctypes.c_int(1 if dark else 0)
        # 20 — the current attribute (Win10 1903+/Win11), 19 — older Win10 builds.
        for attribute in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
    except Exception:
        pass
