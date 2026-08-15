"""The "Cache" tab in the HTML panel — every resource the page loaded
(images/scripts/styles/fonts/XHR), with its size and a flag for whether
it was served from cache (Resource Timing API — see web/inspect_js.py).
Right-click on a row — save/open in explorer/properties (see
browser_mixin.py: _on_cache_context_menu — also has the honest disclaimer
that this isn't reading a file straight from the browser's disk cache,
but re-downloading the content from the same URL).

The search box on top filters by name/type; clicking a column header
sorts (a built-in QTableWidget feature, just enabled) — the size column
uses NumericTableWidgetItem so sorting goes by actual bytes, not by the
displayed string "244.1 KB".
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView

from .format_utils import format_size, NumericTableWidgetItem


class CacheFilesView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(6)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("tableSearchEdit")
        self.search_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search_edit)

        self.table = QTableWidget(0, 4)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.header_keys = ["col_name", "col_type", "col_size", "col_cached"]
        # Name used to be Stretch — with no floor, it shrank too
        # aggressively on a narrow panel (truncated to "wp-…",
        # "wooco…", etc). Interactive + an explicit starting width gives
        # it real room, and the user can still drag it wider/narrower by
        # hand; the short "Cached" column absorbs the remaining stretch instead.
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 220)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        # the external API stays the same as before (when the class
        # itself WAS a QTableWidget) — the calling code (browser_mixin.py,
        # scenario_editor_page.py) doesn't need to change
        self.customContextMenuRequested = self.table.customContextMenuRequested

        self._all_items = []

    def setHorizontalHeaderLabels(self, labels):
        self.table.setHorizontalHeaderLabels(labels)

    def itemAt(self, pos):
        return self.table.itemAt(pos)

    def viewport(self):
        return self.table.viewport()

    def item_data_at(self, row: int):
        item = self.table.item(row, 0)
        return item.data(1000) if item else None

    def load_items(self, items):
        if not items or (isinstance(items, dict) and "error" in items):
            items = []
        self._all_items = items
        self._apply_filter()

    def _apply_filter(self):
        query = self.search_edit.text().strip().lower()
        if not query:
            filtered = self._all_items
        else:
            filtered = [
                it for it in self._all_items
                if query in (it.get("name") or "").lower() or query in (it.get("type") or "").lower()
            ]
        self._populate(filtered)

    def _populate(self, items):
        # disable sorting while populating — otherwise QTableWidget tries
        # to sort as rows are inserted, which is both slower and can mix
        # up the order between insertRow/setItem calls
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        # heaviest resources first by default (until the user clicks a
        # header and explicitly picks a sort order)
        items = sorted(items, key=lambda x: x.get("size", 0), reverse=True)
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            name_item = QTableWidgetItem(item.get("name", ""))
            name_item.setToolTip(item.get("fullUrl", ""))
            name_item.setData(1000, item)  # for the context menu — the whole object
            type_item = QTableWidgetItem(item.get("type", ""))
            size_item = NumericTableWidgetItem(format_size(item.get("size", 0)), item.get("size", 0))
            cached_item = QTableWidgetItem("✓" if item.get("cached") else "—")
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, type_item)
            self.table.setItem(row, 2, size_item)
            self.table.setItem(row, 3, cached_item)
        self.table.setSortingEnabled(True)
        