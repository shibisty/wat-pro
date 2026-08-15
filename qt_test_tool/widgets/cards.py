"""A MUI-like card panel, reused across every block of the UI."""

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel


def make_card(title: str) -> tuple:
    """Creates a card panel in the spirit of MUI Paper, with a section title."""
    frame = QFrame()
    frame.setProperty("class", "card")
    frame.setObjectName("")
    frame.setStyleSheet("")  # we use the global QSS via a class selector
    frame.setFrameShape(QFrame.Shape.NoFrame)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 18)
    layout.setSpacing(10)
    if title:
        label = QLabel(title)
        label.setProperty("class", "sectionLabel")
        layout.addWidget(label)
    return frame, layout
