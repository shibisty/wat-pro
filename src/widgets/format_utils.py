"""Small formatters shared across several widgets."""

from PyQt6.QtWidgets import QTableWidgetItem


def format_size(n) -> str:
    n = n or 0
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


class NumericTableWidgetItem(QTableWidgetItem):
    """A QTableWidgetItem that sorts by number (value), not by the
    displayed text — otherwise "244.1 KB" would sort before "14.6 KB" as
    a plain string (character-by-character comparison)."""

    def __init__(self, text: str, value):
        super().__init__(text)
        self._value = value

    def __lt__(self, other):
        if isinstance(other, NumericTableWidgetItem):
            return self._value < other._value
        return super().__lt__(other)
    