"""
"Scenario editor" page — what used to be the app's only window. Now it's
a QWidget inside AppShell; shared things (theme, language, DB connection)
come from the shell, not created here.
"""

from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import QColor, QShortcut, QKeySequence
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QTextEdit,
    QListWidget, QLabel, QFrame, QComboBox, QAbstractItemView,
    QSpinBox, QTabWidget, QMainWindow, QDockWidget,
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
        self.app = app  # AppShell: provides .t(), .theme, .language, .db_conn

        # kept in sync with AppShell on theme/language change (see apply_theme/retranslate below)
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

        # Read saved side-dock widths NOW, before building anything —
        # see _restore_dock_state() for the long version of why: applying
        # a saved width AFTER the window's first layout pass has already
        # happened turned out to be unreliable (both resizeDocks() and a
        # temporary minimumWidth bump failed to actually take effect).
        # Baking it into the widgets' initial minimumWidth instead means
        # Qt accounts for it on the very first, natural layout pass,
        # rather than us fighting an already-settled one afterward.
        self._initial_left_width = self.app.settings.value("window/left_dock_width", 280, type=int) or 280
        self._initial_right_width = self.app.settings.value("window/right_dock_width", 280, type=int) or 280

        # scenario_combo/edit_scen_btn/delete_scen_btn are created here
        # (this is where their state/logic lives, via ScenarioMixin) but
        # NOT placed in this page's own layout — AppShell picks them up
        # into its top AppBar, next to the page-switch icons (see
        # shell.py's _build_ui). new_scen_btn's old spot is now
        # File → Create scenario in the menu bar instead of a button here.
        self.scenario_combo = QComboBox()
        self.scenario_combo.setObjectName("appbarScenarioCombo")
        # selecting in the list loads the scenario immediately — there's
        # no separate "Load" button anymore
        # activated (NOT currentIndexChanged!) — fires on ANY explicit
        # user selection in the list, even if the index didn't change
        # (e.g. the only scenario in the list is already selected —
        # clicking it should still do something, but currentIndexChanged
        # wouldn't fire at all in that case)
        self.scenario_combo.activated.connect(self.on_scenario_selected)

        self.edit_scen_btn = QPushButton("✏️")
        self.edit_scen_btn.setProperty("class", "circleBtn")
        self.edit_scen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_scen_btn.clicked.connect(self.edit_scenario_name)

        self.delete_scen_btn = QPushButton("🗑️")
        self.delete_scen_btn.setProperty("class", "circleBtn")
        self.delete_scen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_scen_btn.clicked.connect(self.delete_scenario)

        # ---- content: an embedded QMainWindow with docks — this way
        # panels get a proper minimum size when dragged, a "close"
        # button, and a system menu to bring them back (createPopupMenu)
        # instead of the risk of "dragged to zero and no way to find it
        # again" that QSplitter has ----
        self.inner_window = QMainWindow()
        self.inner_window.setWindowFlags(Qt.WindowType.Widget)
        outer.addWidget(self.inner_window, stretch=1)

        # ============ LEFT COLUMN: page HTML source (live, read-only) ============
        html_panel = QWidget()
        html_panel_layout = QVBoxLayout(html_panel)
        html_panel_layout.setContentsMargins(18, 8, 8, 18)
        html_panel_layout.setSpacing(10)

        html_card, html_card_layout = make_card("")
        html_card_layout.setContentsMargins(18, 6, 18, 18)
        html_header = QHBoxLayout()
        html_header.addStretch()
        self.html_refresh_btn = QPushButton()
        self.html_refresh_btn.clicked.connect(self.refresh_html_panels)
        html_header.addWidget(self.html_refresh_btn)
        html_card_layout.addLayout(html_header)

        self.html_tabs = QTabWidget()

        self.html_viewer = HtmlCodeViewer()
        self.html_tabs.addTab(self.html_viewer, "")  # tab text set by retranslate()

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

        html_panel.setMinimumWidth(self._initial_right_width)

        # ============ MIDDLE COLUMN: tools + scenario steps ============
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
        scenario_layout.setContentsMargins(18, 6, 18, 18)
        self._refresh_scenario_list()

        self.steps_list = QListWidget()
        # ExtendedSelection gives Ctrl+click (add/remove one at a time) and
        # Shift+click (range between the last-selected item and the new one) out of the box
        self.steps_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.steps_list.setMinimumHeight(160)
        self.steps_list.itemDoubleClicked.connect(lambda item: self.edit_step())
        scenario_layout.addWidget(self.steps_list, stretch=1)

        # Delete — remove selected steps; Ctrl+Z — undo the last change to
        # the step list. WidgetShortcut — only fires when the steps list
        # actually has focus, doesn't interfere with Ctrl+Z in text fields
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

        left.setMinimumWidth(self._initial_left_width)

        self.left_dock = QDockWidget()
        self.left_dock.setObjectName("leftDock")
        self.left_dock.setWindowTitle("")  # set by retranslate()
        self.left_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.left_dock.setWidget(left)
        self.left_dock.setMinimumWidth(280)
        self.inner_window.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.left_dock)

        # ============ RIGHT COLUMN (browser) ============
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

        # address bar — the browser session's current URL (not necessarily
        # the same as the scenario's start URL — that one is set separately
        # in the scenario create/edit dialog)
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
        self.go_btn.setObjectName("goBtn")
        self.go_btn.setProperty("class", "primaryBtn")
        self.go_btn.clicked.connect(self.navigate)
        nav_layout.addWidget(self.go_btn)

        # browser window size — also a "live" setting for the current
        # session; the scenario's start size is set separately in its own
        # dialog, these fields just reflect/change the current state
        self.device_preset_combo = QComboBox()
        self.device_preset_combo.addItem("")  # placeholder text set by retranslate()
        for preset_name in DEVICE_PRESETS:
            self.device_preset_combo.addItem(preset_name)
        self.device_preset_combo.currentIndexChanged.connect(self.on_device_preset_selected)
        nav_layout.addWidget(self.device_preset_combo)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(200, 7680)
        self.width_spin.setValue(1366)
        self.width_spin.setSuffix(" px")
        self.width_spin.valueChanged.connect(self.on_device_size_changed)
        nav_layout.addWidget(self.width_spin)

        nav_layout.addWidget(QLabel("×"))

        self.height_spin = QSpinBox()
        self.height_spin.setRange(200, 7680)
        self.height_spin.setValue(768)
        self.height_spin.setSuffix(" px")
        self.height_spin.valueChanged.connect(self.on_device_size_changed)
        nav_layout.addWidget(self.height_spin)

        nav_layout.addStretch()

        # zoom — the only thing that's still a "live" browser setting and
        # not a scenario property: it auto-adjusts as you go (auto-fit),
        # manual override lives right here, next to the other live controls
        self.device_zoom_label = QLabel()
        nav_layout.addWidget(self.device_zoom_label)

        self.zoom_combo = QComboBox()
        self.zoom_combo.setEditable(True)
        self.zoom_combo.setObjectName("zoomCombo")
        self.zoom_combo.setMinimumWidth(130)
        self.zoom_combo.addItem("")
        for v in range(10, 201, 10):
            self.zoom_combo.addItem(f"{v}%")
        self.zoom_combo.setCurrentIndex(0)
        self.zoom_auto = True
        self.zoom_combo.activated.connect(self.on_zoom_activated)
        self.zoom_combo.lineEdit().returnPressed.connect(self.on_zoom_manual_entry)
        nav_layout.addWidget(self.zoom_combo)

        # nav_bar is inserted into the page-wide `outer` layout (not
        # right_layout) further down, once it's fully built — it now
        # spans the full page width, in the spot that used to hold
        # scen_bar, rather than being nested inside just the browser
        # column. See the outer.insertWidget(0, nav_bar) call below.
        outer.insertWidget(0, nav_bar)

        self.web_view = QWebEngineView()
        page = LoggingWebPage(
            QWebEngineProfile.defaultProfile(), self.web_view, self._on_page_console_message
        )
        self.web_view.setPage(page)
        page.loadFinished.connect(self._on_page_load_finished)
        page.urlChanged.connect(self._on_page_url_changed)
        page.bridge.dataInserted.connect(self._on_bridge_insert)

        # Load about:blank right away — without this the page never goes
        # through a single real navigation cycle, and DocumentCreation
        # script injection (theme/lang, g$/g_, InsertToDB, resource
        # observer) only fires together with navigation. Without this
        # line, a user who opens the app and immediately types something
        # in the JS console before navigating to a real site would see
        # "g$ is not defined" — not a bug specific to g$/g_, but a general
        # property of a page that's never been "lived through" yet.
        page.load(QUrl("about:blank"))

        self.device_canvas = ZoomableWebCanvas(self.web_view, self._on_canvas_resized)
        self.device_canvas.setObjectName("deviceCanvas")
        right_layout.addWidget(self.device_canvas, stretch=1)

        self.inner_window.setCentralWidget(right)

        self.html_dock = QDockWidget()
        self.html_dock.setObjectName("htmlDock")
        self.html_dock.setWindowTitle("")  # set by retranslate()
        self.html_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.html_dock.setWidget(html_panel)
        self.html_dock.setMinimumWidth(280)
        self.inner_window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.html_dock)

        # ============ CONSOLE: at the bottom, also a dock ============
        console_card, console_layout = make_card("")
        console_layout.setContentsMargins(0, 6, 0, 18)  # no side padding — see below
        console_header = QHBoxLayout()
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

        console_input_row = QHBoxLayout()
        self.console_input = HistoryLineEdit()
        self.console_input.returnPressed.connect(self.run_console_command)
        console_input_row.addWidget(self.console_input, stretch=1)
        self.clear_console_input_btn = QPushButton("✕")
        self.clear_console_input_btn.setProperty("class", "circleBtn")
        self.clear_console_input_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_console_input_btn.clicked.connect(self.console_input.clear)
        console_input_row.addWidget(self.clear_console_input_btn)
        console_layout.addLayout(console_input_row)

        console_wrapper = QWidget()
        console_wrapper_layout = QVBoxLayout(console_wrapper)
        console_wrapper_layout.setContentsMargins(0, 8, 0, 18)  # side padding removed here too
        console_wrapper_layout.addWidget(console_card)
        console_wrapper.setMinimumHeight(120)

        self.console_dock = QDockWidget()
        self.console_dock.setObjectName("consoleDock")
        self.console_dock.setWindowTitle("")  # set by retranslate()
        self.console_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.console_dock.setWidget(console_wrapper)
        self.console_dock.setMinimumHeight(120)
        self.inner_window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.console_dock)

        # if a user undocks a panel AFTER the theme was applied — re-apply
        # the stylesheet right at the moment it floats, just in case
        for dock in (self.left_dock, self.html_dock, self.console_dock):
            dock.topLevelChanged.connect(lambda floating, d=dock: self._on_dock_float_changed(d))

        self.web_view.setFixedSize(self.width_spin.value(), self.height_spin.value())
        self.device_canvas.update_content_size()

        self._last_html_source = None

        # Deferred, not called directly: at this point the window hasn't
        # actually been shown yet (show() happens later, outside the
        # constructor) — restoreState() on a window with no real geometry
        # yet can miscalculate splitter proportions, which then get
        # silently overwritten once Qt does its real layout pass on
        # first show. QTimer.singleShot(0, ...) runs this right after the
        # event loop processes the initial show/layout event instead.
        QTimer.singleShot(0, self._restore_dock_state)

        # The saved width was baked into left/html_panel's initial
        # minimumWidth above so Qt honors it on the very first layout
        # pass. Left as-is forever, it would permanently prevent shrinking
        # the panel below whatever was last saved. Once that first pass
        # has settled (long enough after show that it reliably has, on a
        # real window — unlike trying to push a size onto an
        # already-settled layout, which is what didn't work before),
        # lower the minimum back to the true floor so the user can resize
        # freely again; the panel's current (already correct) width isn't
        # affected by lowering a minimum.
        def _release_min_width():
            left.setMinimumWidth(280)
            html_panel.setMinimumWidth(280)
        QTimer.singleShot(600, _release_min_width)

    def _restore_dock_state(self):
        # Corners must be set BEFORE restoreState, not after — setting
        # them afterward forces Qt to recompute the dock layout for the
        # new corner ownership, which was silently discarding the
        # restored panel sizes (the actual cause of "sizes revert after
        # closing the app"). Setting them first means restoreState()
        # applies the saved sizes on top of the already-correct structure.
        self.inner_window.setCorner(Qt.Corner.BottomLeftCorner, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.inner_window.setCorner(Qt.Corner.BottomRightCorner, Qt.DockWidgetArea.RightDockWidgetArea)

        # A dock_state saved by an OLDER version of the app (before this
        # corner fix existed) may have baked in the wrong corner
        # ownership as part of its serialized bytes — restoring it would
        # just drag the layout back to the old, wrong arrangement. Skip
        # it exactly once (falling back to the correct default layout),
        # then bump the marker so every save/restore after that is normal.
        layout_version = self.app.settings.value("window/dock_layout_version", 0, type=int)
        if layout_version < 2:
            self.app.settings.setValue("window/dock_layout_version", 2)
            return

        state = self.app.settings.value("window/dock_state")
        if state is not None:
            self.inner_window.restoreState(state)

        # Note: left/right dock width restoration no longer happens here.
        # Trying to push a width onto the docks AFTER this point (via
        # resizeDocks() or a temporary minimumWidth bump) turned out to
        # be unreliable — the saved width is instead baked into
        # left/html_panel's initial minimumWidth back in _build_ui(),
        # before the window's first layout pass ever happens.

    def save_splitter_state(self):
        """Name kept for backward compatibility with the call from shell.closeEvent()."""
        self.app.settings.setValue("window/dock_state", self.inner_window.saveState())
        # See _restore_dock_state() — explicit width persistence for the
        # side docks, since restoreState() alone doesn't reliably bring
        # these back.
        self.app.settings.setValue("window/left_dock_width", self.left_dock.width())
        self.app.settings.setValue("window/right_dock_width", self.html_dock.width())

    # ---------------- Theme/language (called from AppShell) ----------------
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
        # theme propagation into the browser page itself is handled by AppShell (shared profile)

        # A floating (undocked) dock panel becomes a separate top-level Qt
        # window — the main window's QSS does NOT cascade to it (a general
        # Qt limitation, not a bug specific to our code), so we apply the
        # stylesheet explicitly to each dock, not just to the shell.
        stylesheet = build_stylesheet(self.theme)
        for dock in (self.left_dock, self.html_dock, self.console_dock):
            dock.setStyleSheet(stylesheet)
            for w in dock.findChildren(QWidget):
                w.style().unpolish(w)
                w.style().polish(w)

    def retranslate(self):
        t = self.t
        self.scenario_combo.setToolTip(t("tooltip_scenario_select"))
        if self.scenario_combo.count() > 0:
            self.scenario_combo.setItemText(0, t("placeholder_choose_scenario"))
        self.edit_scen_btn.setToolTip(t("tooltip_edit_scenario"))
        self.delete_scen_btn.setToolTip(t("tooltip_delete_scenario"))
        # (panels_btn removed — panel visibility now lives in the top menu bar's View menu)

        self.headers_btn.setText("⚙  " + t("btn_headers"))
        self.randomize_btn.setText("🎲  " + t("btn_randomize_form"))
        self.randomize_btn.setToolTip(t("tooltip_randomize_form"))

        self.left_dock.setWindowTitle(t("section_scenario_steps"))
        self.add_step_btn.setToolTip(t("tooltip_add_step"))
        self.edit_step_btn.setToolTip(t("tooltip_edit_step"))
        self.delete_step_btn.setToolTip(t("tooltip_delete_step"))
        self.move_up_btn.setToolTip(t("tooltip_move_up"))
        self.move_down_btn.setToolTip(t("tooltip_move_down"))
        self.play_btn.setText("▶  " + t("btn_play"))
        self.pause_btn.setToolTip(t("tooltip_pause_scenario"))
        self.resume_btn.setToolTip(t("tooltip_resume_scenario"))

        self.console_dock.setWindowTitle(t("section_console"))
        self.clear_console_input_btn.setToolTip(t("tooltip_clear_console_input"))
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

        self.html_dock.setWindowTitle(t("section_auxiliary_tools"))
        self.html_refresh_btn.setText("🔄  " + t("btn_refresh"))
        self.html_tabs.setTabText(0, t("tab_code"))
        self.html_tabs.setTabText(1, t("tab_tree"))
        self.html_tabs.setTabText(2, t("tab_localstorage"))
        self.html_tabs.setTabText(3, t("tab_cache"))
        self.local_storage_view.setHorizontalHeaderLabels([t(k) for k in self.local_storage_view.header_keys])
        self.cache_files_view.setHorizontalHeaderLabels([t(k) for k in self.cache_files_view.header_keys])
        self.local_storage_view.search_edit.setPlaceholderText(t("placeholder_table_search"))
        self.cache_files_view.search_edit.setPlaceholderText(t("placeholder_table_search"))
        