"""
Browser navigation, headers dialog, live page HTML source (code + tree),
intercepting the page's console.* messages, form randomizer, and
recording user actions into scenario steps.
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
        dlg = HeadersDialog(self.app.interceptor.headers, self.t, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.app.interceptor.headers = dlg.get_headers()
            self.log(self.t("log_headers_updated").format(headers=self.app.interceptor.headers))

    # ---------------- Navigation ----------------

    def navigate(self):
        url = self.address_edit.text().strip()
        if not url:
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self.web_view.load(QUrl(url))
        self.log(self.t("log_navigating").format(url=url))

    # ---------------- HTML: code + tree (live, for SPAs) ----------------

    def _web_view_alive(self) -> bool:
        """
        All the methods below are called ASYNCHRONOUSLY (the
        runJavaScript callback arrives later, from Qt's event loop) — by
        that time the web_view widget may well have already been deleted
        (a tab/window was closed, the page was swapped via
        _start_fresh_session, etc). Without this check we'd hit
        RuntimeError: "wrapped C/C++ object ... has been deleted" at that
        point — the Python wrapper is still alive, but the C++ object
        behind it is already gone.
        """
        try:
            from PyQt6 import sip
            return not sip.isdeleted(self.web_view)
        except ImportError:
            return True  # sip unavailable — can't check, assume alive
        except RuntimeError:
            return False

    def _on_page_load_finished(self, ok):
        if not self._web_view_alive():
            return
        self._last_html_source = None
        self.refresh_html_panels()
        if getattr(self, "recording", False):
            # recording listeners don't survive navigation — reinstall them
            self.web_view.page().runJavaScript(RECORDER_INSTALL_JS)

    def _on_page_url_changed(self, url):
        """
        Keeps the address bar showing the CURRENT page URL — link clicks,
        JS redirects, and in-page navigation all change the real URL
        without the user ever typing anything into the address bar
        themselves. Without this, the field only ever showed whatever
        was originally typed/loaded, not where the browser actually is.
        Skipped while the field has focus so it doesn't yank out
        whatever the user is currently typing there.
        """
        if not self._web_view_alive():
            return
        if self.address_edit.hasFocus():
            return
        self.address_edit.setText(url.toString())

    def _poll_html_source(self):
        if not self._web_view_alive():
            return
        # First tag nodes with unique classes and build the tree — this
        # same instrumentation is what makes the subsequent toHtml() usable
        # for precisely highlighting the whole tag in the "Code" tab.
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
        """Highlights the element in the browser on hover in the code/tree (or clears the highlight)."""
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
        """Single point that refreshes all 4 tabs of the HTML panel
        (Code/Tree/localStorage/Cache) — called both by the "Refresh"
        button and once right after navigating to a new page."""
        self._poll_html_source()
        self._poll_local_storage()
        self._poll_cache_files()

    # ---------------- "Cache" tab: right-click -> save/explorer/properties ----------------
    #
    # Honest disclaimer: the "Cache" tab shows metadata from the browser's
    # Resource Timing API, not the actual contents of Chromium's disk
    # cache (that's a binary format with no public read API — see
    # web/inspect_js.py). So "Open in Explorer"/"Properties" don't act on
    # a file that's already sitting somewhere — they RE-DOWNLOAD the
    # content from the same URL and save it to a temp folder, and only
    # then does Explorer/Properties open a real file on disk. For
    # third-party domains without CORS headers, downloading the body
    # won't work — you'll get a clear error in the log instead of a crash.

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
        """Re-downloads the resource by URL (by polling — runJavaScript
        doesn't wait for a Promise, see inspect_js.py) and saves it to
        dest_path; calls on_saved(path) when done, if one was given."""
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

    # ---------------- Recording actions into the scenario ----------------

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
        self._poll_recorded_actions()  # grab whatever accumulated before stopping
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
        # the message itself is the web page's own console.* output (its
        # own text, not ours), so we don't translate the content, only the prefix
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
            