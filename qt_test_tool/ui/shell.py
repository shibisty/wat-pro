"""
Оболочка приложения: общий AppBar (переключение экранов, язык, тема) +
QStackedWidget с четырьмя страницами. Всё общее состояние (тема, язык,
соединение с БД, HTTP-профиль WebEngine) живёт здесь и пробрасывается в
страницы через self (AppShell передаётся каждой странице как `app`).
"""

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox, QStackedWidget,
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

        # ---- настройки профиля (.ini): тема и язык ----
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

        # ---- общий WebEngine-профиль (заголовки, Accept-Language, JS-мост) ----
        self.interceptor = HeaderInterceptor()
        profile = QWebEngineProfile.defaultProfile()
        profile.setUrlRequestInterceptor(self.interceptor)
        profile.setHttpAcceptLanguage(ACCEPT_LANGUAGE_MAP.get(self.language, ACCEPT_LANGUAGE_MAP["en"]))
        self._install_page_scripts()

        # ---- общее соединение с БД (не сценарии — те снова JSON-файлы) ----
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

        # ---- верхний AppBar: переключение экранов + язык + тема ----
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

        self.lang_combo = QComboBox()
        self.lang_combo.setObjectName("appbarLangCombo")
        for code, name in SUPPORTED_LANGUAGES.items():
            self.lang_combo.addItem(name, code)
        idx = self.lang_combo.findData(self.language)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.currentIndexChanged.connect(self.on_language_changed)
        top_layout.addWidget(self.lang_combo)

        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setObjectName("themeToggle")
        self.theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_btn.clicked.connect(self.toggle_theme)
        top_layout.addWidget(self.theme_btn)

        outer.addWidget(top_bar)

        # ---- страницы ----
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, stretch=1)

        self.pages["scenario_editor"] = ScenarioEditorPage(self)
        self.pages["scheduler"] = SchedulerPage(self)
        self.pages["notifications"] = NotificationsPage(self)
        self.pages["database"] = DatabasePage(self)

        for key, _, _ in PAGES:
            self.stack.addWidget(self.pages[key])

        self.switch_page("scenario_editor")

    def switch_page(self, key: str):
        self.stack.setCurrentWidget(self.pages[key])
        for k, btn in self.page_buttons.items():
            btn.setChecked(k == key)
        # у страниц БД/автоматизации данные могут устареть, пока их не видно
        if key == "database" and hasattr(self.pages["database"], "refresh"):
            self.pages["database"].refresh()
        if key == "scheduler" and hasattr(self.pages["scheduler"], "refresh"):
            self.pages["scheduler"].refresh()

    # ---------------- Тема/язык (общие для всех страниц) ----------------
    def _install_page_scripts(self):
        """
        Раньше здесь была своя копия настройки скриптов профиля — из-за
        этого дефолтный профиль (используется до первого запуска сценария,
        когда ещё не подменили страницу на off-the-record) не получал
        наблюдатель за ресурсами (вкладка "Кэш" пустая) и вообще был
        источником рассинхронизации с configure_profile(). Теперь оба
        места настройки профиля идут через одну и ту же функцию.
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
                # build_live_update_script вызывает уже установленные на
                # странице window.__qttSetTheme/__qttSetLanguage — это
                # реально дёргает подписанные matchMedia('change')-колбэки
                # сайта, а не просто переопределяет matchMedia заново (что
                # обнулило бы уже подписанных слушателей).
                web_view.page().runJavaScript(build_live_update_script(nav_lang, self.theme))

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.settings.setValue("profile/theme", self.theme)
        self.settings.sync()
        self.apply_theme()

    def on_language_changed(self, index):
        code = self.lang_combo.itemData(index)
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
        self.lang_combo.setToolTip(t("tooltip_language_select"))
        self.theme_btn.setToolTip(t("tooltip_theme_toggle"))
        