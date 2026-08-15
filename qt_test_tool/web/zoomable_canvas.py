"""
The browser canvas, on a QGraphicsView. Unlike
QWebEngineView.setZoomFactor (which changes window.innerWidth/innerHeight
— i.e. "zooms the content inside the window", not "the window of
content"), the scale here is applied as a visual QGraphicsView
transform. QWebEngineView itself always stays at a fixed px size
(setFixedSize), so the page always sees exactly the viewport configured
in the device panel — like device emulation in Chrome DevTools, not a
browser page zoom.
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
        """Call after web_view.setFixedSize(...) — updates the scene bounds."""
        self._update_scene_rect()

    def _update_scene_rect(self):
        self.setSceneRect(self.proxy.boundingRect())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._on_resize()
