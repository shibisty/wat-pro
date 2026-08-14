"""Вкладка "localStorage" в HTML-панели — просмотр (read-only) содержимого."""

from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView

from .format_utils import format_size


class LocalStorageView(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(0, 3, parent)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.header_keys = ["col_key", "col_value", "col_size"]
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

    def load_items(self, items):
        self.setRowCount(0)
        if not items or (isinstance(items, dict) and "error" in items):
            return
        self.setRowCount(len(items))
        for row, item in enumerate(items):
            key_item = QTableWidgetItem(item.get("key", ""))
            value_item = QTableWidgetItem(item.get("value", ""))
            value_item.setToolTip(item.get("value", ""))
            size_item = QTableWidgetItem(format_size(item.get("size", 0)))
            self.setItem(row, 0, key_item)
            self.setItem(row, 1, value_item)
            self.setItem(row, 2, size_item)
            