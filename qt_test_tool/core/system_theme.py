"""
Определение системной темы (светлая/тёмная) и покраска системной рамки
окна (заголовок, кнопки свернуть/закрыть) под тему — только Windows,
через DWM API.
"""

import platform
import subprocess


def detect_system_theme() -> str:
    """
    Определяет текущую системную тему (светлая/тёмная).
    Windows — через реестр, macOS — через `defaults read`,
    Linux — через `gsettings` (GNOME/Cinnamon и совместимые).
    Если определить не удалось — светлая тема по умолчанию.
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
    Красит системную рамку окна (заголовок, кнопки свернуть/закрыть) в тёмный
    цвет на Windows 10 (1809+) / Windows 11 через DWM API.
    На других ОС или старых сборках Windows тихо ничего не делает —
    системную рамку там штатными средствами Qt перекрасить нельзя.
    """
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        hwnd = int(window.winId())
        value = ctypes.c_int(1 if dark else 0)
        # 20 — актуальный атрибут (Win10 1903+/Win11), 19 — старые сборки Win10.
        for attribute in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
    except Exception:
        pass
