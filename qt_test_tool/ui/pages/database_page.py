"""
Страница "База данных" — просмотр collected_data (то, что сценарии
сохранили через шаг с collect=True), с ручным редактированием/удалением
и экспортом в CSV.
"""

import csv

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
)

from ...data import scenarios_repo, collected_data_repo
from ...widgets.cards import make_card


class DatabasePage(QWidget):
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

        card, card_layout = make_card("")

        btn_row = QHBoxLayout()
        self.scenario_filter = QComboBox()
        self.scenario_filter.currentIndexChanged.connect(self.refresh)
        btn_row.addWidget(self.scenario_filter)

        self.refresh_btn = QPushButton()
        self.refresh_btn.clicked.connect(self.refresh)
        btn_row.addWidget(self.refresh_btn)

        self.delete_btn = QPushButton()
        self.delete_btn.clicked.connect(self.delete_selected)
        btn_row.addWidget(self.delete_btn)

        self.export_btn = QPushButton()
        self.export_btn.setProperty("class", "primaryBtn")
        self.export_btn.clicked.connect(self.export_csv)
        btn_row.addWidget(self.export_btn)

        btn_row.addStretch()
        card_layout.addLayout(btn_row)

        self.table = QTableWidget(0, 4)
        self.table.itemChanged.connect(self._on_item_changed)
        card_layout.addWidget(self.table, stretch=1)

        layout.addWidget(card, stretch=1)
        self._suppress_item_changed = False

    def apply_theme(self):
        pass

    def retranslate(self):
        t = self.t
        self.refresh_btn.setText(t("btn_refresh"))
        self.delete_btn.setText(t("btn_delete"))
        self.export_btn.setText(t("btn_export_csv"))
        self.table.setHorizontalHeaderLabels([
            t("col_row_id"), t("col_scenario"), t("col_content"), t("col_created_at"),
        ])
        self._refresh_scenario_filter()

    def _refresh_scenario_filter(self):
        current = self.scenario_filter.currentData()
        self.scenario_filter.blockSignals(True)
        self.scenario_filter.clear()
        self.scenario_filter.addItem(self.t("filter_all_scenarios"), None)
        for s in scenarios_repo.list_scenarios():
            self.scenario_filter.addItem(s["name"], s["id"])
        idx = self.scenario_filter.findData(current)
        if idx >= 0:
            self.scenario_filter.setCurrentIndex(idx)
        self.scenario_filter.blockSignals(False)

    def refresh(self):
        self._refresh_scenario_filter()
        scenario_id = self.scenario_filter.currentData()
        rows = collected_data_repo.list_rows(self.db_conn, scenario_id)

        self._suppress_item_changed = True
        self.table.setRowCount(len(rows))
        for row_idx, row in enumerate(rows):
            id_item = QTableWidgetItem(str(row["row_id"]))
            id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_idx, 0, id_item)

            scenario_item = QTableWidgetItem(row["scenario_name"] or "—")
            scenario_item.setFlags(scenario_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_idx, 1, scenario_item)

            content_item = QTableWidgetItem(row["content_text"] or "")
            content_item.setData(1000, row["row_id"])
            self.table.setItem(row_idx, 2, content_item)

            date_item = QTableWidgetItem(row["created_at"] or "")
            date_item.setFlags(date_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_idx, 3, date_item)
        self._suppress_item_changed = False

    def _on_item_changed(self, item):
        if self._suppress_item_changed or item.column() != 2:
            return
        row_id = item.data(1000)
        if row_id is None:
            return
        collected_data_repo.update_row(self.db_conn, row_id, item.text())

    def delete_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        id_item = self.table.item(row, 0)
        if not id_item:
            return
        collected_data_repo.delete_row(self.db_conn, int(id_item.text()))
        self.refresh()

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, self.t("btn_export_csv"), "collected_data.csv", "CSV (*.csv)")
        if not path:
            return
        scenario_id = self.scenario_filter.currentData()
        rows = collected_data_repo.list_rows(self.db_conn, scenario_id)
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["row_id", "scenario_id", "scenario_name", "content_text", "created_at"])
            for row in rows:
                writer.writerow([
                    row["row_id"], row["scenario_id"], row["scenario_name"],
                    row["content_text"], row["created_at"],
                ])
        QMessageBox.information(self, "", self.t("msg_export_done") + path)
