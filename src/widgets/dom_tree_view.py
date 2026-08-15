"""
The page content tree — the second tab of the HTML panel. Built from the
JSON returned by DOM_TREE_JS (see web/dom_tree_js.py). Emits
hoveredSelectorChanged(selector) on hovering a node — the subscriber (the
scenario editor page) highlights the corresponding element in the browser.
"""

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem, QHeaderView


class DomTreeView(QTreeWidget):
    hoveredSelectorChanged = pyqtSignal(str)  # empty string = clear the highlight

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Тег", "Содержимое"])
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        # The "Tag" column used to be fixed at 180px — on deeply nested
        # elements the indentation offset (indentation × level) ate up
        # the whole column width, and the tag text just ran off the
        # visible area (got clipped, looked like an empty row). Now:
        # smaller per-level indentation + the column fits its actual
        # content + horizontal scrolling instead of clipping.
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
        """tree_data — a dict with nodeName/attributes/content/children/upeSelector, or None/with an error key."""
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
        