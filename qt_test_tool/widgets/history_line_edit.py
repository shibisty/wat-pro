"""QLineEdit с историей введённых команд — навигация стрелками вверх/вниз, как в терминале."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLineEdit


class HistoryLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._history = []
        self._history_index = None
        self._draft = ""

    def add_to_history(self, text: str):
        text = text.strip()
        if text and (not self._history or self._history[-1] != text):
            self._history.append(text)
        self._history_index = None
        self._draft = ""

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Up:
            self._navigate(-1)
            return
        if event.key() == Qt.Key.Key_Down:
            self._navigate(1)
            return
        super().keyPressEvent(event)

    def _navigate(self, direction: int):
        if not self._history:
            return
        if self._history_index is None:
            self._draft = self.text()
            self._history_index = len(self._history)

        self._history_index += direction
        if self._history_index < 0:
            self._history_index = 0

        if self._history_index >= len(self._history):
            self._history_index = len(self._history)
            self.setText(self._draft)
            return

        self.setText(self._history[self._history_index])
