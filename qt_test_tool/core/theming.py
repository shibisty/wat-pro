"""
Палитры тем (light/dark) в духе Material UI и генератор QSS-стилей для
всего приложения.
"""

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

    /* ---- верхний AppBar ---- */
    #topBar {{
        background: {c['appbar_bg']};
        min-height: 64px;
        max-height: 64px;
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

    /* ---- кнопки переключения экранов в AppBar ---- */
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

    /* локальная под-панель страницы (например, управление сценарием) */
    #pageSubBar {{
        background: {c['chrome_bar']};
        border-bottom: 1px solid {c['border']};
    }}

    /* поле выбора сценария внутри AppBar */
    #appbarScenarioCombo {{
        min-width: 200px;
    }}
    #appbarLangCombo {{
        min-width: 130px;
    }}

    /* ---- карточки-панели слева ---- */
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

    /* ---- обычные кнопки (MUI outlined) ---- */
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

    /* ---- главная кнопка (MUI contained primary) ---- */
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
    /* компактная высота — под рост соседних полей ввода, а не стандартная кнопка */
    QPushButton#goBtn {{
        padding: 11px 18px;
        border: 1px solid transparent;
        min-height: 20px;
        max-height: 20px;
    }}

    /* ---- круглые icon-кнопки браузера (back/forward/reload) ---- */
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

    /* ---- поля ввода ---- */
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
    QComboBox::drop-down {{
        border: none;
        width: 30px;
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
    QTreeWidget::branch {{
        background: {c['surface']};
    }}
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

    /* ---- вкладки (Код/Дерево в HTML-панели и т.п.) ---- */
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

    /* ---- разделитель между левой панелью и браузером ---- */
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

    /* ---- Chrome-подобная панель навигации браузера ---- */
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

    /* ---- панель настройки размера/зума окна браузера ---- */
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
    