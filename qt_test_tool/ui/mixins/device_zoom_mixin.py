"""
Управление px-размером страницы и авто-подгоняемым зумом (аналог
device toolbar в Chrome DevTools).
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
        self._autosave()

    def _on_canvas_resized(self):
        self._recompute_auto_zoom()

    def _recompute_auto_zoom(self):
        """Пересчитывает zoom под доступную область — как Chrome DevTools
        автоматически уменьшает масштаб, если заданный px-размер страницы
        не помещается в видимую область панели инструментов."""
        if not getattr(self, "zoom_auto", False):
            return
        viewport = self.device_canvas.viewport()
        avail_w = viewport.width()
        avail_h = viewport.height()
        dev_w = self.width_spin.value()
        dev_h = self.height_spin.value()
        if dev_w <= 0 or dev_h <= 0 or avail_w <= 0 or avail_h <= 0:
            return
        # уменьшаем, если не помещается; но не увеличиваем автоматически выше 100%
        factor = min(avail_w / dev_w, avail_h / dev_h, 1.0)
        percent = max(10, round(factor * 100))
        self._apply_zoom(percent, update_combo_text=True)

    def _apply_zoom(self, percent, update_combo_text=False):
        # Важно: масштабируем ТОЛЬКО визуальное отображение (QGraphicsView),
        # а не сам QWebEngineView.setZoomFactor() — тот меняет
        # window.innerWidth/innerHeight страницы (т.е. "зумит контент внутри
        # окна"), из-за чего эмулируемый px-размер устройства переставал
        # быть достоверным. Здесь же web_view всегда остаётся заданного
        # размера, а зумируется только то, как он показан на экране —
        # ровно как device toolbar в Chrome DevTools.
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
