"""
Application shell: a shared AppBar (screen switching, language, theme) +
a QStackedWidget with four pages. All shared state (theme, language, DB
connection, WebEngine HTTP profile) lives here and is passed down to the
pages via self (AppShell is passed to each page as `app`).
"""

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QIcon, QActionGroup
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QStackedWidget,
)
from PyQt6.QtWebEngineCore import QWebEngineProfile

from ..core.config import SETTINGS_PATH, APP_FULL_NAME, ICON_PATH
from ..core.i18n import (
    SUPPORTED_LANGUAGES, RTL_LANGUAGES, ACCEPT_LANGUAGE_MAP, NAVIGATOR_LOCALE_MAP,
    load_translations, detect_system_language,
)
from ..core.system_theme import detect_system_theme, apply_native_titlebar_theme
from ..core.theming import build_stylesheet
from ..web.page import HeaderInterceptor, build_live_update_script, configure_profile
from ..data import database, scenarios_repo

from .pages.scenario_editor_page import ScenarioEditorPage
from .pages.scheduler_page import SchedulerPage
from .pages.notifications_page import NotificationsPage
from .pages.database_page import DatabasePage


PAGES = [
    ("scenario_editor", "tab_scenario_editor", "📝"),
    ("scheduler", "tab_scheduler", "⏱️"),
    ("notifications", "tab_notifications", "✉️"),
    ("database", "tab_database", "🗄️"),
]


class AppShell(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_FULL_NAME)
        self.setWindowIcon(QIcon(ICON_PATH))
        self.resize(1800, 1100)

        # ---- profile settings (.ini): theme and language ----
        self.settings = QSettings(SETTINGS_PATH, QSettings.Format.IniFormat)
        saved_theme = self.settings.value("profile/theme", "")
        saved_language = self.settings.value("profile/language", "")

        self.theme = saved_theme if saved_theme in ("light", "dark") else detect_system_theme()
        self.language = (
            saved_language if saved_language in SUPPORTED_LANGUAGES else detect_system_language()
        )
        if not saved_theme:
            self.settings.setValue("profile/theme", self.theme)
        if not saved_language:
            self.settings.setValue("profile/language", self.language)
        self.settings.sync()

        self.tr_dict = load_translations(self.language)
        QApplication.instance().setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if self.language in RTL_LANGUAGES else Qt.LayoutDirection.LeftToRight
        )

        # ---- shared WebEngine profile (headers, Accept-Language, JS bridge) ----
        self.interceptor = HeaderInterceptor()
        profile = QWebEngineProfile.defaultProfile()
        profile.setUrlRequestInterceptor(self.interceptor)
        profile.setHttpAcceptLanguage(ACCEPT_LANGUAGE_MAP.get(self.language, ACCEPT_LANGUAGE_MAP["en"]))
        self._install_page_scripts()

        # ---- shared DB connection (not scenarios — those are JSON files again) ----
        self.db_conn = database.ensure_ready()
        scenarios_repo.ensure_ready()

        self.pages = {}
        self._build_ui()
        self.apply_theme()
        self.retranslate_ui()
        self._restore_geometry()

    def _restore_geometry(self):
        geometry = self.settings.value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        self.settings.setValue("window/geometry", self.saveGeometry())
        for page in self.pages.values():
            if hasattr(page, "save_splitter_state"):
                page.save_splitter_state()
        self.settings.sync()
        super().closeEvent(event)

    def t(self, key: str) -> str:
        return self.tr_dict.get(key, key)

    # ---------------- UI ----------------
    def _build_ui(self):
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setCentralWidget(central)

        # ---- top AppBar: screen switching + language + theme ----
        top_bar = QWidget()
        top_bar.setObjectName("topBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(20, 0, 20, 0)
        top_layout.setSpacing(8)

        self.page_buttons = {}
        for key, tr_key, icon in PAGES:
            btn = QPushButton(icon)
            btn.setProperty("class", "pageTabBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self.switch_page(k))
            top_layout.addWidget(btn)
            self.page_buttons[key] = btn

        top_layout.addStretch()

        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setObjectName("themeToggle")
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(self.toggle_theme)
        top_layout.addWidget(self.theme_btn)

        outer.addWidget(top_bar)

        # ---- pages ----
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, stretch=1)

        self.pages["scenario_editor"] = ScenarioEditorPage(self)
        self.pages["scheduler"] = SchedulerPage(self)
        self.pages["notifications"] = NotificationsPage(self)
        self.pages["database"] = DatabasePage(self)

        for key, _, _ in PAGES:
            self.stack.addWidget(self.pages[key])

        # docks referenced by the View menu must exist first — built
        # after the pages, not before
        self._build_menu_bar()

        self.switch_page("scenario_editor")

    def _build_menu_bar(self):
        """
        A standard Windows-style top menu bar (File/View/Languages) —
        alongside the existing custom AppBar, not replacing it. View
        reflects the visibility of the scenario editor's three docks
        (Scenario steps/Auxiliary Tools/JS console) — previously only
        reachable via the 🗔 button that lived inside that page, moved
        here so it's available regardless of which page is active.
        Languages replaces the old AppBar combo box.
        """
        menubar = self.menuBar()

        self.file_menu = menubar.addMenu("")
        self.exit_action = self.file_menu.addAction("")
        self.exit_action.triggered.connect(self.close)

        self.view_menu = menubar.addMenu("")
        editor = self.pages["scenario_editor"]
        # toggleViewAction() is a built-in Qt convenience — a ready-made
        # checkable QAction tied to the dock's visibility, with its text
        # automatically kept in sync with the dock's windowTitle()
        # (which the page's own retranslate() already updates), so no
        # extra retranslation work is needed for these three specifically
        self.view_menu.addAction(editor.left_dock.toggleViewAction())
        self.view_menu.addAction(editor.html_dock.toggleViewAction())
        self.view_menu.addAction(editor.console_dock.toggleViewAction())

        self.languages_menu = menubar.addMenu("")
        self._language_actions = {}
        lang_group = QActionGroup(self)
        lang_group.setExclusive(True)
        for code, name in SUPPORTED_LANGUAGES.items():
            action = self.languages_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(code == self.language)
            lang_group.addAction(action)
            action.triggered.connect(lambda checked, c=code: self.on_language_menu_selected(c))
            self._language_actions[code] = action

    def switch_page(self, key: str):
        self.stack.setCurrentWidget(self.pages[key])
        for k, btn in self.page_buttons.items():
            btn.setChecked(k == key)
        # the DB/scheduler pages' data can go stale while they're not visible
        if key == "database" and hasattr(self.pages["database"], "refresh"):
            self.pages["database"].refresh()
        if key == "scheduler" and hasattr(self.pages["scheduler"], "refresh"):
            self.pages["scheduler"].refresh()

    # ---------------- Theme/language (shared across all pages) ----------------
    def _install_page_scripts(self):
        """
        This used to have its own copy of the profile script setup — as a
        result, the default profile (used before the first scenario run,
        while the page hasn't been swapped for an off-the-record one yet)
        never got the resource observer (the "Cache" tab stayed empty) and
        was in general a source of drift from configure_profile(). Now
        both places that configure a profile go through the same function.
        """
        profile = QWebEngineProfile.defaultProfile()
        nav_lang = NAVIGATOR_LOCALE_MAP.get(self.language, "en-US")
        accept_lang = ACCEPT_LANGUAGE_MAP.get(self.language, ACCEPT_LANGUAGE_MAP["en"])
        configure_profile(profile, self.interceptor, accept_lang, nav_lang, self.theme)

    def apply_theme(self):
        self.setStyleSheet(build_stylesheet(self.theme))
        for w in self.findChildren(QWidget):
            w.style().unpolish(w)
            w.style().polish(w)
        apply_native_titlebar_theme(self, self.theme == "dark")
        if self.theme == "light":
            self.theme_btn.setText("🌙")
        else:
            self.theme_btn.setText("☀️")

        self._install_page_scripts()
        nav_lang = NAVIGATOR_LOCALE_MAP.get(self.language, "en-US")

        for page in self.pages.values():
            page.theme = self.theme
            page.apply_theme()
            web_view = getattr(page, "web_view", None)
            if web_view is not None:
                # build_live_update_script calls the
                # window.__qttSetTheme/__qttSetLanguage already installed
                # on the page — this actually fires the site's subscribed
                # matchMedia('change') callbacks, instead of just
                # redefining matchMedia again (which would wipe out
                # already-subscribed listeners).
                web_view.page().runJavaScript(build_live_update_script(nav_lang, self.theme))

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.settings.setValue("profile/theme", self.theme)
        self.settings.sync()
        self.apply_theme()

    def on_language_menu_selected(self, code):
        if not code or code == self.language:
            return
        self.language = code
        self.settings.setValue("profile/language", self.language)
        self.settings.sync()
        self.tr_dict = load_translations(self.language)
        QApplication.instance().setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if self.language in RTL_LANGUAGES else Qt.LayoutDirection.LeftToRight
        )
        QWebEngineProfile.defaultProfile().setHttpAcceptLanguage(
            ACCEPT_LANGUAGE_MAP.get(self.language, ACCEPT_LANGUAGE_MAP["en"])
        )
        self._install_page_scripts()
        nav_lang = NAVIGATOR_LOCALE_MAP.get(self.language, "en-US")

        self.retranslate_ui()
        for page in self.pages.values():
            page.language = self.language
            page.retranslate()
            web_view = getattr(page, "web_view", None)
            if web_view is not None:
                web_view.page().runJavaScript(build_live_update_script(nav_lang, self.theme))

    def retranslate_ui(self):
        t = self.t
        for key, tr_key, icon in PAGES:
            self.page_buttons[key].setToolTip(t(tr_key))
        self.theme_btn.setToolTip(t("tooltip_theme_toggle"))
        self.file_menu.setTitle(t("menu_file"))
        self.exit_action.setText(t("menu_exit"))
        self.view_menu.setTitle(t("menu_view"))
        self.languages_menu.setTitle(t("menu_languages"))