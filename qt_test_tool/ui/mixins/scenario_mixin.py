"""
Управление сценариями: создание/выбор (JSON-файлы — удобно передавать
другим пользователям), редактирование шагов и запуск через ScenarioRunner.

Поведение "живое": выбор сценария в списке сразу его загружает (без
отдельной кнопки), а любое изменение (имя, URL, размер окна, шаги) сразу
сохраняется на диск (без отдельной кнопки) — см. _autosave(). Явные
кнопки остались только там, где нужна осознанная развилка: создать
новый / переименовать / удалить.

Сценарий хранит не только шаги, но и стартовый URL, размер окна браузера
(width/height) и зум — чтобы можно было один раз настроить тест под
мобильный/планшет/десктоп и оно запоминалось.

Шаги с collect=True после выполнения пишут результат в collected_data;
шаги с notify=True отправляют e-mail уведомление прямо посреди сценария
(независимо от финального успеха/неудачи всего сценария).

Каждый запуск сценария (play_scenario) стартует в СВЕЖЕЙ off-the-record
сессии (см. _start_fresh_session) — отдельный QWebEngineProfile без куки/
кэша/localStorage/IndexedDB от прошлых запусков. Это нужно, например,
когда сценарий кладёт товар в корзину: без изоляции сессии повторный
прогон видел бы уже занятую корзину от предыдущего раза и ломался бы.
После завершения сценария использованная сессия тоже подчищается
(куки/кэш), а следующий запуск в любом случае получит совсем новый
профиль.
"""

import copy

from PyQt6.QtCore import QUrl, QTimer
from PyQt6.QtWidgets import QInputDialog, QListWidgetItem, QDialog, QMessageBox
from PyQt6.QtWebEngineCore import QWebEngineProfile

from ...core.theming import THEMES, qcolor
from ...core.scenario_runner import ScenarioRunner
from ...core.i18n import ACCEPT_LANGUAGE_MAP, NAVIGATOR_LOCALE_MAP
from ...data import scenarios_repo, collected_data_repo
from ...notifications import email_notifier
from ...widgets.dialogs import StepDialog
from ...web.page import LoggingWebPage, configure_profile


class ScenarioMixin:
    def _refresh_scenario_list(self):
        self.scenario_combo.blockSignals(True)
        self.scenario_combo.clear()
        for row in scenarios_repo.list_scenarios():
            self.scenario_combo.addItem(row["name"], row["id"])
        self.scenario_combo.blockSignals(False)

    def new_scenario(self):
        name, ok = QInputDialog.getText(
            self, self.t("dialog_new_scenario_title"), self.t("dialog_new_scenario_label")
        )
        if not (ok and name.strip()):
            return
        name = name.strip()
        # создаём запись сразу — без этого автосохранению не к чему привязаться
        self.current_scenario_id = scenarios_repo.create_scenario(
            name, [], url="", width=self.width_spin.value(), height=self.height_spin.value(),
            zoom_auto=True, zoom_percent=100,
        )
        self.current_scenario_name = name
        self.steps = []
        self._refresh_steps_list()
        self._refresh_scenario_list()
        idx = self.scenario_combo.findData(self.current_scenario_id)
        if idx >= 0:
            self.scenario_combo.blockSignals(True)
            self.scenario_combo.setCurrentIndex(idx)
            self.scenario_combo.blockSignals(False)
        self.log(f"Создан новый сценарий: {self.current_scenario_name}")

    def on_scenario_selected(self, index):
        """Автозагрузка при выборе в списке — отдельной кнопки «Загрузить» больше нет."""
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

        # восстанавливаем размер окна браузера и зум, сохранённые со сценарием
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
        """Переименование текущего сценария (id/файл сохраняются, меняется только имя)."""
        if not self.current_scenario_name:
            self.log("Сначала выберите или создайте сценарий", "error")
            return
        name, ok = QInputDialog.getText(
            self, self.t("dialog_rename_scenario_title"), self.t("dialog_rename_scenario_label"),
            text=self.current_scenario_name,
        )
        if not (ok and name.strip()):
            return
        self.current_scenario_name = name.strip()
        self._autosave()

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
            # activated не всплывает при программной установке индекса —
            # подгружаем явно
            self._load_scenario(self.scenario_combo.currentData())

    def _autosave(self):
        """Тихое сохранение без диалогов/лишних логов — вызывается после
        любого изменения (шаги, имя, URL, размер), если у сценария уже
        есть имя (иначе просто нечего/некуда сохранять)."""
        if not self.current_scenario_name:
            return
        url = self.address_edit.text().strip()
        zoom_text = "".join(ch for ch in self.zoom_combo.currentText() if ch.isdigit())
        zoom_percent = int(zoom_text) if zoom_text else 100
        self.current_scenario_id = scenarios_repo.upsert_scenario_by_name(
            self.current_scenario_name, self.steps, url,
            width=self.width_spin.value(), height=self.height_spin.value(),
            zoom_auto=self.zoom_auto, zoom_percent=zoom_percent,
        )
        self._refresh_scenario_list()
        idx = self.scenario_combo.findData(self.current_scenario_id)
        if idx >= 0:
            self.scenario_combo.blockSignals(True)
            self.scenario_combo.setCurrentIndex(idx)
            self.scenario_combo.blockSignals(False)

    # ---------------- Шаги сценария ----------------

    def _refresh_steps_list(self):
        self.steps_list.clear()
        for i, step in enumerate(self.steps):
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
        """Снимок текущего списка шагов перед изменением — для Ctrl+Z."""
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
        dlg = StepDialog(step, tr=self.t, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._push_undo()
            self.steps[row] = dlg.get_data()
            self._refresh_steps_list()
            self._autosave()

    def delete_step(self):
        """Удаляет ВСЕ выделенные шаги (ExtendedSelection — Ctrl/Shift для
        множественного выбора). Работает и по кнопке 🗑️, и по клавише Delete."""
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

    # ---------------- Свежая (off-the-record) сессия для прогона ----------------

    def _start_fresh_session(self):
        """
        Создаёт новый анонимный (off-the-record) профиль WebEngine —
        отдельные куки/кэш/localStorage/IndexedDB, полностью изолированные
        от предыдущего состояния (например, товара в корзине от прошлого
        прогона). Подменяет self.web_view.page() на страницу этого нового
        профиля и пересоздаёт ScenarioRunner (он был привязан к старой
        странице — сигналы loadStarted/loadFinished слушали бы не то).
        """
        profile = QWebEngineProfile(self)  # анонимный конструктор = off-the-record, в памяти
        configure_profile(
            profile,
            self.app.interceptor,
            ACCEPT_LANGUAGE_MAP.get(self.language, ACCEPT_LANGUAGE_MAP["en"]),
            NAVIGATOR_LOCALE_MAP.get(self.language, "en-US"),
            self.theme,
        )
        new_page = LoggingWebPage(profile, self.web_view, self._on_page_console_message)
        new_page.loadFinished.connect(self._on_page_load_finished)
        self.web_view.setPage(new_page)

        # держим ссылки на объекты — иначе Python/Qt могут собрать их
        # раньше времени, пока сценарий ещё выполняется
        self._session_profile = profile
        self._session_page = new_page

        # раннер был привязан к старой странице — пересоздаём
        self._scenario_runner = ScenarioRunner(new_page)

    def _cleanup_session(self):
        """Подчистить куки/кэш использованной сессии — вызывается по
        завершении сценария (в дополнение к тому, что следующий запуск
        всё равно получит совсем новый профиль)."""
        if hasattr(self, "_session_profile"):
            self._session_profile.cookieStore().deleteAllCookies()
            self._session_profile.clearHttpCache()

    # ---------------- Воспроизведение сценария ----------------
    def play_scenario(self):
        """Всегда полный перезапуск: свежая (off-the-record) сессия, с шага 1.
        Для продолжения с места остановки — см. pause_scenario()/resume_scenario()."""
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
            # URL не задан — сразу переходим к прогону (пустая страница и так «загружена»)
            QTimer.singleShot(0, start_after_load)

    def pause_scenario(self):
        """Остановить после текущего шага, БЕЗ очистки сессии — страница
        остаётся как есть, можно посмотреть состояние и продолжить."""
        if not hasattr(self, "_scenario_runner") or not self._scenario_runner.running:
            return
        self._scenario_runner.request_pause()
        self.pause_btn.setEnabled(False)  # до фактической остановки (после текущего шага)

    def resume_scenario(self):
        """Продолжить с места остановки — в ТОЙ ЖЕ сессии, без новой навигации."""
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

        start_msg = f"=== Запуск сценария '{self.current_scenario_name or '(без имени)'}' ==="
        self._scenario_runner.run(
            self.steps,
            on_log=self.log,
            on_step_result=on_step_result,
            on_collect=on_collect,
            on_notify=on_notify,
            on_finished=on_finished,
            on_paused=on_paused,
            start_message=start_msg,
            resume_from=resume_from,
        )
        self._update_run_controls()
        