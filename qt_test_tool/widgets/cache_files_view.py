"""Вкладка "Кэш" в HTML-панели — все ресурсы, которые страница загрузила
(картинки/скрипты/стили/шрифты/XHR), с размером и пометкой, было ли
отдано из кэша (Resource Timing API — см. web/inspect_js.py). ПКМ на
строке — сохранить/открыть в проводнике/свойства (см. browser_mixin.py:
_on_cache_context_menu — там же честная оговорка про то, что это не
прямое чтение файла из дискового кэша браузера, а повторное скачивание
содержимого по тому же URL)."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView

from .format_utils import format_size


class CacheFilesView(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(0, 4, parent)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.header_keys = ["col_name", "col_type", "col_size", "col_cached"]
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

    def load_items(self, items):
        self.setRowCount(0)
        if not items or (isinstance(items, dict) and "error" in items):
            return
        # тяжёлые ресурсы сверху — обычно это то, что интересно увидеть в первую очередь
        items = sorted(items, key=lambda x: x.get("size", 0), reverse=True)
        self.setRowCount(len(items))
        for row, item in enumerate(items):
            name_item = QTableWidgetItem(item.get("name", ""))
            name_item.setToolTip(item.get("fullUrl", ""))
            name_item.setData(1000, item)  # для контекстного меню — весь объект целиком
            type_item = QTableWidgetItem(item.get("type", ""))
            size_item = QTableWidgetItem(format_size(item.get("size", 0)))
            cached_item = QTableWidgetItem("✓" if item.get("cached") else "—")
            self.setItem(row, 0, name_item)
            self.setItem(row, 1, type_item)
            self.setItem(row, 2, size_item)
            self.setItem(row, 3, cached_item)

    def item_data_at(self, row: int):
        item = self.item(row, 0)
        return item.data(1000) if item else None
        