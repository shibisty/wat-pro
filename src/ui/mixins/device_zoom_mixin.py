"""
Manages the page's px size and auto-fit zoom (equivalent to the device
toolbar in Chrome DevTools).
"""

from ...core.config import DEVICE_PRESETS


class DeviceZoomMixin:
    def on_device_preset_selected(self, index):
        if index <= 0:
            return
        name = self.device_preset_combo.itemText(index)
        width, height = DEVICE_PRESETS[name]
        self.width_spin.setValue(width)
        self.height_spin.setValue(height)
        self.log(f"Применён пресет «{name}»: {width}×{height} px")

    def on_device_size_changed(self):
        self.web_view.setFixedSize(self.width_spin.value(), self.height_spin.value())
        self.device_canvas.update_content_size()
        self._recompute_auto_zoom()
        # Deliberately no autosave here — changing the size in the fields
        # next to the address bar is a "try it out" action on the live
        # session, not a commitment to change the scenario's configured
        # start size. Only the explicit scenario edit dialog
        # (ScenarioDialog) updates what's saved.

    def _on_canvas_resized(self):
        self._recompute_auto_zoom()

    def _recompute_auto_zoom(self):
        """Recomputes the zoom to fit the available area — like Chrome
        DevTools automatically scales down when the page's configured px
        size doesn't fit the toolbar's visible area."""
        if not getattr(self, "zoom_auto", False):
            return
        viewport = self.device_canvas.viewport()
        avail_w = viewport.width()
        avail_h = viewport.height()
        dev_w = self.width_spin.value()
        dev_h = self.height_spin.value()
        if dev_w <= 0 or dev_h <= 0 or avail_w <= 0 or avail_h <= 0:
            return
        # scale down if it doesn't fit; but don't auto-scale above 100%
        factor = min(avail_w / dev_w, avail_h / dev_h, 1.0)
        percent = max(10, round(factor * 100))
        self._apply_zoom(percent, update_combo_text=True)

    def _apply_zoom(self, percent, update_combo_text=False):
        # Important: we scale ONLY the visual display (QGraphicsView),
        # not QWebEngineView.setZoomFactor() itself — that one changes the
        # page's window.innerWidth/innerHeight (i.e. "zooms the content
        # inside the window"), which made the emulated device px size
        # unreliable. Here, web_view always stays at the configured size,
        # and only how it's displayed on screen gets zoomed — exactly like
        # the device toolbar in Chrome DevTools.
        self.device_canvas.set_zoom(percent / 100.0)
        if update_combo_text:
            self.zoom_combo.blockSignals(True)
            self.zoom_combo.setEditText(f"{percent}%")
            self.zoom_combo.blockSignals(False)

    def on_zoom_activated(self, index):
        if index == 0:
            self.zoom_auto = True
            self._recompute_auto_zoom()
            return
        text = self.zoom_combo.itemText(index)
        self._set_manual_zoom_from_text(text)

    def on_zoom_manual_entry(self):
        text = self.zoom_combo.currentText()
        self._set_manual_zoom_from_text(text)

    def _set_manual_zoom_from_text(self, text):
        digits = "".join(ch for ch in text if ch.isdigit())
        if not digits:
            self._recompute_auto_zoom()
            return
        percent = max(10, min(500, int(digits)))
        self.zoom_auto = False
        self._apply_zoom(percent, update_combo_text=True)
        