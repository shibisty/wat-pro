"""
Навигация браузера, диалог заголовков, live HTML-источник страницы
(код + дерево), перехват console.* сообщений со страницы, рандомайзер
форм и запись действий пользователя в шаги сценария.
"""

import json

from PyQt6.QtCore import QUrl, QTimer
from PyQt6.QtWidgets import QDialog
from PyQt6.QtWebEngineCore import QWebEnginePage

from ...widgets.dialogs import HeadersDialog
from ...widgets.html_viewer import pretty_print_html_with_spans
from ...web.randomizer_js import RANDOMIZE_FORM_JS
from ...web.dom_tree_js import DOM_TREE_JS, build_highlight_script
from ...web.recorder_js import RECORDER_INSTALL_JS, RECORDER_POLL_JS, action_to_step_js


class BrowserMixin:
    def open_headers_dialog(self):
        dlg = HeadersDialog(self.interceptor.headers, self.t, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.interceptor.headers = dlg.get_headers()
            self.log(f"Заголовки обновлены: {self.interceptor.headers}")

    # ---------------- Навигация ----------------

    def navigate(self):
        url = self.address_edit.text().strip()
        if not url:
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self.web_view.load(QUrl(url))
        self.log(f"Переход на {url}")
        self._autosave()

    # ---------------- HTML: код + дерево (live, для SPA) ----------------

    def _on_page_load_finished(self, ok):
        self._last_html_source = None
        self._poll_html_source()
        if getattr(self, "recording", False):
            # слушатели записи не переживают навигацию — переустанавливаем
            self.web_view.page().runJavaScript(RECORDER_INSTALL_JS)

    def _poll_html_source(self):
        # Сначала помечаем узлы уникальными классами и строим дерево —
        # это же инструментирование делает последующий toHtml() пригодным
        # для точной подсветки тега целиком во вкладке "Код".
        self.web_view.page().runJavaScript(DOM_TREE_JS, self._on_tree_captured)

    def _on_tree_captured(self, tree_json):
        tree_data = None
        if tree_json:
            try:
                tree_data = json.loads(tree_json)
            except (TypeError, ValueError):
                tree_data = None
        if hasattr(self, "dom_tree_view"):
            self.dom_tree_view.load_tree(tree_data)

        self.web_view.page().toHtml(self._on_html_captured)

    def _on_html_captured(self, html):
        if html == self._last_html_source:
            return
        self._last_html_source = html
        pretty, spans = pretty_print_html_with_spans(html)
        scrollbar = self.html_viewer.verticalScrollBar()
        old_value = scrollbar.value()
        self.html_viewer.setPlainText(pretty)
        self.html_viewer.set_spans(spans)
        scrollbar.setValue(min(old_value, scrollbar.maximum()))

    def _on_hover_selector_changed(self, selector: str):
        """Подсвечивает элемент в браузере при наведении в коде/дереве (или снимает подсветку)."""
        self.web_view.page().runJavaScript(build_highlight_script(selector or None))

    # ---------------- Запись действий в сценарий ----------------

    def toggle_recording(self):
        if getattr(self, "recording", False):
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self.recording = True
        self.web_view.page().runJavaScript(RECORDER_INSTALL_JS)
        if not hasattr(self, "record_poll_timer"):
            self.record_poll_timer = QTimer(self)
            self.record_poll_timer.setInterval(500)
            self.record_poll_timer.timeout.connect(self._poll_recorded_actions)
        self.record_poll_timer.start()
        self.record_btn.setText("⏹")
        self.record_btn.setProperty("recording", "true")
        self.record_btn.style().unpolish(self.record_btn)
        self.record_btn.style().polish(self.record_btn)
        self.log("Запись действий началась — кликайте/заполняйте форму в браузере", "ok")

    def _stop_recording(self):
        self.recording = False
        if hasattr(self, "record_poll_timer"):
            self.record_poll_timer.stop()
        self._poll_recorded_actions()  # забрать то, что накопилось перед остановкой
        self.record_btn.setText("⏺")
        self.record_btn.setProperty("recording", "false")
        self.record_btn.style().unpolish(self.record_btn)
        self.record_btn.style().polish(self.record_btn)
        self.log("Запись остановлена", "info")

    def _poll_recorded_actions(self):
        self.web_view.page().runJavaScript(RECORDER_POLL_JS, self._on_recorded_actions)

    def _on_recorded_actions(self, actions_json):
        try:
            actions = json.loads(actions_json) if actions_json else []
        except (TypeError, ValueError):
            actions = []
        if not actions:
            return
        for action in actions:
            js = action_to_step_js(action)
            self.steps.append({"js": js, "expected": "", "collect": False, "notify": False})
            self.log(f"Записан шаг: {js[:80]}", "ok")
        self._refresh_steps_list()
        self._autosave()

    def _on_page_console_message(self, level, message, line_number, source_id):
        level_map = {
            QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel: "info",
            QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel: "warn",
            QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel: "error",
        }
        our_level = level_map.get(level, "info")
        source_short = source_id.rsplit("/", 1)[-1] if source_id else ""
        location = f"  ({source_short}:{line_number})" if source_short else ""
        self.log(f"[console] {message}{location}", our_level)

    def randomize_form(self):
        self.log("Заполняю форму рандомными данными…")
        self.web_view.page().runJavaScript(RANDOMIZE_FORM_JS, self._randomize_form_cb)

    def _randomize_form_cb(self, result):
        try:
            data = json.loads(result) if result else {}
            filled = data.get("filled", 0)
            skipped = data.get("skipped", 0)
            total = data.get("total", 0)
            if total == 0:
                self.log("На странице не найдено полей ввода (input/select/textarea)", "error")
            else:
                self.log(
                    f"Готово: заполнено {filled} из {total} полей"
                    + (f", пропущено {skipped} (disabled/readonly/без вариантов)" if skipped else ""),
                    "ok",
                )
        except Exception as e:
            self.log(f"Не удалось разобрать результат рандомайзера: {e}", "error")
