"""The "localStorage" tab in the HTML panel — a (read-only) view of its
contents.

The search box on top filters by key/value; clicking a column header
sorts (a built-in QTableWidget feature) — the size column sorts by
actual bytes via NumericTableWidgetItem, not the displayed string.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView

from .format_utils import format_size, NumericTableWidgetItem


class LocalStorageView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(6)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("tableSearchEdit")
        self.search_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search_edit)

        self.table = QTableWidget(0, 3)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.header_keys = ["col_key", "col_value", "col_size"]
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)

        self._all_items = []

    def setHorizontalHeaderLabels(self, labels):
        self.table.setHorizontalHeaderLabels(labels)

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
                if query in (it.get("key") or "").lower() or query in (it.get("value") or "").lower()
            ]
        self._populate(filtered)

    def _populate(self, items):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            key_item = QTableWidgetItem(item.get("key", ""))
            value_item = QTableWidgetItem(item.get("value", ""))
            value_item.setToolTip(item.get("value", ""))
            size_item = NumericTableWidgetItem(format_size(item.get("size", 0)), item.get("size", 0))
            self.table.setItem(row, 0, key_item)
            self.table.setItem(row, 1, value_item)
            self.table.setItem(row, 2, size_item)
        self.table.setSortingEnabled(True)
