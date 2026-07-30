"""
Главное окно приложения. Логика по областям ответственности вынесена в
миксины (ui/mixins/*) — сам класс отвечает только за создание виджетов
(_build_ui) и инициализацию состояния (__init__).
"""

from PyQt6.QtCore import Qt, QSettings, QTimer
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QTextEdit, QListWidget, QSplitter, QLabel,
    QFrame, QComboBox, QAbstractItemView, QScrollArea, QSpinBox,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile

from ..core.config import SETTINGS_PATH, DEVICE_PRESETS
from ..core.i18n import (
    SUPPORTED_LANGUAGES, RTL_LANGUAGES, ACCEPT_LANGUAGE_MAP,
    load_translations,
)
from ..core.system_theme import detect_system_theme
from ..core.i18n import detect_system_language
from ..core.theming import THEMES
from ..web.page import LoggingWebPage, HeaderInterceptor, AutoFitScrollArea
from ..widgets.cards import make_card
from ..widgets.html_viewer import HtmlHighlighter, HtmlCodeViewer

from .mixins.theme_lang_mixin import ThemeLangMixin
from .mixins.device_zoom_mixin import DeviceZoomMixin
from .mixins.browser_mixin import BrowserMixin
from .mixins.console_mixin import ConsoleMixin
from .mixins.scenario_mixin import ScenarioMixin


class MainWindow(
    ScenarioMixin,
    ConsoleMixin,
    DeviceZoomMixin,
    ThemeLangMixin,
    BrowserMixin,
    QMainWindow,
):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Web Automation Tools")
        self.resize(1800, 1100)

        # ---- настройки профиля (.ini): тема и язык ----
        self.settings = QSettings(SETTINGS_PATH, QSettings.Format.IniFormat)
        saved_theme = self.settings.value("profile/theme", "")
        saved_language = self.settings.value("profile/language", "")

        self.theme = saved_theme if saved_theme in ("light", "dark") else detect_system_theme()
        self.language = (
            saved_language if saved_language in SUPPORTED_LANGUAGES else detect_system_language()
        )
        # если тема/язык не были сохранены раньше — фиксируем то, что определили сейчас
        if not saved_theme:
            self.settings.setValue("profile/theme", self.theme)
        if not saved_language:
            self.settings.setValue("profile/language", self.language)
        self.settings.sync()

        self.tr_dict = load_translations(self.language)
        QApplication.instance().setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if self.language in RTL_LANGUAGES else Qt.LayoutDirection.LeftToRight
        )

        self.interceptor = HeaderInterceptor()
        profile = QWebEngineProfile.defaultProfile()
        profile.setUrlRequestInterceptor(self.interceptor)
        profile.setHttpAcceptLanguage(ACCEPT_LANGUAGE_MAP.get(self.language, ACCEPT_LANGUAGE_MAP["en"]))
        self._install_page_scripts()

        self.steps = []  # [{"js": str, "expected": str}, ...]
        self.log_entries = []  # [(text, level), ...] — храним историю, чтобы перекрасить при смене темы
        self.current_scenario_name = ""

        self._build_ui()
        self.apply_theme()
        self.retranslate_ui()

    def _build_ui(self):
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setCentralWidget(central)

        # ---- верхний AppBar (тулбар на весь экран) ----
        top_bar = QWidget()
        top_bar.setObjectName("topBar")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(20, 0, 20, 0)
        top_layout.setSpacing(8)

        self.new_scen_btn = QPushButton("＋")
        self.new_scen_btn.setProperty("class", "appbarIconBtn")
        self.new_scen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_scen_btn.clicked.connect(self.new_scenario)
        top_layout.addWidget(self.new_scen_btn)

        self.scenario_combo = QComboBox()
        self.scenario_combo.setObjectName("appbarScenarioCombo")
        top_layout.addWidget(self.scenario_combo)

        self.load_scen_btn = QPushButton()
        self.load_scen_btn.clicked.connect(self.load_selected_scenario)
        top_layout.addWidget(self.load_scen_btn)

        self.save_btn = QPushButton("💾")
        self.save_btn.setProperty("class", "appbarIconBtn")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self.save_scenario)
        top_layout.addWidget(self.save_btn)

        top_layout.addStretch()

        # ---- выбор языка ----
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

        # ---- содержимое ниже тулбара: 3 колонки сверху + консоль на всю ширину снизу ----
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        outer.addWidget(main_splitter, stretch=1)

        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(content_splitter)

        # ============ ЛЕВАЯ КОЛОНКА: HTML-код страницы (live, read-only) ============
        html_panel = QWidget()
        html_panel_layout = QVBoxLayout(html_panel)
        html_panel_layout.setContentsMargins(18, 18, 8, 18)
        html_panel_layout.setSpacing(10)

        html_card, html_card_layout = make_card("")
        self.html_section_label = QLabel()
        self.html_section_label.setProperty("class", "sectionLabel")
        html_card_layout.addWidget(self.html_section_label)

        self.html_viewer = HtmlCodeViewer()
        html_card_layout.addWidget(self.html_viewer, stretch=1)
        html_panel_layout.addWidget(html_card, stretch=1)

        self.html_highlighter = HtmlHighlighter(self.html_viewer.document(), THEMES[self.theme])

        html_panel.setMinimumWidth(320)

        # ============ СРЕДНЯЯ КОЛОНКА: инструменты + шаги сценария ============
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 18, 12, 18)
        left_layout.setSpacing(16)

        # Карточка: инструменты (заголовки, рандомайзер форм)
        tools_card, tools_layout = make_card("")
        self.headers_btn = QPushButton()
        self.headers_btn.clicked.connect(self.open_headers_dialog)
        tools_layout.addWidget(self.headers_btn)

        self.randomize_btn = QPushButton()
        self.randomize_btn.clicked.connect(self.randomize_form)
        tools_layout.addWidget(self.randomize_btn)

        left_layout.addWidget(tools_card)

        # Карточка: сценарии (теперь занимает всю освободившуюся высоту колонки)
        scenario_card, scenario_layout = make_card("")
        self.scenario_section_label = QLabel()
        self.scenario_section_label.setProperty("class", "sectionLabel")
        scenario_layout.addWidget(self.scenario_section_label)
        self._refresh_scenario_list()

        self.steps_list = QListWidget()
        self.steps_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.steps_list.setMinimumHeight(160)
        scenario_layout.addWidget(self.steps_list, stretch=1)

        step_btn_row = QHBoxLayout()
        self.add_step_btn = QPushButton("➕")
        self.add_step_btn.setProperty("class", "circleBtn")
        self.add_step_btn.clicked.connect(self.add_step)
        self.edit_step_btn = QPushButton("✏️")
        self.edit_step_btn.setProperty("class", "circleBtn")
        self.edit_step_btn.clicked.connect(self.edit_step)
        self.delete_step_btn = QPushButton("🗑️")
        self.delete_step_btn.setProperty("class", "circleBtn")
        self.delete_step_btn.clicked.connect(self.delete_step)
        self.move_up_btn = QPushButton("↑")
        self.move_up_btn.setProperty("class", "circleBtn")
        self.move_up_btn.clicked.connect(lambda: self.move_step(-1))
        self.move_down_btn = QPushButton("↓")
        self.move_down_btn.setProperty("class", "circleBtn")
        self.move_down_btn.clicked.connect(lambda: self.move_step(1))
        for b in (self.add_step_btn, self.edit_step_btn, self.delete_step_btn,
                  self.move_up_btn, self.move_down_btn):
            step_btn_row.addWidget(b)
        scenario_layout.addLayout(step_btn_row)

        run_row = QHBoxLayout()
        self.play_btn = QPushButton()
        self.play_btn.setProperty("class", "primaryBtn")
        self.play_btn.clicked.connect(self.play_scenario)
        run_row.addWidget(self.play_btn, stretch=1)
        scenario_layout.addLayout(run_row)

        left_layout.addWidget(scenario_card, stretch=1)

        left.setMinimumWidth(360)
        content_splitter.addWidget(left)

        # ============ ПРАВАЯ КОЛОНКА (браузер) ============
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Chrome-подобная панель навигации
        nav_bar = QWidget()
        nav_bar.setObjectName("chromeNavBar")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(16, 12, 16, 12)
        nav_layout.setSpacing(8)

        self.back_btn = QPushButton("←")
        self.back_btn.setProperty("class", "circleBtn")
        self.back_btn.clicked.connect(lambda: self.web_view.back())
        self.fwd_btn = QPushButton("→")
        self.fwd_btn.setProperty("class", "circleBtn")
        self.fwd_btn.clicked.connect(lambda: self.web_view.forward())
        self.reload_btn = QPushButton("⟳")
        self.reload_btn.setProperty("class", "circleBtn")
        self.reload_btn.clicked.connect(lambda: self.web_view.reload())
        nav_layout.addWidget(self.back_btn)
        nav_layout.addWidget(self.fwd_btn)
        nav_layout.addWidget(self.reload_btn)

        address_pill = QFrame()
        address_pill.setObjectName("addressPill")
        pill_layout = QHBoxLayout(address_pill)
        pill_layout.setContentsMargins(2, 0, 6, 0)
        pill_layout.setSpacing(4)
        addr_icon = QLabel("🔒")
        addr_icon.setObjectName("addressIcon")
        pill_layout.addWidget(addr_icon)
        self.address_edit = QLineEdit()
        self.address_edit.returnPressed.connect(self.navigate)
        pill_layout.addWidget(self.address_edit, stretch=1)
        nav_layout.addWidget(address_pill, stretch=1)

        self.go_btn = QPushButton()
        self.go_btn.setProperty("class", "primaryBtn")
        self.go_btn.clicked.connect(self.navigate)
        nav_layout.addWidget(self.go_btn)

        right_layout.addWidget(nav_bar)

        # ---- панель настройки размера окна (px) и зума, как в Chrome DevTools ----
        device_bar = QWidget()
        device_bar.setObjectName("deviceBar")
        device_layout = QHBoxLayout(device_bar)
        device_layout.setContentsMargins(16, 8, 16, 8)
        device_layout.setSpacing(8)

        self.device_screen_label = QLabel()
        device_layout.addWidget(self.device_screen_label)

        self.device_preset_combo = QComboBox()
        self.device_preset_combo.addItem("")  # текст плейсхолдера подставит retranslate_ui
        for preset_name in DEVICE_PRESETS:
            self.device_preset_combo.addItem(preset_name)
        self.device_preset_combo.currentIndexChanged.connect(self.on_device_preset_selected)
        device_layout.addWidget(self.device_preset_combo)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(200, 7680)
        self.width_spin.setValue(1366)
        self.width_spin.setSuffix(" px")
        self.width_spin.valueChanged.connect(self.on_device_size_changed)
        device_layout.addWidget(self.width_spin)

        device_layout.addWidget(QLabel("×"))

        self.height_spin = QSpinBox()
        self.height_spin.setRange(200, 7680)
        self.height_spin.setValue(768)
        self.height_spin.setSuffix(" px")
        self.height_spin.valueChanged.connect(self.on_device_size_changed)
        device_layout.addWidget(self.height_spin)

        device_layout.addStretch()

        self.device_zoom_label = QLabel()
        device_layout.addWidget(self.device_zoom_label)

        # Зум: выпадающий список кратно 10 + возможность ввести своё значение.
        # Первый пункт "Авто" — зум пересчитывается под доступную область сам,
        # как в Chrome DevTools; любой другой выбор/ручной ввод фиксирует зум.
        self.zoom_combo = QComboBox()
        self.zoom_combo.setEditable(True)
        self.zoom_combo.setObjectName("zoomCombo")
        self.zoom_combo.addItem("")  # "Авто" — текст подставит retranslate_ui
        for v in range(10, 201, 10):
            self.zoom_combo.addItem(f"{v}%")
        self.zoom_combo.setCurrentIndex(0)
        self.zoom_auto = True
        self.zoom_combo.activated.connect(self.on_zoom_activated)
        self.zoom_combo.lineEdit().returnPressed.connect(self.on_zoom_manual_entry)
        device_layout.addWidget(self.zoom_combo)

        right_layout.addWidget(device_bar)

        # ---- "холст": веб-вью всегда фиксированного размера (px), по центру
        # серой области; если размер больше видимой области — можно
        # прокрутить, а зум по умолчанию сам подстраивается, чтобы вся
        # страница уместилась — как device toolbar в Chrome DevTools
        self.web_view = QWebEngineView()
        page = LoggingWebPage(
            QWebEngineProfile.defaultProfile(), self.web_view, self._on_page_console_message
        )
        self.web_view.setPage(page)
        page.loadFinished.connect(self._on_page_load_finished)

        self.device_canvas = AutoFitScrollArea(self._on_canvas_resized)
        self.device_canvas.setObjectName("deviceCanvas")
        self.device_canvas.setWidgetResizable(False)
        self.device_canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.device_canvas.setWidget(self.web_view)
        self.device_canvas.setFrameShape(QFrame.Shape.NoFrame)
        right_layout.addWidget(self.device_canvas, stretch=1)

        content_splitter.addWidget(right)

        content_splitter.addWidget(html_panel)

        # С кодовой панелью справа порядок колонок: инструменты+сценарий,
        # браузер, HTML-код. Браузер по-прежнему компактнее, чем раньше,
        # ведь с фиксированным размером страницы и авто-зумом ширина панели
        # не обязана быть большой, чтобы корректно показывать сайт.
        content_splitter.setSizes([560, 660, 320])

        # ============ КОНСОЛЬ: на всю ширину, снизу ============
        console_card, console_layout = make_card("")
        console_header = QHBoxLayout()
        self.console_title = QLabel()
        self.console_title.setProperty("class", "sectionLabel")
        console_header.addWidget(self.console_title)
        console_header.addStretch()
        self.clear_console_btn = QPushButton()
        self.clear_console_btn.clicked.connect(self.clear_console)
        console_header.addWidget(self.clear_console_btn)
        console_layout.addLayout(console_header)

        console_body = QHBoxLayout()
        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        console_body.addWidget(self.console_output, stretch=1)
        console_layout.addLayout(console_body, stretch=1)

        self.console_input = QLineEdit()
        self.console_input.returnPressed.connect(self.run_console_command)
        console_layout.addWidget(self.console_input)

        console_wrapper = QWidget()
        console_wrapper_layout = QVBoxLayout(console_wrapper)
        console_wrapper_layout.setContentsMargins(18, 8, 18, 18)
        console_wrapper_layout.addWidget(console_card)
        console_wrapper.setMinimumHeight(140)

        main_splitter.addWidget(console_wrapper)
        main_splitter.setSizes([750, 220])

        # всегда фиксированный размер — сразу применяем к веб-вью
        self.web_view.setFixedSize(self.width_spin.value(), self.height_spin.value())

        # таймер live-обновления HTML-кода страницы (на случай SPA)
        self.html_poll_timer = QTimer(self)
        self.html_poll_timer.setInterval(1000)
        self.html_poll_timer.timeout.connect(self._poll_html_source)
        self._last_html_source = None