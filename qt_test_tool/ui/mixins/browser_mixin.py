"""
Навигация браузера, диалог заголовков, live HTML-источник страницы
(код + дерево), перехват console.* сообщений со страницы, рандомайзер
форм и запись действий пользователя в шаги сценария.
"""

import base64
import hashlib
import json
import os
import platform
import subprocess
import tempfile

from PyQt6.QtCore import QUrl, QTimer, Qt
from PyQt6.QtWidgets import QDialog, QMenu, QFileDialog, QApplication
from PyQt6.QtWebEngineCore import QWebEnginePage

from ...widgets.dialogs import HeadersDialog
from ...widgets.html_viewer import pretty_print_html_with_spans
from ...web.randomizer_js import RANDOMIZE_FORM_JS
from ...web.dom_tree_js import DOM_TREE_JS, build_highlight_script
from ...web.recorder_js import RECORDER_INSTALL_JS, RECORDER_POLL_JS, action_to_step_js
from ...web.inspect_js import (
    LOCAL_STORAGE_JS, RESOURCE_ENTRIES_JS,
    build_fetch_resource_start_script, FETCH_RESOURCE_CHECK_JS,
)


class BrowserMixin:
    def open_headers_dialog(self):
        dlg = HeadersDialog(self.interceptor.headers, self.t, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.interceptor.headers = dlg.get_headers()
            self.log(self.t("log_headers_updated").format(headers=self.interceptor.headers))

    # ---------------- Навигация ----------------

    def navigate(self):
        url = self.address_edit.text().strip()
        if not url:
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self.web_view.load(QUrl(url))
        self.log(self.t("log_navigating").format(url=url))
        self._autosave()

    # ---------------- HTML: код + дерево (live, для SPA) ----------------

    def _web_view_alive(self) -> bool:
        """
        Все методы ниже вызываются АСИНХРОННО (колбэк от runJavaScript
        приходит позже, из цикла событий Qt) — за это время виджет
        web_view вполне может быть уже удалён (закрыли вкладку/окно,
        подменили страницу через _start_fresh_session и т.п.). Без этой
        проверки в такой момент ловим RuntimeError: "wrapped C/C++ object
        ... has been deleted" — Python-обёртка ещё жива, а C++-объект
        за ней уже нет.
        """
        try:
            from PyQt6 import sip
            return not sip.isdeleted(self.web_view)
        except ImportError:
            return True  # sip недоступен — не можем проверить, считаем живым
        except RuntimeError:
            return False

    def _on_page_load_finished(self, ok):
        if not self._web_view_alive():
            return
        self._last_html_source = None
        self.refresh_html_panels()
        if getattr(self, "recording", False):
            # слушатели записи не переживают навигацию — переустанавливаем
            self.web_view.page().runJavaScript(RECORDER_INSTALL_JS)

    def _poll_html_source(self):
        if not self._web_view_alive():
            return
        # Сначала помечаем узлы уникальными классами и строим дерево —
        # это же инструментирование делает последующий toHtml() пригодным
        # для точной подсветки тега целиком во вкладке "Код".
        self.web_view.page().runJavaScript(DOM_TREE_JS, self._on_tree_captured)

    def _on_tree_captured(self, tree_json):
        if not self._web_view_alive():
            return
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
        if not self._web_view_alive():
            return
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
        if not self._web_view_alive():
            return
        self.web_view.page().runJavaScript(build_highlight_script(selector or None))

    def _poll_local_storage(self):
        if not hasattr(self, "local_storage_view") or not self._web_view_alive():
            return

        def on_result(items_json):
            if not self._web_view_alive():
                return
            try:
                items = json.loads(items_json) if items_json else []
            except (TypeError, ValueError):
                items = []
            self.local_storage_view.load_items(items)

        self.web_view.page().runJavaScript(LOCAL_STORAGE_JS, on_result)

    def _poll_cache_files(self):
        if not hasattr(self, "cache_files_view") or not self._web_view_alive():
            return

        def on_result(items_json):
            if not self._web_view_alive():
                return
            try:
                items = json.loads(items_json) if items_json else []
            except (TypeError, ValueError):
                items = []
            self.cache_files_view.load_items(items)

        self.web_view.page().runJavaScript(RESOURCE_ENTRIES_JS, on_result)

    def refresh_html_panels(self):
        """Единая точка обновления всех 4 вкладок HTML-панели (Код/Дерево/
        localStorage/Кэш) — вызывается и по кнопке "Обновить", и один раз
        сразу после навигации на новую страницу."""
        self._poll_html_source()
        self._poll_local_storage()
        self._poll_cache_files()

    # ---------------- Вкладка "Кэш": ПКМ → сохранить/проводник/свойства ----------------
    #
    # Честная оговорка: вкладка "Кэш" показывает метаданные из Resource
    # Timing API браузера, а не прямое содержимое дискового кэша Chromium
    # (тот в бинарном формате, без публичного API для чтения — см.
    # web/inspect_js.py). Поэтому "Открыть в проводнике"/"Свойства"
    # работают не с уже лежащим где-то файлом, а СКАЧИВАЮТ содержимое
    # заново по тому же URL и сохраняют во временную папку — тогда
    # проводник/свойства открывают уже реальный файл на диске. Для чужих
    # доменов без CORS-заголовков скачать тело не получится — будет
    # понятная ошибка в логе, а не падение.

    def _on_cache_context_menu(self, pos):
        item = self.cache_files_view.itemAt(pos)
        if item is None:
            return
        data = self.cache_files_view.item_data_at(item.row())
        if not data:
            return
        url = data.get("fullUrl", "")
        suggested_name = data.get("name") or "download"

        menu = QMenu(self.cache_files_view)
        save_action = menu.addAction(self.t("ctx_save_as"))
        menu.addSeparator()
        explorer_action = menu.addAction(self.t("ctx_open_explorer"))
        props_action = menu.addAction(self.t("ctx_properties"))
        menu.addSeparator()
        copy_action = menu.addAction(self.t("ctx_copy_url"))

        windows_only = platform.system() == "Windows"
        if not windows_only:
            explorer_action.setEnabled(False)
            explorer_action.setToolTip(self.t("log_explorer_windows_only"))
            props_action.setEnabled(False)
            props_action.setToolTip(self.t("log_explorer_windows_only"))

        chosen = menu.exec(self.cache_files_view.viewport().mapToGlobal(pos))
        if chosen is None:
            return

        if chosen == copy_action:
            QApplication.clipboard().setText(url)
        elif chosen == save_action:
            path, _ = QFileDialog.getSaveFileName(self, self.t("ctx_save_as"), suggested_name)
            if path:
                self._fetch_and_save(url, suggested_name, path, None)
        elif chosen == explorer_action:
            dest = self._temp_path_for(url, suggested_name)
            self._fetch_and_save(url, suggested_name, dest, self._open_in_explorer)
        elif chosen == props_action:
            dest = self._temp_path_for(url, suggested_name)
            self._fetch_and_save(url, suggested_name, dest, self._show_file_properties)

    def _temp_path_for(self, url: str, suggested_name: str) -> str:
        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
        folder = os.path.join(tempfile.gettempdir(), "WATPro_cache", url_hash)
        return os.path.join(folder, suggested_name or "download")

    def _fetch_and_save(self, url, suggested_name, dest_path, on_saved):
        """Скачивает ресурс заново по URL (поллингом — runJavaScript Promise
        не дожидается, см. inspect_js.py) и сохраняет в dest_path; по
        завершении вызывает on_saved(path), если он задан."""
        self.log(self.t("log_fetching_resource").format(name=suggested_name))
        self.web_view.page().runJavaScript(build_fetch_resource_start_script(url))
        self._poll_fetch_resource(suggested_name, dest_path, on_saved, 0)

    def _poll_fetch_resource(self, suggested_name, dest_path, on_saved, elapsed_ms):
        def on_check(result_json):
            if result_json is None:
                if elapsed_ms >= 15000:
                    self.log(self.t("log_fetch_timeout").format(name=suggested_name), "error")
                    return
                QTimer.singleShot(
                    150,
                    lambda: self._poll_fetch_resource(suggested_name, dest_path, on_saved, elapsed_ms + 150),
                )
                return

            try:
                result = json.loads(result_json)
            except (TypeError, ValueError):
                result = {"success": False, "error": "parse error"}

            if not result.get("success"):
                self.log(
                    self.t("log_fetch_failed").format(name=suggested_name, error=result.get("error", "?")),
                    "error",
                )
                return

            try:
                content = base64.b64decode(result["base64"])
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                with open(dest_path, "wb") as f:
                    f.write(content)
            except Exception as e:
                self.log(self.t("log_fetch_failed").format(name=suggested_name, error=str(e)), "error")
                return

            self.log(self.t("log_fetch_saved").format(path=dest_path), "ok")
            if on_saved:
                on_saved(dest_path)

        self.web_view.page().runJavaScript(FETCH_RESOURCE_CHECK_JS, on_check)

    def _open_in_explorer(self, path: str):
        if platform.system() != "Windows":
            self.log(self.t("log_explorer_windows_only"), "error")
            return
        subprocess.run(["explorer", "/select,", path])

    def _show_file_properties(self, path: str):
        if platform.system() != "Windows":
            self.log(self.t("log_explorer_windows_only"), "error")
            return
        try:
            os.startfile(path, "properties")
        except Exception as e:
            self.log(self.t("log_fetch_failed").format(name=os.path.basename(path), error=str(e)), "error")

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
        self.log(self.t("log_recording_started"), "ok")

    def _stop_recording(self):
        self.recording = False
        if hasattr(self, "record_poll_timer"):
            self.record_poll_timer.stop()
        self._poll_recorded_actions()  # забрать то, что накопилось перед остановкой
        self.record_btn.setText("⏺")
        self.record_btn.setProperty("recording", "false")
        self.record_btn.style().unpolish(self.record_btn)
        self.record_btn.style().polish(self.record_btn)
        self.log(self.t("log_recording_stopped"), "info")

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
            self.log(self.t("log_step_recorded").format(code=js[:80]), "ok")
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
        # само сообщение — вывод console.* самой веб-страницы (её собственный
        # текст, не наш), поэтому не переводим содержимое, только префикс
        self.log(f"[console] {message}{location}", our_level)

    def randomize_form(self):
        self.log(self.t("log_randomizing"))
        self.web_view.page().runJavaScript(RANDOMIZE_FORM_JS, self._randomize_form_cb)

    def _randomize_form_cb(self, result):
        try:
            data = json.loads(result) if result else {}
            filled = data.get("filled", 0)
            skipped = data.get("skipped", 0)
            total = data.get("total", 0)
            if total == 0:
                self.log(self.t("log_no_form_fields"), "error")
            else:
                text = self.t("log_randomize_done").format(filled=filled, total=total)
                if skipped:
                    text += self.t("log_randomize_skipped").format(skipped=skipped)
                self.log(text, "ok")
        except Exception as e:
            self.log(self.t("log_randomize_parse_failed").format(error=e), "error")
            