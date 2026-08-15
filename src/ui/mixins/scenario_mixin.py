"""
Scenario management: create/select (JSON files — easy to hand off to
other users), edit steps and run via ScenarioRunner.

"Live" behavior: picking a scenario in the list loads it immediately (no
separate button), and any change (name, URL, window size, steps) is
autosaved to disk immediately (no separate button) — see _autosave().
Explicit buttons remain only where a deliberate fork is needed: create
new / rename / delete.

A scenario stores not just its steps, but also the start URL, browser
window size (width/height) and zoom — so you can configure a test for
mobile/tablet/desktop once and have it remembered.

Steps with collect=True write their result to collected_data after
running; steps with notify=True send an e-mail notification right in
the middle of the scenario (independent of the overall scenario's final
success/failure).

Every scenario run (play_scenario) starts in a FRESH off-the-record
session (see _start_fresh_session) — a separate QWebEngineProfile with no
cookies/cache/localStorage/IndexedDB from previous runs. This matters,
for example, when a scenario adds an item to a cart: without session
isolation, a repeat run would see the cart already occupied from last
time and break. After the scenario finishes, the used session is also
cleaned up (cookies/cache), and the next run gets a brand new profile
regardless.
"""

import copy
import json

from PyQt6.QtCore import QUrl, QTimer
from PyQt6.QtWidgets import QInputDialog, QListWidgetItem, QDialog, QMessageBox, QFileDialog
from PyQt6.QtWebEngineCore import QWebEngineProfile

from ...core.theming import THEMES, qcolor
from ...core.scenario_runner import ScenarioRunner
from ...core.i18n import ACCEPT_LANGUAGE_MAP, NAVIGATOR_LOCALE_MAP
from ...data import scenarios_repo, collected_data_repo
from ...notifications import email_notifier
from ...widgets.dialogs import StepDialog, ScenarioDialog
from ...web.page import LoggingWebPage, configure_profile


class ScenarioMixin:
    def _refresh_scenario_list(self):
        self.scenario_combo.blockSignals(True)
        self.scenario_combo.clear()
        self.scenario_combo.addItem(self.t("placeholder_choose_scenario"), None)
        for row in scenarios_repo.list_scenarios():
            self.scenario_combo.addItem(row["name"], row["id"])
        self.scenario_combo.blockSignals(False)

    def new_scenario(self):
        dlg = ScenarioDialog(
            width=self.width_spin.value(), height=self.height_spin.value(),
            tr=self.t, parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        if not data["name"]:
            self.log(self.t("log_select_scenario_first"), "error")
            return
        # create the record right away — autosave has nothing to attach to otherwise
        self.current_scenario_id = scenarios_repo.create_scenario(
            data["name"], [], url=data["url"], width=data["width"], height=data["height"],
            zoom_auto=True, zoom_percent=100,
        )
        self.current_scenario_name = data["name"]
        self.steps = []
        self._refresh_steps_list()
        self._refresh_scenario_list()
        idx = self.scenario_combo.findData(self.current_scenario_id)
        if idx >= 0:
            self.scenario_combo.blockSignals(True)
            self.scenario_combo.setCurrentIndex(idx)
            self.scenario_combo.blockSignals(False)

        # apply the start URL/size to the current browser session right
        # away, so what was set in the dialog is visible on the live screen
        self.width_spin.setValue(data["width"])
        self.height_spin.setValue(data["height"])
        self.address_edit.setText(data["url"])
        if data["url"]:
            self.navigate()

        self.log(f"Создан новый сценарий: {self.current_scenario_name}")

    def on_scenario_selected(self, index):
        """Auto-load on list selection — there's no separate "Load" button anymore."""
        if index < 0:
            return
        scenario_id = self.scenario_combo.currentData()
        if scenario_id is None:
            return
        self._load_scenario(scenario_id)

    def _load_scenario(self, scenario_id):
        data = scenarios_repo.get_scenario(scenario_id)
        if not data:
            self.log("Сценарий не найден", "error")
            return
        self.current_scenario_id = data["id"]
        self.current_scenario_name = data["name"]
        self.steps = data["steps"]
        self._refresh_steps_list()

        # restore the browser window size and zoom saved with the scenario
        self.width_spin.setValue(data.get("width", 1366))
        self.height_spin.setValue(data.get("height", 768))
        if data.get("zoom_auto", True):
            self.zoom_auto = True
            self.zoom_combo.setCurrentIndex(0)
            self._recompute_auto_zoom()
        else:
            self._set_manual_zoom_from_text(f"{data.get('zoom_percent', 100)}%")

        self.address_edit.setText(data.get("url", ""))
        if data.get("url"):
            self.navigate()
        self.log(f"Загружен сценарий: {self.current_scenario_name}")

    def edit_scenario_name(self):
        """Edit the current scenario: name + start URL + start size
        (id/file stay the same, only the content changes). Saves url/
        width/height explicitly here — this is the ONE place they're
        meant to change, via the dialog, not via the general _autosave()
        (which only ever touches steps — see its docstring)."""
        if not self.current_scenario_name:
            self.log(self.t("log_select_scenario_first"), "error")
            return
        dlg = ScenarioDialog(
            name=self.current_scenario_name,
            url=self.address_edit.text(),
            width=self.width_spin.value(),
            height=self.height_spin.value(),
            tr=self.t, parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        data = dlg.get_data()
        if not data["name"]:
            return
        self.current_scenario_name = data["name"]
        self.width_spin.setValue(data["width"])
        self.height_spin.setValue(data["height"])
        self.address_edit.setText(data["url"])

        existing = scenarios_repo.get_scenario(self.current_scenario_id) if self.current_scenario_id else None
        zoom_auto = existing.get("zoom_auto", True) if existing else True
        zoom_percent = existing.get("zoom_percent", 100) if existing else 100
        self.current_scenario_id = scenarios_repo.upsert_scenario_by_name(
            data["name"], self.steps, data["url"],
            width=data["width"], height=data["height"],
            zoom_auto=zoom_auto, zoom_percent=zoom_percent,
        )
        self._refresh_scenario_list()
        idx = self.scenario_combo.findData(self.current_scenario_id)
        if idx >= 0:
            self.scenario_combo.blockSignals(True)
            self.scenario_combo.setCurrentIndex(idx)
            self.scenario_combo.blockSignals(False)

        if data["url"]:
            self.navigate()

    def delete_scenario(self):
        if self.current_scenario_id is None:
            self.log("Сначала выберите сценарий в списке", "error")
            return
        reply = QMessageBox.question(
            self,
            self.t("confirm_delete_scenario_title"),
            self.t("confirm_delete_scenario_text").format(name=self.current_scenario_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        scenarios_repo.delete_scenario(self.current_scenario_id)
        self.log(f"Сценарий удалён: {self.current_scenario_name}")
        self.current_scenario_id = None
        self.current_scenario_name = ""
        self.steps = []
        self._refresh_steps_list()
        self._refresh_scenario_list()
        if self.scenario_combo.count() > 0:
            self.scenario_combo.setCurrentIndex(0)
            # activated doesn't fire on a programmatic index change —
            # load explicitly
            self._load_scenario(self.scenario_combo.currentData())

    def _autosave(self):
        """
        Silent save, no dialogs/extra logs — called after any change to
        the STEPS list (add/edit/delete/move/undo/record), provided the
        scenario already has a name (otherwise there's simply
        nothing/nowhere to save to).

        IMPORTANT: only `steps` gets updated here. url/width/height/zoom
        are set explicitly, once, via the scenario create/edit dialog
        (see new_scenario()/edit_scenario_name()) — this deliberately does
        NOT pull them from the live nav_bar fields. Without this, just
        navigating somewhere to poke around, or resizing the window for a
        quick look, would silently overwrite the scenario's configured
        start state on every step change.
        """
        if not self.current_scenario_name:
            return

        existing = None
        if self.current_scenario_id is not None:
            existing = scenarios_repo.get_scenario(self.current_scenario_id)
        if existing is None:
            existing = scenarios_repo.get_scenario_by_name(self.current_scenario_name)

        if existing is not None:
            url = existing.get("url", "")
            width = existing.get("width", 1366)
            height = existing.get("height", 768)
            zoom_auto = existing.get("zoom_auto", True)
            zoom_percent = existing.get("zoom_percent", 100)
        else:
            # a genuinely new scenario that somehow isn't on disk yet —
            # fall back to whatever the live fields currently show, just
            # this once, so there's at least something to write
            url = self.address_edit.text().strip()
            width = self.width_spin.value()
            height = self.height_spin.value()
            zoom_auto = self.zoom_auto
            zoom_percent = 100

        self.current_scenario_id = scenarios_repo.upsert_scenario_by_name(
            self.current_scenario_name, self.steps, url,
            width=width, height=height,
            zoom_auto=zoom_auto, zoom_percent=zoom_percent,
        )
        self._refresh_scenario_list()
        idx = self.scenario_combo.findData(self.current_scenario_id)
        if idx >= 0:
            self.scenario_combo.blockSignals(True)
            self.scenario_combo.setCurrentIndex(idx)
            self.scenario_combo.blockSignals(False)

    # ---------------- Scenario steps ----------------

    def _refresh_steps_list(self):
        self.steps_list.clear()
        for i, step in enumerate(self.steps):
            if step.get("kind") == "recorder":
                title = step.get("recorder_title") or "Recorder"
                count = len(step.get("recorder_steps", []))
                preview = f"🎬 {title} ({count} {self.t('recorder_actions_suffix')})"
            else:
                preview = step["js"].strip().replace("\n", " ")[:60]
            marks = ""
            if step.get("collect"):
                marks += " 💾"
            if step.get("notify"):
                marks += " ✉️"
            if step.get("wait_for_navigation"):
                marks += " ⏳"
            if (step.get("wait_for_selector") or "").strip():
                marks += " 🔎"
            if step.get("delay_ms"):
                marks += " ⏱️"
            self.steps_list.addItem(QListWidgetItem(f"{i + 1}. {preview}{marks}"))

    def _push_undo(self):
        """Snapshot of the current step list before a change — for Ctrl+Z."""
        if not hasattr(self, "_undo_stack"):
            self._undo_stack = []
        self._undo_stack.append(copy.deepcopy(self.steps))
        if len(self._undo_stack) > 20:
            self._undo_stack.pop(0)

    def undo_steps(self):
        if not getattr(self, "_undo_stack", None):
            self.log("Нечего отменять", "info")
            return
        self.steps = self._undo_stack.pop()
        self._refresh_steps_list()
        self._autosave()
        self.log("Отменено последнее изменение шагов", "ok")

    def import_recorder_file(self):
        """
        The 🎬 Import Recorder button — takes a Chrome DevTools Recorder
        export (.json) and appends it to the current scenario as ONE
        opaque step (see core/scenario_runner.py /
        web/recorder_replay_js.py for how it actually plays back).
        """
        path, _ = QFileDialog.getOpenFileName(
            self, self.t("dialog_import_recorder_title"), "", "JSON (*.json)"
        )
        if not path:
            return
        step = self._load_recorder_file(path)
        if step is None:
            return
        self._push_undo()
        self.steps.append(step)
        self._refresh_steps_list()
        self._autosave()
        self.log(self.t("log_recorder_imported").format(title=step["recorder_title"]), "ok")

    def _load_recorder_file(self, path):
        """
        Parses and validates a Recorder .json file, returning a ready
        scenario step dict, or None (with an error already logged) if
        the file isn't a valid Recorder export.

        setViewport is pulled out here, at import time, if it's present
        as the first step (the overwhelmingly common case — Chrome always
        records it as the very first action) — page JS can't resize the
        actual browser window, so it's applied separately, on the Python
        side, right before the rest of the recording plays (see
        ScenarioRunner._execute_recorder_step / on_recorder_viewport).
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            self.log(self.t("log_recorder_import_failed").format(error=str(e)), "error")
            return None

        raw_steps = data.get("steps")
        if not isinstance(raw_steps, list):
            self.log(self.t("log_recorder_invalid_file"), "error")
            return None

        viewport = None
        if raw_steps and raw_steps[0].get("type") == "setViewport":
            viewport = {"width": raw_steps[0].get("width"), "height": raw_steps[0].get("height")}
            raw_steps = raw_steps[1:]

        return {
            "kind": "recorder",
            "recorder_title": data.get("title") or "Recorder",
            "recorder_steps": raw_steps,
            "recorder_viewport": viewport,
            "collect": False,
            "notify": False,
        }

    def add_step(self):
        dlg = StepDialog(tr=self.t, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if data["js"].strip():
                self._push_undo()
                self.steps.append(data)
                self._refresh_steps_list()
                self._autosave()

    def edit_step(self):
        row = self.steps_list.currentRow()
        if row < 0:
            return
        step = self.steps[row]
        if step.get("kind") == "recorder":
            self._edit_recorder_step(row, step)
            return
        dlg = StepDialog(step, tr=self.t, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._push_undo()
            self.steps[row] = dlg.get_data()
            self._refresh_steps_list()
            self._autosave()

    def _edit_recorder_step(self, row, step):
        """
        A recorder step isn't JS text — the normal StepDialog doesn't
        apply to it. For now: show what it is, offer to delete it or
        replace it with a freshly re-imported recording (e.g. after
        re-recording in Chrome). No in-place field editing of individual
        recorded actions yet.
        """
        title = step.get("recorder_title") or "Recorder"
        count = len(step.get("recorder_steps", []))
        reply = QMessageBox.question(
            self,
            self.t("dialog_recorder_step_title"),
            self.t("dialog_recorder_step_text").format(title=title, count=count),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            path, _ = QFileDialog.getOpenFileName(
                self, self.t("dialog_import_recorder_title"), "", "JSON (*.json)"
            )
            if not path:
                return
            new_step = self._load_recorder_file(path)
            if new_step is None:
                return
            self._push_undo()
            self.steps[row] = new_step
            self._refresh_steps_list()
            self._autosave()

    def delete_step(self):
        """Deletes ALL selected steps (ExtendedSelection — Ctrl/Shift for
        multi-select). Works both via the 🗑️ button and the Delete key."""
        rows = sorted({index.row() for index in self.steps_list.selectedIndexes()}, reverse=True)
        if not rows:
            return
        self._push_undo()
        for row in rows:
            del self.steps[row]
        self._refresh_steps_list()
        self._autosave()

    def move_step(self, direction):
        row = self.steps_list.currentRow()
        new_row = row + direction
        if row < 0 or new_row < 0 or new_row >= len(self.steps):
            return
        self._push_undo()
        self.steps[row], self.steps[new_row] = self.steps[new_row], self.steps[row]
        self._refresh_steps_list()
        self.steps_list.setCurrentRow(new_row)
        self._autosave()

    def _on_bridge_insert(self, data):
        """
        InsertToDB(data) from the page's JS — see web/bridge.py. Unlike
        the 💾 collect flag on a step (one value per step, only after it
        finishes), this can be called any number of times from anywhere
        in the step's JS code, at any moment.
        """
        if getattr(self, "current_scenario_id", None) is None:
            self.log("InsertToDB: сценарий ещё не назван — данные не записаны в БД.", "error")
            return
        collected_data_repo.insert_row(self.db_conn, self.current_scenario_id, data)
        self.log(f"InsertToDB: записано в БД ({len(data)} симв.)", "ok")

    # ---------------- Fresh (off-the-record) session for a run ----------------

    def _start_fresh_session(self):
        """
        Creates a new anonymous (off-the-record) WebEngine profile —
        separate cookies/cache/localStorage/IndexedDB, fully isolated from
        previous state (e.g. an item left in the cart from the last run).
        Swaps self.web_view.page() for a page on this new profile and
        recreates ScenarioRunner (it was bound to the old page — its
        loadStarted/loadFinished signals would be listening to the wrong one).
        """
        profile = QWebEngineProfile(self)  # anonymous constructor = off-the-record, in-memory
        configure_profile(
            profile,
            self.app.interceptor,
            ACCEPT_LANGUAGE_MAP.get(self.language, ACCEPT_LANGUAGE_MAP["en"]),
            NAVIGATOR_LOCALE_MAP.get(self.language, "en-US"),
            self.theme,
        )
        new_page = LoggingWebPage(profile, self.web_view, self._on_page_console_message)
        new_page.loadFinished.connect(self._on_page_load_finished)
        new_page.urlChanged.connect(self._on_page_url_changed)
        new_page.bridge.dataInserted.connect(self._on_bridge_insert)
        self.web_view.setPage(new_page)

        # keep references to these objects — otherwise Python/Qt might
        # garbage-collect them early, while the scenario is still running
        self._session_profile = profile
        self._session_page = new_page

        # the runner was bound to the old page — recreate it
        self._scenario_runner = ScenarioRunner(new_page)

    def _cleanup_session(self):
        """Clean up cookies/cache of the used session — called when the
        scenario finishes (on top of the fact that the next run gets a
        brand new profile regardless)."""
        if hasattr(self, "_session_profile"):
            self._session_profile.cookieStore().deleteAllCookies()
            self._session_profile.clearHttpCache()

    # ---------------- Playing a scenario ----------------
    def play_scenario(self):
        """Always a full restart: a fresh (off-the-record) session, from
        step 1. To resume from where it stopped — see
        pause_scenario()/resume_scenario()."""
        if hasattr(self, "_scenario_runner") and self._scenario_runner.running:
            self.log("Сценарий уже выполняется", "error")
            return
        if not self.steps:
            self.log("Нет шагов для выполнения", "error")
            return

        self.log("=== Новая сессия: очищаю куки/кэш/localStorage перед запуском ===")
        self._start_fresh_session()

        url = self.address_edit.text().strip()

        def start_after_load(ok=True):
            try:
                self._session_page.loadFinished.disconnect(start_after_load)
            except (TypeError, RuntimeError):
                pass
            self._run_loaded_scenario(resume_from=0)

        if url:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            self._session_page.loadFinished.connect(start_after_load)
            self.web_view.load(QUrl(url))
        else:
            # no URL set — go straight to running (an empty page is already "loaded")
            QTimer.singleShot(0, start_after_load)

    def pause_scenario(self):
        """Stop after the current step, WITHOUT cleaning up the session —
        the page stays as is, so you can inspect the state and continue."""
        if not hasattr(self, "_scenario_runner") or not self._scenario_runner.running:
            return
        self._scenario_runner.request_pause()
        self.pause_btn.setEnabled(False)  # until it actually stops (after the current step)

    def resume_scenario(self):
        """Continue from where it stopped — in the SAME session, no new navigation."""
        if not hasattr(self, "_scenario_runner") or self._scenario_runner.paused_at_index is None:
            return
        resume_from = self._scenario_runner.paused_at_index
        self.log(f"=== Продолжаю с шага {resume_from + 1} (та же сессия, без очистки) ===")
        self._run_loaded_scenario(resume_from=resume_from)

    def _update_run_controls(self):
        running = hasattr(self, "_scenario_runner") and self._scenario_runner.running
        paused = hasattr(self, "_scenario_runner") and self._scenario_runner.paused_at_index is not None

        self.play_btn.setEnabled(not running)
        self.pause_btn.setEnabled(running)
        self.resume_btn.setEnabled(paused and not running)

    def _run_loaded_scenario(self, resume_from=0):
        def on_step_result(index, success, result):
            if not self._web_view_alive():
                return
            item = self.steps_list.item(index)
            if item:
                c = THEMES[self.theme]
                item.setBackground(qcolor(c["success_bg"] if success else c["error_bg"]))
            self.steps_list.setCurrentRow(index)

        def on_collect(index, step, result):
            if getattr(self, "current_scenario_id", None) is None:
                self.log(f"Шаг {index + 1}: сценарий ещё не назван — результат не записан в БД.", "error")
                return
            text = "" if result is None else str(result)
            collected_data_repo.insert_row(self.db_conn, self.current_scenario_id, text)
            self.log(f"Шаг {index + 1}: результат сохранён в БД", "ok")

        def on_notify(index, step, result):
            details = f"Шаг {index + 1}: {step['js'].strip()[:120]}\nРезультат: {result}"
            email_notifier.send_manual_notification(
                self.db_conn, self.current_scenario_name or "(без имени)", details
            )
            self.log(f"Шаг {index + 1}: уведомление отправлено", "ok")

        def on_paused(next_index):
            self._update_run_controls()

        def on_finished(success):
            self._cleanup_session()
            self.log("=== Сессия очищена после завершения сценария ===")
            self._update_run_controls()

        def on_recorder_viewport(width, height):
            if width:
                self.width_spin.setValue(width)
            if height:
                self.height_spin.setValue(height)

        start_msg = f"=== Запуск сценария '{self.current_scenario_name or '(без имени)'}' ==="
        self._scenario_runner.run(
            self.steps,
            on_log=self.log,
            on_step_result=on_step_result,
            on_collect=on_collect,
            on_notify=on_notify,
            on_finished=on_finished,
            on_paused=on_paused,
            on_recorder_viewport=on_recorder_viewport,
            start_message=start_msg,
            resume_from=resume_from,
        )
        self._update_run_controls()
        