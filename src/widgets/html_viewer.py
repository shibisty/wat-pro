"""
Page HTML source viewer: syntax highlighting, line numbers, read-only
(no editing). Plus a lightweight pretty-printer for the serialized HTML
that page.toHtml() returns.
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
    Same formatting as pretty_print_html(), but also returns a dict
    {upe_selector: (start_line, end_line)} — the line range (0-indexed in
    the resulting text) of each element tagged by the tree instrumenter
    (see web/dom_tree_js.py). Needed so hovering over a tag in the text
    view highlights the whole block.
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

        # Common case: the whole element (opening tag + text + closing
        # tag) fits on a single line, e.g. <p class="...">Hi</p> — it
        # needs to be recognized separately, otherwise it won't match
        # either the opening or closing tag pattern and would simply drop
        # out of span tracking.
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
    Simple formatting of serialized HTML (from page.toHtml()) for
    convenient reading in the viewer — not a full parser, just lightweight
    line-break and indentation placement based on tag nesting.
    """
    text, _spans = pretty_print_html_with_spans(html)
    return text


class HtmlHighlighter(QSyntaxHighlighter):
    """Simple HTML highlighting: tags, attributes, attribute values, comments."""

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
        # Comments <!-- ... --> (within a line — simplified, but good
        # enough for viewing markup)
        for match in self._iter_matches(r"&lt;!--.*?--&gt;|<!--.*?-->", text):
            self.setFormat(match.capturedStart(), match.capturedLength(), self.comment_format)

        # Tag names: </? tagname
        for m in self._iter_matches(r"</?\s*([a-zA-Z0-9\-]+)", text):
            self.setFormat(m.capturedStart(1), m.capturedLength(1), self.tag_format)

        # Attributes: name=
        for m in self._iter_matches(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)(?==)', text):
            self.setFormat(m.capturedStart(1), m.capturedLength(1), self.attr_format)

        # Quoted attribute values
        for m in self._iter_matches(r'"[^"]*"|\'[^\']*\'', text):
            self.setFormat(m.capturedStart(), m.capturedLength(), self.value_format)


class HtmlCodeViewer(QPlainTextEdit):
    """A read-only QPlainTextEdit with a line-number gutter on the left
    and full-tag highlighting on hover (see set_spans/hoveredSelectorChanged)."""

    hoveredSelectorChanged = pyqtSignal(str)  # empty string = clear the highlight

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
        """spans: {selector: (start_line, end_line)} — from pretty_print_html_with_spans()."""
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
