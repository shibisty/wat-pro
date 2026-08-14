"""
Страница "Редактор сценариев" — то, что раньше было единственным окном
приложения. Теперь это QWidget внутри AppShell; общие вещи (тема, язык,
БД-соединение) приходят от shell, а не создаются здесь.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QTextEdit,
    QListWidget, QLabel, QFrame, QComboBox, QAbstractItemView,
    QSpinBox, QTabWidget, QMainWindow, QDockWidget, QMenu,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile

from ...core.config import DEVICE_PRESETS
from ...core.theming import THEMES, build_stylesheet
from ...web.page import LoggingWebPage
from ...web.zoomable_canvas import ZoomableWebCanvas
from ...widgets.cards import make_card
from ...widgets.html_viewer import HtmlHighlighter, HtmlCodeViewer
from ...widgets.dom_tree_view import DomTreeView
from ...widgets.local_storage_view import LocalStorageView
from ...widgets.cache_files_view import CacheFilesView
from ...widgets.history_line_edit import HistoryLineEdit

from ..mixins.device_zoom_mixin import DeviceZoomMixin
from ..mixins.browser_mixin import BrowserMixin
from ..mixins.console_mixin import ConsoleMixin
from ..mixins.scenario_mixin import ScenarioMixin


class ScenarioEditorPage(
    ScenarioMixin,
    ConsoleMixin,
    DeviceZoomMixin,
    BrowserMixin,
    QWidget,
):
    def __init__(self, app):
        super().__init__()
        self.app = app  # AppShell: даёт .t(), .theme, .language, .db_conn

        # синхронизируются с AppShell при смене темы/языка (см. apply_theme/retranslate ниже)
        self.theme = app.theme
        self.language = app.language
        self.db_conn = app.db_conn

        self.steps = []  # [{"js": str, "expected": str, "collect": bool}, ...]
        self.log_entries = []
        self.current_scenario_id = None
        self.current_scenario_name = ""

        self._build_ui()
        self.apply_theme()
        self.retranslate()

    def t(self, key: str) -> str:
        return self.app.t(key)

    # ---------------- UI ----------------
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- локальная под-панель управления сценарием: имя, URL, размер —
        # всё, что раньше жило порознь в nav_bar/device_bar, теперь рядом с
        # выбором сценария, потому что это его свойства, а не просто
        # состояние текущего сеанса браузера ----
        scen_bar = QWidget()
        scen_bar.setObjectName("pageSubBar")
        scen_layout = QHBoxLayout(scen_bar)
        scen_layout.setContentsMargins(20, 8, 20, 8)
        scen_layout.setSpacing(8)

        self.new_scen_btn = QPushButton("＋")
        self.new_scen_btn.setProperty("class", "circleBtn")
        self.new_scen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_scen_btn.clicked.connect(self.new_scenario)
        scen_layout.addWidget(self.new_scen_btn)

        self.scenario_combo = QComboBox()
        self.scenario_combo.setObjectName("appbarScenarioCombo")
        # выбор в списке сразу загружает сценарий — отдельной кнопки "Загрузить" больше нет
        # activated (не currentIndexChanged!) — срабатывает при ЛЮБОМ явном
        # выборе пользователя в списке, даже если индекс не изменился
        # (например, единственный сценарий в списке уже выбран — клик по
        # нему всё равно должен что-то делать, а currentIndexChanged в
        # таком случае вообще не сработал бы)
        self.scenario_combo.activated.connect(self.on_scenario_selected)
        scen_layout.addWidget(self.scenario_combo)

        self.edit_scen_btn = QPushButton("✏️")
        self.edit_scen_btn.setProperty("class", "circleBtn")
        self.edit_scen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_scen_btn.clicked.connect(self.edit_scenario_name)
        scen_layout.addWidget(self.edit_scen_btn)

        self.delete_scen_btn = QPushButton("🗑️")
        self.delete_scen_btn.setProperty("class", "circleBtn")
        self.delete_scen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_scen_btn.clicked.connect(self.delete_scenario)
        scen_layout.addWidget(self.delete_scen_btn)

        # стартовый URL сценария — та же адресная строка, что и для навигации
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
        scen_layout.addWidget(address_pill, stretch=1)

        self.go_btn = QPushButton()
        self.go_btn.setObjectName("goBtn")
        self.go_btn.setProperty("class", "primaryBtn")
        self.go_btn.clicked.connect(self.navigate)
        scen_layout.addWidget(self.go_btn)

        # стартовый размер окна браузера сценария (зум подстраивается сам —
        # его настройка осталась у самого браузера, не здесь)
        self.device_preset_combo = QComboBox()
        self.device_preset_combo.addItem("")  # текст плейсхолдера подставит retranslate()
        for preset_name in DEVICE_PRESETS:
            self.device_preset_combo.addItem(preset_name)
        self.device_preset_combo.currentIndexChanged.connect(self.on_device_preset_selected)
        scen_layout.addWidget(self.device_preset_combo)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(200, 7680)
        self.width_spin.setValue(1366)
        self.width_spin.setSuffix(" px")
        self.width_spin.valueChanged.connect(self.on_device_size_changed)
        scen_layout.addWidget(self.width_spin)

        scen_layout.addWidget(QLabel("×"))

        self.height_spin = QSpinBox()
        self.height_spin.setRange(200, 7680)
        self.height_spin.setValue(768)
        self.height_spin.setSuffix(" px")
        self.height_spin.valueChanged.connect(self.on_device_size_changed)
        scen_layout.addWidget(self.height_spin)

        self.panels_btn = QPushButton("🗔")
        self.panels_btn.setProperty("class", "circleBtn")
        self.panels_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.panels_btn.clicked.connect(self._show_panels_menu)
        scen_layout.addWidget(self.panels_btn)

        outer.addWidget(scen_bar)

        # ---- содержимое: встроенный QMainWindow с доками — так панели
        # получают нормальный минимальный размер при перетаскивании, кнопку
        # "закрыть", и системное меню возврата (createPopupMenu) вместо
        # риска "утащить в ноль и не найти, как вернуть" у QSplitter ----
        self.inner_window = QMainWindow()
        self.inner_window.setWindowFlags(Qt.WindowType.Widget)
        outer.addWidget(self.inner_window, stretch=1)

        # ============ ЛЕВАЯ КОЛОНКА: HTML-код страницы (live, read-only) ============
        html_panel = QWidget()
        html_panel_layout = QVBoxLayout(html_panel)
        html_panel_layout.setContentsMargins(18, 18, 8, 18)
        html_panel_layout.setSpacing(10)

        html_card, html_card_layout = make_card("")
        html_header = QHBoxLayout()
        self.html_section_label = QLabel()
        self.html_section_label.setProperty("class", "sectionLabel")
        html_header.addWidget(self.html_section_label)
        html_header.addStretch()
        self.html_refresh_btn = QPushButton()
        self.html_refresh_btn.clicked.connect(self.refresh_html_panels)
        html_header.addWidget(self.html_refresh_btn)
        html_card_layout.addLayout(html_header)

        self.html_tabs = QTabWidget()

        self.html_viewer = HtmlCodeViewer()
        self.html_tabs.addTab(self.html_viewer, "")  # текст вкладки подставит retranslate()

        self.dom_tree_view = DomTreeView()
        self.html_tabs.addTab(self.dom_tree_view, "")

        self.local_storage_view = LocalStorageView()
        self.html_tabs.addTab(self.local_storage_view, "")

        self.cache_files_view = CacheFilesView()
        self.cache_files_view.customContextMenuRequested.connect(self._on_cache_context_menu)
        self.html_tabs.addTab(self.cache_files_view, "")

        self.html_viewer.hoveredSelectorChanged.connect(self._on_hover_selector_changed)
        self.dom_tree_view.hoveredSelectorChanged.connect(self._on_hover_selector_changed)

        html_card_layout.addWidget(self.html_tabs, stretch=1)
        html_panel_layout.addWidget(html_card, stretch=1)

        self.html_highlighter = HtmlHighlighter(self.html_viewer.document(), THEMES[self.theme])

        html_panel.setMinimumWidth(280)

        # ============ СРЕДНЯЯ КОЛОНКА: инструменты + шаги сценария ============
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 18, 12, 18)
        left_layout.setSpacing(16)

        tools_card, tools_layout = make_card("")
        self.headers_btn = QPushButton()
        self.headers_btn.clicked.connect(self.open_headers_dialog)
        tools_layout.addWidget(self.headers_btn)

        self.randomize_btn = QPushButton()
        self.randomize_btn.clicked.connect(self.randomize_form)
        tools_layout.addWidget(self.randomize_btn)

        left_layout.addWidget(tools_card)

        scenario_card, scenario_layout = make_card("")
        self.scenario_section_label = QLabel()
        self.scenario_section_label.setProperty("class", "sectionLabel")
        scenario_layout.addWidget(self.scenario_section_label)
        self._refresh_scenario_list()

        self.steps_list = QListWidget()
        # ExtendedSelection даёт Ctrl+клик (добавить/убрать по одному) и
        # Shift+клик (диапазон между уже выделенным и новым) "из коробки"
        self.steps_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.steps_list.setMinimumHeight(160)
        self.steps_list.itemDoubleClicked.connect(lambda item: self.edit_step())
        scenario_layout.addWidget(self.steps_list, stretch=1)

        # Delete — удалить выделенные шаги; Ctrl+Z — вернуть последнее
        # изменение списка шагов. WidgetShortcut — срабатывают только когда
        # список шагов реально в фокусе, не мешают Ctrl+Z в текстовых полях
        delete_shortcut = QShortcut(QKeySequence.StandardKey.Delete, self.steps_list)
        delete_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        delete_shortcut.activated.connect(self.delete_step)

        undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self.steps_list)
        undo_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        undo_shortcut.activated.connect(self.undo_steps)

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

        self.pause_btn = QPushButton("⏸")
        self.pause_btn.setProperty("class", "circleBtn")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self.pause_scenario)
        run_row.addWidget(self.pause_btn)

        self.resume_btn = QPushButton("↻")
        self.resume_btn.setProperty("class", "circleBtn")
        self.resume_btn.setEnabled(False)
        self.resume_btn.clicked.connect(self.resume_scenario)
        run_row.addWidget(self.resume_btn)

        scenario_layout.addLayout(run_row)

        left_layout.addWidget(scenario_card, stretch=1)

        left.setMinimumWidth(280)

        self.left_dock = QDockWidget()
        self.left_dock.setObjectName("leftDock")
        self.left_dock.setWindowTitle("")  # подставит retranslate()
        self.left_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.left_dock.setWidget(left)
        self.left_dock.setMinimumWidth(280)
        self.inner_window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.left_dock)

        # ============ ПРАВАЯ КОЛОНКА (браузер) ============
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

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

        self.record_btn = QPushButton("⏺")
        self.record_btn.setProperty("class", "circleBtn")
        self.record_btn.setProperty("recording", "false")
        self.record_btn.clicked.connect(self.toggle_recording)
        nav_layout.addWidget(self.record_btn)

        nav_layout.addStretch()

        # зум — единственное, что осталось "живой" настройкой браузера, а
        # не свойством сценария: он сам подстраивается по ходу (auto-fit),
        # ручной выбор здесь же, рядом с остальными live-контролами
        self.device_zoom_label = QLabel()
        nav_layout.addWidget(self.device_zoom_label)

        self.zoom_combo = QComboBox()
        self.zoom_combo.setEditable(True)
        self.zoom_combo.setObjectName("zoomCombo")
        self.zoom_combo.addItem("")
        for v in range(10, 201, 10):
            self.zoom_combo.addItem(f"{v}%")
        self.zoom_combo.setCurrentIndex(0)
        self.zoom_auto = True
        self.zoom_combo.activated.connect(self.on_zoom_activated)
        self.zoom_combo.lineEdit().returnPressed.connect(self.on_zoom_manual_entry)
        nav_layout.addWidget(self.zoom_combo)

        right_layout.addWidget(nav_bar)

        self.web_view = QWebEngineView()
        page = LoggingWebPage(
            QWebEngineProfile.defaultProfile(), self.web_view, self._on_page_console_message
        )
        self.web_view.setPage(page)
        page.loadFinished.connect(self._on_page_load_finished)

        self.device_canvas = ZoomableWebCanvas(self.web_view, self._on_canvas_resized)
        self.device_canvas.setObjectName("deviceCanvas")
        right_layout.addWidget(self.device_canvas, stretch=1)

        self.inner_window.setCentralWidget(right)

        self.html_dock = QDockWidget()
        self.html_dock.setObjectName("htmlDock")
        self.html_dock.setWindowTitle("")  # подставит retranslate()
        self.html_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.html_dock.setWidget(html_panel)
        self.html_dock.setMinimumWidth(280)
        self.inner_window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.html_dock)

        # ============ КОНСОЛЬ: снизу, тоже док ============
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

        self.console_input = HistoryLineEdit()
        self.console_input.returnPressed.connect(self.run_console_command)
        console_layout.addWidget(self.console_input)

        console_wrapper = QWidget()
        console_wrapper_layout = QVBoxLayout(console_wrapper)
        console_wrapper_layout.setContentsMargins(18, 8, 18, 18)
        console_wrapper_layout.addWidget(console_card)
        console_wrapper.setMinimumHeight(120)

        self.console_dock = QDockWidget()
        self.console_dock.setObjectName("consoleDock")
        self.console_dock.setWindowTitle("")  # подставит retranslate()
        self.console_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.console_dock.setWidget(console_wrapper)
        self.console_dock.setMinimumHeight(120)
        self.inner_window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.console_dock)

        # если пользователь открепит панель уже ПОСЛЕ применения темы —
        # подстрахуемся и перепримени́м стиль сразу в момент открепления
        for dock in (self.left_dock, self.html_dock, self.console_dock):
            dock.topLevelChanged.connect(lambda floating, d=dock: self._on_dock_float_changed(d))

        self.web_view.setFixedSize(self.width_spin.value(), self.height_spin.value())
        self.device_canvas.update_content_size()

        self._last_html_source = None

        self._restore_dock_state()

    def _show_panels_menu(self):
        """
        Системное меню возврата панелей — используем стандартный
        createPopupMenu() от QMainWindow: он сам строит чек-лист всех
        доков (с текущим состоянием видимости), включая те, что были
        закрыты/утащены в ноль — выбор пункта возвращает панель с её
        нормальным минимальным размером, а не нулевым.
        """
        menu = self.inner_window.createPopupMenu()
        if menu is None:
            menu = QMenu(self)
        menu.exec(self.panels_btn.mapToGlobal(self.panels_btn.rect().bottomLeft()))

    def _restore_dock_state(self):
        state = self.app.settings.value("window/dock_state")
        if state is not None:
            self.inner_window.restoreState(state)

    def save_splitter_state(self):
        """Имя сохранено для обратной совместимости вызова из shell.closeEvent()."""
        self.app.settings.setValue("window/dock_state", self.inner_window.saveState())

    # ---------------- Тема/язык (вызывается из AppShell) ----------------
    def _on_dock_float_changed(self, dock):
        stylesheet = build_stylesheet(self.theme)
        dock.setStyleSheet(stylesheet)
        for w in dock.findChildren(QWidget):
            w.style().unpolish(w)
            w.style().polish(w)

    def apply_theme(self):
        c = THEMES[self.theme]
        self.web_view.page().setBackgroundColor(QColor(c["surface"]))
        if hasattr(self, "console_output"):
            self._rerender_console()
        if hasattr(self, "html_viewer"):
            self.html_viewer.set_editor_colors(
                c["code_bg"], c["code_text"], c["code_linenum_bg"], c["code_linenum_text"]
            )
            self.html_highlighter.set_colors(c)
        # проброс темы в саму страницу браузера делает AppShell (общий профиль)

        # Открепленная (floating) панель дока становится отдельным
        # top-level окном Qt — QSS главного окна на неё НЕ каскадируется
        # (это общее ограничение Qt, не баг конкретно нашего кода), поэтому
        # применяем стиль явно к каждому доку, а не только к shell.
        stylesheet = build_stylesheet(self.theme)
        for dock in (self.left_dock, self.html_dock, self.console_dock):
            dock.setStyleSheet(stylesheet)
            for w in dock.findChildren(QWidget):
                w.style().unpolish(w)
                w.style().polish(w)

    def retranslate(self):
        t = self.t
        self.new_scen_btn.setToolTip(t("tooltip_new_scenario"))
        self.scenario_combo.setToolTip(t("tooltip_scenario_select"))
        self.edit_scen_btn.setToolTip(t("tooltip_edit_scenario"))
        self.delete_scen_btn.setToolTip(t("tooltip_delete_scenario"))
        self.panels_btn.setToolTip(t("tooltip_panels"))

        self.headers_btn.setText("⚙  " + t("btn_headers"))
        self.randomize_btn.setText("🎲  " + t("btn_randomize_form"))
        self.randomize_btn.setToolTip(t("tooltip_randomize_form"))

        self.scenario_section_label.setText(t("section_scenario_steps"))
        self.left_dock.setWindowTitle(t("section_scenario_steps"))
        self.add_step_btn.setToolTip(t("tooltip_add_step"))
        self.edit_step_btn.setToolTip(t("tooltip_edit_step"))
        self.delete_step_btn.setToolTip(t("tooltip_delete_step"))
        self.move_up_btn.setToolTip(t("tooltip_move_up"))
        self.move_down_btn.setToolTip(t("tooltip_move_down"))
        self.play_btn.setText("▶  " + t("btn_play"))
        self.pause_btn.setToolTip(t("tooltip_pause_scenario"))
        self.resume_btn.setToolTip(t("tooltip_resume_scenario"))

        self.console_title.setText(t("section_console"))
        self.console_dock.setWindowTitle(t("section_console"))
        self.clear_console_btn.setText("🗑  " + t("btn_clear_console"))
        self.console_input.setPlaceholderText(t("console_placeholder"))

        self.back_btn.setToolTip(t("tooltip_back"))
        self.fwd_btn.setToolTip(t("tooltip_forward"))
        self.reload_btn.setToolTip(t("tooltip_reload"))
        self.address_edit.setPlaceholderText(t("address_placeholder"))
        self.go_btn.setText(t("btn_go"))
        self.record_btn.setToolTip(t("tooltip_record"))

        self.device_preset_combo.setItemText(0, t("device_preset_placeholder"))
        self.device_zoom_label.setText(t("device_label_zoom"))
        self.zoom_combo.blockSignals(True)
        self.zoom_combo.setItemText(0, t("zoom_auto"))
        if self.zoom_auto:
            self.zoom_combo.setEditText(t("zoom_auto"))
        self.zoom_combo.blockSignals(False)

        self.html_section_label.setText(t("section_html_source"))
        self.html_dock.setWindowTitle(t("section_html_source"))
        self.html_refresh_btn.setText("🔄  " + t("btn_refresh"))
        self.html_tabs.setTabText(0, t("tab_code"))
        self.html_tabs.setTabText(1, t("tab_tree"))
        self.html_tabs.setTabText(2, t("tab_localstorage"))
        self.html_tabs.setTabText(3, t("tab_cache"))
        self.local_storage_view.setHorizontalHeaderLabels([t(k) for k in self.local_storage_view.header_keys])
        self.cache_files_view.setHorizontalHeaderLabels([t(k) for k in self.cache_files_view.header_keys])
        