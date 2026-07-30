"""MUI-подобная карточка-панель, переиспользуется во всех блоках интерфейса."""

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel


def make_card(title: str) -> tuple:
    """Создаёт карточку-панель в духе MUI Paper с заголовком секции."""
    frame = QFrame()
    frame.setProperty("class", "card")
    frame.setObjectName("")
    frame.setStyleSheet("")  # используем глобальный QSS через class-селектор
    frame.setFrameShape(QFrame.Shape.NoFrame)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 18)
    layout.setSpacing(10)
    if title:
        label = QLabel(title)
        label.setProperty("class", "sectionLabel")
        layout.addWidget(label)
    return frame, layout
