"""
"Automation" page — create/delete/view scheduled tasks. The schedule is
actually stored in Windows Task Scheduler (schtasks.exe); the cron_jobs
table in SQLite is just a mirror for display.
"""

import time

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox,
    QLineEdit, QTableWidget, QTableWidgetItem, QDialog, QMessageBox,
)

from ...data import scenarios_repo, cron_jobs_repo
from ...scheduler import task_scheduler_bridge as ts
from ...widgets.cards import make_card


class CreateTaskDialog(QDialog):
    def __init__(self, scenarios, tr, parent=None):
        super().__init__(parent)
        self.tr_ = tr
        self.setWindowTitle(tr("dlg_create_task_title"))
        self.resize(420, 320)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(tr("lbl_select_scenario")))
        self.scenario_combo = QComboBox()
        for s in scenarios:
            self.scenario_combo.addItem(s["name"], s["id"])
        layout.addWidget(self.scenario_combo)

        layout.addWidget(QLabel(tr("lbl_schedule_type")))
        self.type_combo = QComboBox()
        self.type_combo.addItem(tr("schedule_daily"), "daily")
        self.type_combo.addItem(tr("schedule_weekly"), "weekly")
        self.type_combo.addItem(tr("schedule_once"), "once")
        self.type_combo.addItem(tr("schedule_minutely"), "minutely")
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        layout.addWidget(self.type_combo)

        self.value_label = QLabel(tr("lbl_time_hhmm"))
        layout.addWidget(self.value_label)
        self.value_edit = QLineEdit("09:00")
        layout.addWidget(self.value_edit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton(tr("btn_cancel"))
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton(tr("btn_ok"))
        ok_btn.setProperty("class", "primaryBtn")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _on_type_changed(self):
        schedule_type = self.type_combo.currentData()
        if schedule_type == "minutely":
            self.value_label.setText(self.tr_("lbl_minutes_interval"))
            self.value_edit.setText("15")
        else:
            self.value_label.setText(self.tr_("lbl_time_hhmm"))
            self.value_edit.setText("09:00")

    def get_data(self):
        return (
            self.scenario_combo.currentData(),
            self.scenario_combo.currentText(),
            self.type_combo.currentData(),
            self.value_edit.text().strip(),
        )


class SchedulerPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.db_conn = app.db_conn
        self.theme = app.theme
        self.language = app.language
        self._build_ui()
        self.apply_theme()
        self.retranslate()
        self.refresh()

    def t(self, key: str) -> str:
        return self.app.t(key)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        if not ts.is_supported():
            self.warning_label = QLabel()
            self.warning_label.setStyleSheet("color: #e65100; font-weight: 600;")
            layout.addWidget(self.warning_label)
        else:
            self.warning_label = None

        card, card_layout = make_card("")

        btn_row = QHBoxLayout()
        self.create_btn = QPushButton()
        self.create_btn.setProperty("class", "primaryBtn")
        self.create_btn.clicked.connect(self.create_task)
        btn_row.addWidget(self.create_btn)

        self.refresh_btn = QPushButton()
        self.refresh_btn.clicked.connect(self.refresh)
        btn_row.addWidget(self.refresh_btn)

        self.run_now_btn = QPushButton()
        self.run_now_btn.clicked.connect(self.run_selected_now)
        btn_row.addWidget(self.run_now_btn)

        self.delete_btn = QPushButton()
        self.delete_btn.clicked.connect(self.delete_selected)
        btn_row.addWidget(self.delete_btn)

        btn_row.addStretch()
        card_layout.addLayout(btn_row)

        self.table = QTableWidget(0, 6)
        card_layout.addWidget(self.table, stretch=1)

        layout.addWidget(card, stretch=1)

    def apply_theme(self):
        pass  # the table/card are styled by the global QSS via AppShell

    def retranslate(self):
        t = self.t
        if self.warning_label is not None:
            self.warning_label.setText("⚠ " + t("msg_windows_only"))
        self.create_btn.setText(t("btn_create_task"))
        self.refresh_btn.setText(t("btn_refresh"))
        self.run_now_btn.setText(t("btn_run_now"))
        self.delete_btn.setText(t("btn_delete"))
        self.table.setHorizontalHeaderLabels([
            t("col_scenario"), t("col_task_name"), t("col_schedule"),
            t("col_enabled"), t("col_last_run"), t("col_last_status"),
        ])

    def refresh(self):
        jobs = cron_jobs_repo.list_jobs(self.db_conn)
        self.table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            schedule_desc = f"{job['schedule_type']} — {job['schedule_value']}"
            values = [
                job["scenario_name"] or "—",
                job["task_name"],
                schedule_desc,
                "✓" if job["enabled"] else "—",
                job["last_run_at"] or "—",
                job["last_status"] or "—",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(1000, job["id"])  # tuck the job id away in a UserRole-like slot
                self.table.setItem(row, col, item)

    def _selected_job(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if not item:
            return None
        job_id = item.data(1000)
        return cron_jobs_repo.get_job(self.db_conn, job_id)

    def create_task(self):
        if not ts.is_supported():
            QMessageBox.warning(self, "", self.t("msg_windows_only"))
            return
        scenarios = scenarios_repo.list_scenarios()
        if not scenarios:
            QMessageBox.warning(self, "", self.t("msg_no_scenarios"))
            return
        dlg = CreateTaskDialog(scenarios, self.t, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        scenario_id, scenario_name, schedule_type, schedule_value = dlg.get_data()
        task_name = f"{ts.TASK_PREFIX}{scenario_name}_{int(time.time())}"
        try:
            ts.create_task(task_name, scenario_id, schedule_type, schedule_value)
            cron_jobs_repo.create_job(self.db_conn, scenario_id, task_name, schedule_type, schedule_value)
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "", str(e))

    def run_selected_now(self):
        job = self._selected_job()
        if not job:
            return
        try:
            ts.run_task_now(job["task_name"])
        except Exception as e:
            QMessageBox.critical(self, "", str(e))

    def delete_selected(self):
        job = self._selected_job()
        if not job:
            return
        ts.delete_task(job["task_name"])
        cron_jobs_repo.delete_job(self.db_conn, job["id"])
        self.refresh()
