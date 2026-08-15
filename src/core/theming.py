"""
Light/dark theme palettes in a Material UI spirit, and the QSS
stylesheet generator for the whole app.
"""

import os

from .config import CHEVRON_DOWN_ICON_PATH

# Qt style sheets want forward slashes in url() regardless of OS —
# backslashes get interpreted as escape sequences inside the QSS string.
_CHEVRON_ICON_URL = CHEVRON_DOWN_ICON_PATH.replace(os.sep, "/")

THEMES = {
    "light": {
        "bg": "#f5f6f8",
        "surface": "#ffffff",
        "surface_alt": "#fafafa",
        "border": "#e0e0e0",
        "text": "#1c1e21",
        "text_secondary": "#5f6368",
        "primary": "#1976d2",
        "primary_hover": "#1565c0",
        "primary_pressed": "#0d47a1",
        "primary_contrast": "#ffffff",
        "success": "#2e7d32",
        "success_bg": "#e8f5e9",
        "error": "#d32f2f",
        "error_bg": "#fdecea",
        "warning": "#e65100",
        "hover": "#f0f2f5",
        "chrome_bar": "#e8eaed",
        "chrome_field": "#ffffff",
        "appbar_bg": "#1976d2",
        "appbar_text": "#ffffff",
        "appbar_border": "rgba(255,255,255,110)",
        "appbar_hover": "rgba(255,255,255,35)",
        "appbar_pressed": "rgba(255,255,255,55)",
        "canvas_bg": "#dde1e6",
        "code_bg": "#fafafa",
        "code_text": "#1c1e21",
        "code_tag": "#0000ff",
        "code_attr": "#994500",
        "code_value": "#a31515",
        "code_comment": "#008000",
        "code_linenum_bg": "#eeeeee",
        "code_linenum_text": "#858585",
    },
    "dark": {
        "bg": "#17181a",
        "surface": "#1f2023",
        "surface_alt": "#232427",
        "border": "#33353a",
        "text": "#e8e9ea",
        "text_secondary": "#9aa0a6",
        "primary": "#90caf9",
        "primary_hover": "#64b5f6",
        "primary_pressed": "#42a5f5",
        "primary_contrast": "#0d1117",
        "success": "#81c995",
        "success_bg": "#1c3a24",
        "error": "#f28b82",
        "error_bg": "#3a2323",
        "warning": "#ffb74d",
        "hover": "#2a2c30",
        "chrome_bar": "#2a2c30",
        "chrome_field": "#1f2023",
        "appbar_bg": "#1b1c1f",
        "appbar_text": "#e8e9ea",
        "appbar_border": "rgba(255,255,255,45)",
        "appbar_hover": "rgba(255,255,255,15)",
        "appbar_pressed": "rgba(255,255,255,25)",
        "canvas_bg": "#0d0e10",
        "code_bg": "#1e1e1e",
        "code_text": "#d4d4d4",
        "code_tag": "#569cd6",
        "code_attr": "#9cdcfe",
        "code_value": "#ce9178",
        "code_comment": "#6a9955",
        "code_linenum_bg": "#252526",
        "code_linenum_text": "#858585",
    },
}


def build_stylesheet(theme_name: str) -> str:
    c = THEMES[theme_name]
    return f"""
    * {{
        font-family: "Segoe UI", "Roboto", sans-serif;
        font-size: 16px;
        color: {c['text']};
    }}

    QMainWindow, QDialog {{
        background: {c['bg']};
    }}

    /* ---- top AppBar ---- */
    #topBar {{
        background: {c['appbar_bg']};
        min-height: 64px;
        max-height: 64px;
    }}
    #appbarSeparator {{
        background: {c['border']};
        max-width: 1px;
        min-width: 1px;
        margin: 14px 4px;
    }}
    #themeToggle, QPushButton[class="appbarIconBtn"] {{
        background: transparent;
        color: {c['appbar_text']};
        border: none;
        border-radius: 22px;
        min-width: 44px;
        max-width: 44px;
        min-height: 44px;
        max-height: 44px;
        padding: 0px;
        font-size: 18px;
    }}
    #themeToggle:hover, QPushButton[class="appbarIconBtn"]:hover {{
        background: {c['appbar_hover']};
    }}
    #themeToggle:pressed, QPushButton[class="appbarIconBtn"]:pressed {{
        background: {c['appbar_pressed']};
    }}

    /* ---- screen-switch buttons in the AppBar ---- */
    QPushButton[class="pageTabBtn"] {{
        background: transparent;
        color: {c['appbar_text']};
        border: none;
        border-radius: 10px;
        min-width: 44px;
        min-height: 40px;
        padding: 0px 14px;
        font-size: 17px;
    }}
    QPushButton[class="pageTabBtn"]:hover {{
        background: {c['appbar_hover']};
    }}
    QPushButton[class="pageTabBtn"]:checked {{
        background: {c['appbar_hover']};
        border-bottom: 2px solid {c['primary']};
    }}

    /* local page sub-bar (e.g. scenario management) */
    #pageSubBar {{
        background: {c['chrome_bar']};
        border-bottom: 1px solid {c['border']};
    }}

    /* scenario picker field inside the AppBar */
    #appbarScenarioCombo {{
        min-width: 200px;
    }}
    #appbarLangCombo {{
        min-width: 130px;
    }}

    /* ---- card panels on the left ---- */
    QFrame[class="card"] {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 10px;
    }}
    QLabel[class="sectionLabel"] {{
        color: {c['text_secondary']};
        font-size: 13px;
        font-weight: 600;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        padding: 4px 0px;
    }}

    /* ---- regular buttons (MUI outlined) ---- */
    QPushButton {{
        background: {c['surface']};
        color: {c['primary']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        padding: 11px 20px;
        font-weight: 500;
        min-height: 20px;
    }}
    QPushButton:hover {{
        background: {c['hover']};
        border-color: {c['primary']};
    }}
    QPushButton:pressed {{
        background: {c['border']};
    }}
    QPushButton:disabled {{
        color: {c['text_secondary']};
        border-color: {c['border']};
    }}

    /* ---- primary button (MUI contained primary) ---- */
    QPushButton[class="primaryBtn"] {{
        background: {c['primary']};
        color: {c['primary_contrast']};
        border: none;
        border-radius: 8px;
        padding: 12px 22px;
        font-weight: 600;
        min-height: 22px;
    }}
    QPushButton[class="primaryBtn"]:hover {{
        background: {c['primary_hover']};
    }}
    QPushButton[class="primaryBtn"]:pressed {{
        background: {c['primary_pressed']};
    }}
    /* compact height — matching the neighboring input fields, not a standard button */
    QPushButton#goBtn {{
        padding: 11px 18px;
        border: 1px solid transparent;
        min-height: 20px;
        max-height: 20px;
    }}

    /* ---- round icon buttons for the browser (back/forward/reload) ---- */
    QPushButton[class="circleBtn"] {{
        background: transparent;
        border: none;
        border-radius: 22px;
        min-width: 44px;
        max-width: 44px;
        min-height: 44px;
        max-height: 44px;
        padding: 0px;
        font-size: 20px;
        color: {c['text_secondary']};
    }}
    QPushButton[class="circleBtn"]:hover {{
        background: {c['hover']};
        color: {c['text']};
    }}
    QPushButton[class="circleBtn"]:pressed {{
        background: {c['border']};
    }}
    QPushButton[recording="true"] {{
        color: {c['error']};
        background: {c['error_bg']};
    }}

    /* ---- input fields ---- */
    QLineEdit, QComboBox, QSpinBox {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        padding: 11px 14px;
        selection-background-color: {c['primary']};
        min-height: 20px;
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: 2px solid {c['primary']};
    }}
    /* Custom drop-down + arrow (own PNG, see resources/chevron_down.png).
       Deliberately PNG, not SVG — SVG rendering inside a Qt style sheet
       depends on a separate qsvg plugin that isn't guaranteed to be
       present in every PyQt6 install/build, and would silently fail to
       render with no error at all if missing. PNG has no such
       dependency; it's always supported.
       Earlier this deliberately left ::drop-down completely unstyled to
       fall back to Qt's native arrow rendering — but the native
       drop-down button doesn't know about our custom border-radius and
       draws its own square-cornered area, visibly notching the corner
       of an otherwise rounded field. Styling it explicitly (radius
       matching the field, transparent background) plus our own arrow
       image fixes both problems: the arrow is always visible, and the
       corner stays rounded. */
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 28px;
        border: none;
        background: transparent;
        border-top-right-radius: 8px;
        border-bottom-right-radius: 8px;
    }}
    QComboBox::down-arrow {{
        image: url({_CHEVRON_ICON_URL});
        width: 12px;
        height: 12px;
    }}
    QComboBox QAbstractItemView {{
        background: {c['surface']};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        selection-background-color: {c['hover']};
        selection-color: {c['text']};
        outline: none;
        padding: 4px;
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
        width: 18px;
        border: none;
    }}

    QListWidget, QTextEdit, QTableWidget, QTreeWidget {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: 10px;
        padding: 6px;
        gridline-color: {c['border']};
    }}
    QTreeWidget {{
        color: {c['text']};
        alternate-background-color: {c['surface_alt']};
    }}
    /* IMPORTANT: don't style QTreeWidget::branch at all — the moment you
       set even one property on it (even just background), Qt stops
       drawing the native expand arrow and expects you to supply images
       for every state (:closed, :open, etc). With no ::branch rule, the
       background under the arrow comes from the general
       QTreeWidget {{ background: ... }} rule above, and the arrow itself
       is drawn natively (meaning it's always visible, in any theme). */
    QListWidget::item {{
        border-radius: 6px;
        padding: 10px 10px;
        margin: 2px 0px;
    }}
    QListWidget::item:selected {{
        background: {c['hover']};
        color: {c['text']};
        border: 1px solid {c['primary']};
    }}
    QTableWidget::item {{
        padding: 6px 8px;
    }}
    QTreeWidget::item {{
        border-radius: 4px;
        padding: 4px 2px;
    }}
    QTreeWidget::item:hover {{
        background: {c['hover']};
    }}
    QTreeWidget::item:selected {{
        background: {c['hover']};
        color: {c['text']};
    }}

    /* ---- top menu bar (File/View/Languages) — same "never themed,
       falls back to native OS palette" story as docks/tabs/trees below,
       styled up front this time instead of discovering it later */
    QMenuBar {{
        background: {c['surface']};
        color: {c['text']};
        border-bottom: 1px solid {c['border']};
        padding: 2px 4px;
    }}
    QMenuBar::item {{
        background: transparent;
        padding: 6px 10px;
        border-radius: 6px;
    }}
    QMenuBar::item:selected {{
        background: {c['hover']};
    }}
    QMenu {{
        background: {c['surface']};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 8px 24px 8px 12px;
        border-radius: 6px;
    }}
    QMenu::item:selected {{
        background: {c['hover']};
    }}
    QMenu::separator {{
        height: 1px;
        background: {c['border']};
        margin: 4px 8px;
    }}

    /* ---- dock title bar (the strip at the top of a panel with the
       restore/close buttons) — same as QTreeWidget/QTabWidget before,
       was never part of the theme and rendered with the native OS
       palette (dark, regardless of the app's chosen theme) */
    QDockWidget {{
        color: {c['text']};
    }}
    QDockWidget::title {{
        background: {c['surface_alt']};
        color: {c['text']};
        border-bottom: 1px solid {c['border']};
        padding: 6px 8px;
    }}
    QDockWidget::close-button, QDockWidget::float-button {{
        background: transparent;
        border: none;
        padding: 2px;
    }}
    QDockWidget::close-button:hover, QDockWidget::float-button:hover {{
        background: {c['hover']};
        border-radius: 4px;
    }}

    /* ---- tabs (Code/Tree in the HTML panel etc.) ---- */
    QTabWidget::pane {{
        border: 1px solid {c['border']};
        border-radius: 8px;
        top: -1px;
        background: {c['surface']};
    }}
    QTabBar::tab {{
        background: {c['surface_alt']};
        color: {c['text_secondary']};
        border: 1px solid {c['border']};
        border-bottom: none;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        padding: 8px 18px;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        background: {c['surface']};
        color: {c['text']};
        font-weight: 600;
    }}
    QTabBar::tab:hover:!selected {{
        background: {c['hover']};
        color: {c['text']};
    }}
    QHeaderView::section {{
        background: {c['surface_alt']};
        color: {c['text_secondary']};
        border: none;
        border-bottom: 1px solid {c['border']};
        padding: 10px;
        font-weight: 600;
    }}
    /* the table's corner cell (intersection of the column headers and
       row numbers) — a separate QTableCornerButton class, NOT covered by
       the QHeaderView::section rule above, so it's styled separately */
    QTableCornerButton::section {{
        background: {c['surface_alt']};
        border: none;
        border-bottom: 1px solid {c['border']};
    }}

    QScrollBar:vertical {{
        background: transparent;
        width: 14px;
    }}
    QScrollBar::handle:vertical {{
        background: {c['border']};
        border-radius: 7px;
        min-height: 32px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    /* ---- splitter between the left panel and the browser ---- */
    QSplitter::handle {{
        background: {c['bg']};
        border-left: 1px solid {c['border']};
        border-right: 1px solid {c['border']};
        width: 4px;
    }}
    QSplitter::handle:hover {{
        background: {c['primary']};
    }}
    QSplitter::handle:pressed {{
        background: {c['primary_pressed']};
    }}

    /* ---- Chrome-like browser navigation bar ---- */
    #chromeNavBar {{
        background: {c['chrome_bar']};
        border-bottom: 1px solid {c['border']};
    }}
    #addressPill {{
        background: {c['chrome_field']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        min-height: 20px;
    }}
    #addressPill QLineEdit {{
        background: transparent;
        border: none;
        padding: 11px 6px;
        border-radius: 0px;
        font-size: 16px;
    }}
    #addressIcon {{
        color: {c['text_secondary']};
        padding-left: 14px;
        font-size: 16px;
    }}

    /* ---- browser window size/zoom settings bar ---- */
    #deviceBar {{
        background: {c['chrome_bar']};
        border-bottom: 1px solid {c['border']};
    }}
    #deviceBar QLabel {{
        color: {c['text_secondary']};
        font-size: 13px;
    }}
    #deviceCanvas {{
        background: {c['canvas_bg']};
        border: none;
    }}
    """


def qcolor(hex_str):
    from PyQt6.QtGui import QColor
    return QColor(hex_str)
    