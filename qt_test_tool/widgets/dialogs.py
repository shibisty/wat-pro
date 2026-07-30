"""
Модальные окна: редактирование HTTP-заголовков и редактирование одного
шага сценария (с кнопкой вставки JS-рандомайзера форм).
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QCheckBox, QSpinBox, QFrame
)

from ..web.randomizer_js import RANDOMIZE_FORM_JS


class HeadersDialog(QDialog):
    def __init__(self, headers: dict, tr, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("dialog_headers_title"))
        self.resize(520, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([tr("col_header_name"), tr("col_header_value")])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        for name, value in headers.items():
            self._add_row(name, value)

        btn_row = QHBoxLayout()
        add_btn = QPushButton(tr("btn_add_row"))
        add_btn.setAutoDefault(False)
        add_btn.clicked.connect(lambda: self._add_row("", ""))
        del_btn = QPushButton(tr("btn_remove_row"))
        del_btn.setAutoDefault(False)
        del_btn.clicked.connect(self._remove_row)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        ok_row = QHBoxLayout()
        ok_row.addStretch()
        cancel_btn = QPushButton(tr("btn_cancel"))
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton(tr("btn_save_dialog"))
        ok_btn.setProperty("class", "primaryBtn")
        ok_btn.setDefault(True)
        ok_btn.setAutoDefault(True)
        ok_btn.clicked.connect(self.accept)
        ok_row.addWidget(cancel_btn)
        ok_row.addWidget(ok_btn)
        layout.addLayout(ok_row)

    def _add_row(self, name, value):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(name))
        self.table.setItem(row, 1, QTableWidgetItem(value))

    def _remove_row(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def get_headers(self):
        result = {}
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            value_item = self.table.item(row, 1)
            name = name_item.text().strip() if name_item else ""
            value = value_item.text().strip() if value_item else ""
            if name:
                result[name] = value
        return result


# ---------------------------------------------------------------------------
# Диалог добавления/редактирования одного шага сценария
# ---------------------------------------------------------------------------
class StepDialog(QDialog):
    def __init__(self, step: dict = None, tr=None, parent=None):
        super().__init__(parent)
        step = step or {}
        tr = tr or (lambda k: k)
        self.setWindowTitle(tr("dialog_step_title"))
        self.resize(560, 560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        layout.addWidget(QLabel(tr("label_js_code")))

        snippet_row = QHBoxLayout()
        snippet_row.addStretch()
        insert_randomizer_btn = QPushButton("🎲  " + tr("btn_insert_randomizer"))
        insert_randomizer_btn.setAutoDefault(False)
        insert_randomizer_btn.clicked.connect(self._insert_randomizer)
        snippet_row.addWidget(insert_randomizer_btn)
        layout.addLayout(snippet_row)

        self.js_edit = QTextEdit()
        self.js_edit.setPlainText(step.get("js", ""))
        layout.addWidget(self.js_edit)

        layout.addWidget(QLabel(tr("label_expected_result")))
        self.expected_edit = QLineEdit()
        self.expected_edit.setText(step.get("expected", ""))
        layout.addWidget(self.expected_edit)

        self.collect_check = QCheckBox(tr("chk_collect_result"))
        self.collect_check.setChecked(bool(step.get("collect", False)))
        layout.addWidget(self.collect_check)

        self.notify_check = QCheckBox(tr("chk_notify_step"))
        self.notify_check.setChecked(bool(step.get("notify", False)))
        layout.addWidget(self.notify_check)

        # ---- синхронизация: ждать переход / ждать элемент / доп. пауза ----
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(separator)

        sync_label = QLabel(tr("label_sync_section"))
        sync_label.setProperty("class", "sectionLabel")
        layout.addWidget(sync_label)

        self.wait_nav_check = QCheckBox(tr("chk_wait_navigation"))
        self.wait_nav_check.setChecked(bool(step.get("wait_for_navigation", False)))
        layout.addWidget(self.wait_nav_check)

        layout.addWidget(QLabel(tr("label_wait_selector")))
        selector_row = QHBoxLayout()
        self.wait_selector_edit = QLineEdit()
        self.wait_selector_edit.setText(step.get("wait_for_selector", ""))
        self.wait_selector_edit.setPlaceholderText(tr("placeholder_wait_selector"))
        selector_row.addWidget(self.wait_selector_edit, stretch=1)
        selector_row.addWidget(QLabel(tr("label_timeout_ms")))
        self.wait_timeout_spin = QSpinBox()
        self.wait_timeout_spin.setRange(500, 60000)
        self.wait_timeout_spin.setSingleStep(500)
        self.wait_timeout_spin.setValue(int(step.get("wait_timeout_ms", 5000) or 5000))
        self.wait_timeout_spin.setSuffix(" мс")
        selector_row.addWidget(self.wait_timeout_spin)
        layout.addLayout(selector_row)

        delay_row = QHBoxLayout()
        delay_row.addWidget(QLabel(tr("label_delay_after")))
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 30000)
        self.delay_spin.setSingleStep(100)
        self.delay_spin.setValue(int(step.get("delay_ms", 0) or 0))
        self.delay_spin.setSuffix(" мс")
        delay_row.addWidget(self.delay_spin)
        delay_row.addStretch()
        layout.addLayout(delay_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton(tr("btn_cancel"))
        cancel_btn.setAutoDefault(False)
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton(tr("btn_ok"))
        ok_btn.setProperty("class", "primaryBtn")
        ok_btn.setDefault(True)
        ok_btn.setAutoDefault(True)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def get_data(self) -> dict:
        return {
            "js": self.js_edit.toPlainText(),
            "expected": self.expected_edit.text(),
            "collect": self.collect_check.isChecked(),
            "notify": self.notify_check.isChecked(),
            "wait_for_navigation": self.wait_nav_check.isChecked(),
            "wait_for_selector": self.wait_selector_edit.text().strip(),
            "wait_timeout_ms": self.wait_timeout_spin.value(),
            "delay_ms": self.delay_spin.value(),
        }

    def _insert_randomizer(self):
        self.js_edit.setPlainText(RANDOMIZE_FORM_JS.strip())
        