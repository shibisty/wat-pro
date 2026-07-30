"""
Дерево контента страницы — вторая вкладка HTML-панели. Строится из JSON,
который возвращает DOM_TREE_JS (см. web/dom_tree_js.py). При наведении на
узел эмитит hoveredSelectorChanged(selector) — подписчик (страница
редактора сценариев) подсвечивает соответствующий элемент в браузере.
"""

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem, QHeaderView


class DomTreeView(QTreeWidget):
    hoveredSelectorChanged = pyqtSignal(str)  # пустая строка = снять подсветку

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Тег", "Содержимое"])
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        # Раньше колонка "Тег" была зафиксирована на 180px — на глубоко
        # вложенных элементах отступ вложенности (indentation × уровень)
        # съедал всю ширину колонки, и текст тега просто уезжал за
        # видимую область (обрезался, выглядело как пустая строка).
        # Теперь: меньший отступ на уровень + колонка подгоняется под
        # реальное содержимое + горизонтальный скролл вместо обрезания.
        self.setIndentation(14)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setUniformRowHeights(True)

        self.itemEntered.connect(self._on_item_entered)
        self._current_selector = ""

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._current_selector = ""
        self.hoveredSelectorChanged.emit("")

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        item = self.itemAt(event.pos())
        if item is None:
            if self._current_selector:
                self._current_selector = ""
                self.hoveredSelectorChanged.emit("")
            return
        self._on_item_entered(item, 0)

    def _on_item_entered(self, item, column):
        selector = item.data(0, 1000) or ""
        if selector == self._current_selector:
            return
        self._current_selector = selector
        self.hoveredSelectorChanged.emit(selector)

    def load_tree(self, tree_data):
        """tree_data — словарь nodeName/attributes/content/children/upeSelector, или None/с ключом error."""
        self.clear()
        if not tree_data or "error" in tree_data:
            return
        root_item = self._build_item(tree_data)
        self.addTopLevelItem(root_item)
        root_item.setExpanded(True)

    def _build_item(self, node: dict) -> QTreeWidgetItem:
        attrs = node.get("attributes") or []
        attrs_preview = " ".join(
            f'{a["name"]}="{a["value"]}"' for a in attrs
            if not str(a.get("value", "")).startswith("upe-node-") and a["name"] != "class"
        )
        tag_label = node.get("nodeName", "?").lower()
        if attrs_preview:
            tag_label += f" [{attrs_preview}]"

        content = (node.get("content") or "").strip()
        content_preview = (content[:80] + "…") if len(content) > 80 else content

        item = QTreeWidgetItem([tag_label, content_preview])
        item.setData(0, 1000, node.get("upeSelector", ""))
        item.setToolTip(0, tag_label)
        if content:
            item.setToolTip(1, content)

        for child in node.get("children") or []:
            if not child:
                continue
            item.addChild(self._build_item(child))
        return item
        