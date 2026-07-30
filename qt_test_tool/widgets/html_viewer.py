"""
Просмотрщик HTML-кода страницы: подсветка синтаксиса, номера строк,
только для чтения (без редактирования). Плюс лёгкий pretty-printer для
сериализованного HTML, который возвращает page.toHtml().
"""

import re

from PyQt6.QtCore import Qt, QSize, QRect, QRegularExpression, pyqtSignal
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QTextCharFormat, QSyntaxHighlighter, QTextCursor, QTextFormat
)
from PyQt6.QtWidgets import QPlainTextEdit, QWidget, QTextEdit


_VOID_HTML_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
_HTML_TAG_RE = re.compile(r"^<(/?)([a-zA-Z0-9-]+)([^>]*)>$")


_CLASS_ATTR_RE = re.compile(r'class\s*=\s*"([^"]*)"')
_UPE_CLASS_RE = re.compile(r"\bupe-node-\w+\b")
_INLINE_ELEMENT_RE = re.compile(r"^<([a-zA-Z0-9-]+)((?:\s[^>]*)?)>(.*)</\1>$")


def _extract_upe_selector(attrs_text: str):
    cm = _CLASS_ATTR_RE.search(attrs_text)
    if not cm:
        return None
    um = _UPE_CLASS_RE.search(cm.group(1))
    return ("." + um.group(0)) if um else None


def pretty_print_html_with_spans(html: str):
    """
    То же форматирование, что и pretty_print_html(), но дополнительно
    возвращает словарь {upe_selector: (start_line, end_line)} — диапазон
    строк (0-индексация в итоговом тексте) каждого элемента, помеченного
    инструментатором дерева (см. web/dom_tree_js.py). Нужно, чтобы при
    наведении на тег в текстовом виде подсвечивался весь блок целиком.
    """
    if not html:
        return "", {}
    collapsed = re.sub(r">\s*<", "><", html.strip())
    lines = collapsed.replace("><", ">\n<").split("\n")
    indent = 0
    out = []
    stack = []
    spans = {}

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue

        # Частый случай: весь элемент (открывающий тег + текст + закрывающий
        # тег) уместился в одну строку целиком, напр. <p class="...">Hi</p> —
        # его нужно распознать отдельно, иначе он не попадёт ни в открывающие,
        # ни в закрывающие теги и просто выпадет из учёта span'ов.
        inline_m = _INLINE_ELEMENT_RE.match(stripped)
        if inline_m:
            out.append("  " * indent + stripped)
            line_idx = len(out) - 1
            _tag_name, attrs_text, _inner = inline_m.groups()
            selector = _extract_upe_selector(attrs_text)
            if selector:
                spans[selector] = (line_idx, line_idx)
            continue

        m = _HTML_TAG_RE.match(stripped)
        if m:
            closing, name, rest = m.groups()
            self_closing = rest.rstrip().endswith("/") or name.lower() in _VOID_HTML_TAGS

            if closing:
                indent = max(0, indent - 1)
                out.append("  " * indent + stripped)
                line_idx = len(out) - 1
                if stack:
                    entry = stack.pop()
                    if entry["selector"]:
                        spans[entry["selector"]] = (entry["start_line"], line_idx)
            else:
                out.append("  " * indent + stripped)
                line_idx = len(out) - 1
                selector = _extract_upe_selector(rest)
                if self_closing:
                    if selector:
                        spans[selector] = (line_idx, line_idx)
                else:
                    stack.append({"selector": selector, "start_line": line_idx})
                    indent += 1
        else:
            out.append("  " * indent + stripped)

    return "\n".join(out), spans


def pretty_print_html(html: str) -> str:
    """
    Простое форматирование сериализованного HTML (из page.toHtml()) для
    удобного чтения в просмотрщике — не полноценный парсер, а лёгкая
    расстановка переносов строк и отступов по вложенности тегов.
    """
    text, _spans = pretty_print_html_with_spans(html)
    return text


class HtmlHighlighter(QSyntaxHighlighter):
    """Простая подсветка HTML: теги, атрибуты, значения атрибутов, комментарии."""

    def __init__(self, document, colors: dict):
        super().__init__(document)
        self.set_colors(colors)

    def set_colors(self, colors: dict):
        def fmt(color_hex, bold=False):
            f = QTextCharFormat()
            f.setForeground(QColor(color_hex))
            if bold:
                f.setFontWeight(QFont.Weight.Bold)
            return f

        self.tag_format = fmt(colors["code_tag"], bold=True)
        self.attr_format = fmt(colors["code_attr"])
        self.value_format = fmt(colors["code_value"])
        self.comment_format = fmt(colors["code_comment"])
        self.rehighlight()

    @staticmethod
    def _iter_matches(pattern, text):
        it = QRegularExpression(pattern).globalMatch(text)
        while it.hasNext():
            yield it.next()

    def highlightBlock(self, text):
        # Комментарии <!-- ... --> (в пределах строки — упрощённо, но для
        # просмотра разметки этого достаточно)
        for match in self._iter_matches(r"&lt;!--.*?--&gt;|<!--.*?-->", text):
            self.setFormat(match.capturedStart(), match.capturedLength(), self.comment_format)

        # Имена тегов: </? tagname
        for m in self._iter_matches(r"</?\s*([a-zA-Z0-9\-]+)", text):
            self.setFormat(m.capturedStart(1), m.capturedLength(1), self.tag_format)

        # Атрибуты: name=
        for m in self._iter_matches(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)(?==)', text):
            self.setFormat(m.capturedStart(1), m.capturedLength(1), self.attr_format)

        # Значения атрибутов в кавычках
        for m in self._iter_matches(r'"[^"]*"|\'[^\']*\'', text):
            self.setFormat(m.capturedStart(), m.capturedLength(), self.value_format)


class HtmlCodeViewer(QPlainTextEdit):
    """QPlainTextEdit только для чтения, с полосой номеров строк слева и
    подсветкой всего тега при наведении (см. set_spans/hoveredSelectorChanged)."""

    hoveredSelectorChanged = pyqtSignal(str)  # пустая строка = снять подсветку

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMouseTracking(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas, Menlo, monospace")
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(10)
        self.setFont(font)

        self._line_number_area = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_area_width)
        self.updateRequest.connect(self._update_line_number_area)
        self._update_line_number_area_width()

        self.linenum_bg = QColor("#252526")
        self.linenum_text = QColor("#858585")
        self.hover_bg = QColor(255, 64, 129, 40)

        self._spans = []  # [(start_line, end_line, selector), ...]
        self._hovered_selector = None

    def set_spans(self, spans: dict):
        """spans: {selector: (start_line, end_line)} — из pretty_print_html_with_spans()."""
        self._spans = [(s, e, sel) for sel, (s, e) in spans.items()]
        self._hovered_selector = None
        self._update_hover_selection()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        cursor = self.cursorForPosition(event.pos())
        line = cursor.blockNumber()
        selector = self._innermost_span_at(line)
        if selector != self._hovered_selector:
            self._hovered_selector = selector
            self._update_hover_selection()
            self.hoveredSelectorChanged.emit(selector or "")

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self._hovered_selector is not None:
            self._hovered_selector = None
            self._update_hover_selection()
            self.hoveredSelectorChanged.emit("")

    def _innermost_span_at(self, line: int):
        best = None
        best_len = None
        for start, end, selector in self._spans:
            if start <= line <= end:
                length = end - start
                if best_len is None or length < best_len:
                    best = selector
                    best_len = length
        return best

    def _update_hover_selection(self):
        extra_selections = []
        if self._hovered_selector:
            for start, end, selector in self._spans:
                if selector == self._hovered_selector:
                    selection = QTextEdit.ExtraSelection()
                    selection.format.setBackground(self.hover_bg)
                    selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
                    block = self.document().findBlockByNumber(start)
                    end_block = self.document().findBlockByNumber(end)
                    cursor = QTextCursor(block)
                    cursor.setPosition(
                        end_block.position() + len(end_block.text()),
                        QTextCursor.MoveMode.KeepAnchor,
                    )
                    selection.cursor = cursor
                    extra_selections.append(selection)
                    break
        self.setExtraSelections(extra_selections)

    def set_editor_colors(self, bg_hex, text_hex, linenum_bg_hex, linenum_text_hex):
        self.linenum_bg = QColor(linenum_bg_hex)
        self.linenum_text = QColor(linenum_text_hex)
        self.setStyleSheet(
            f"QPlainTextEdit {{ background: {bg_hex}; color: {text_hex}; "
            f"border: none; padding: 4px; }}"
        )
        self._line_number_area.update()

    def line_number_area_width(self):
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 12 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_number_area_width(self):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy):
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(0, rect.y(), self._line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_area_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_number_area.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def line_number_area_paint_event(self, event):
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), self.linenum_bg)

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(self.linenum_text)
                painter.drawText(
                    0, top, self._line_number_area.width() - 6, self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight, str(block_number + 1)
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1


class _LineNumberArea(QWidget):
    def __init__(self, editor: HtmlCodeViewer):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)
