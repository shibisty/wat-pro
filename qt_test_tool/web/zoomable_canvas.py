"""
Холст браузера на QGraphicsView. В отличие от QWebEngineView.setZoomFactor
(который меняет window.innerWidth/innerHeight — то есть "зумит контент
внутри окна", а не "окно контента"), масштаб здесь применяется как
визуальная трансформация QGraphicsView. Сам QWebEngineView всегда
остаётся зафиксированного px-размера (setFixedSize), поэтому страница
всегда видит именно тот viewport, который выставлен в device-панели —
как эмуляция устройства в Chrome DevTools, а не браузерный page zoom.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene


class ZoomableWebCanvas(QGraphicsView):
    def __init__(self, web_view, on_resize=None, parent=None):
        super().__init__(parent)
        self._on_resize = on_resize or (lambda: None)
        self._zoom = 1.0

        scene = QGraphicsScene(self)
        self.setScene(scene)
        self.proxy = scene.addWidget(web_view)

        self.setRenderHints(QPainter.RenderHint.SmoothPixmapTransform | QPainter.RenderHint.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)

    def set_zoom(self, factor: float):
        self._zoom = factor
        self.resetTransform()
        self.scale(factor, factor)
        self._update_scene_rect()

    def zoom(self) -> float:
        return self._zoom

    def update_content_size(self):
        """Вызывать после web_view.setFixedSize(...) — обновляет границы сцены."""
        self._update_scene_rect()

    def _update_scene_rect(self):
        self.setSceneRect(self.proxy.boundingRect())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._on_resize()
