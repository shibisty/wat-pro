"""
Страница "Уведомления" — настройка SMTP-рассылки об успехе/неудаче
прогона сценария. Пароль хранится через keyring, не в БД/settings.ini.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QCheckBox, QSpinBox, QMessageBox,
)

from ...data import notification_settings_repo
from ...notifications import email_notifier
from ...notifications.secure_storage import save_password, get_password, SecureStorageUnavailable
from ...widgets.cards import make_card


class NotificationsPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.db_conn = app.db_conn
        self.theme = app.theme
        self.language = app.language
        self._build_ui()
        self.apply_theme()
        self.retranslate()
        self._load_settings()

    def t(self, key: str) -> str:
        return self.app.t(key)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        card, card_layout = make_card("")

        def row(label_widget, field_widget):
            r = QHBoxLayout()
            label_widget.setMinimumWidth(160)
            r.addWidget(label_widget)
            r.addWidget(field_widget, stretch=1)
            card_layout.addLayout(r)

        self.lbl_host = QLabel()
        self.host_edit = QLineEdit()
        row(self.lbl_host, self.host_edit)

        self.lbl_port = QLabel()
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(587)
        row(self.lbl_port, self.port_spin)

        self.lbl_username = QLabel()
        self.username_edit = QLineEdit()
        row(self.lbl_username, self.username_edit)

        self.lbl_password = QLabel()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        row(self.lbl_password, self.password_edit)

        self.lbl_from = QLabel()
        self.from_edit = QLineEdit()
        row(self.lbl_from, self.from_edit)

        self.lbl_to = QLabel()
        self.to_edit = QLineEdit()
        row(self.lbl_to, self.to_edit)

        self.tls_check = QCheckBox()
        card_layout.addWidget(self.tls_check)
        self.notify_success_check = QCheckBox()
        card_layout.addWidget(self.notify_success_check)
        self.notify_failure_check = QCheckBox()
        card_layout.addWidget(self.notify_failure_check)

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton()
        self.save_btn.setProperty("class", "primaryBtn")
        self.save_btn.clicked.connect(self.save_settings)
        btn_row.addWidget(self.save_btn)

        self.test_btn = QPushButton()
        self.test_btn.clicked.connect(self.send_test)
        btn_row.addWidget(self.test_btn)
        btn_row.addStretch()
        card_layout.addLayout(btn_row)

        card_layout.addStretch()
        layout.addWidget(card, stretch=1)

    def apply_theme(self):
        pass

    def retranslate(self):
        t = self.t
        self.lbl_host.setText(t("lbl_smtp_host"))
        self.lbl_port.setText(t("lbl_smtp_port"))
        self.lbl_username.setText(t("lbl_username"))
        self.lbl_password.setText(t("lbl_password"))
        self.lbl_from.setText(t("lbl_from_addr"))
        self.lbl_to.setText(t("lbl_to_addr"))
        self.tls_check.setText(t("chk_use_tls"))
        self.notify_success_check.setText(t("chk_notify_success"))
        self.notify_failure_check.setText(t("chk_notify_failure"))
        self.save_btn.setText(t("btn_save_settings"))
        self.test_btn.setText(t("btn_send_test"))

    def _load_settings(self):
        settings = notification_settings_repo.get_settings(self.db_conn)
        self.host_edit.setText(settings["smtp_host"])
        self.port_spin.setValue(settings["smtp_port"])
        self.username_edit.setText(settings["username"])
        self.from_edit.setText(settings["from_addr"])
        self.to_edit.setText(settings["to_addr"])
        self.tls_check.setChecked(settings["use_tls"])
        self.notify_success_check.setChecked(settings["notify_on_success"])
        self.notify_failure_check.setChecked(settings["notify_on_failure"])
        if settings["username"]:
            try:
                pwd = get_password(settings["username"])
                if pwd:
                    self.password_edit.setText(pwd)
            except SecureStorageUnavailable:
                pass

    def _collect_settings(self) -> dict:
        return {
            "smtp_host": self.host_edit.text().strip(),
            "smtp_port": self.port_spin.value(),
            "username": self.username_edit.text().strip(),
            "from_addr": self.from_edit.text().strip(),
            "to_addr": self.to_edit.text().strip(),
            "use_tls": self.tls_check.isChecked(),
            "notify_on_success": self.notify_success_check.isChecked(),
            "notify_on_failure": self.notify_failure_check.isChecked(),
        }

    def save_settings(self):
        settings = self._collect_settings()
        notification_settings_repo.save_settings(self.db_conn, settings)
        password = self.password_edit.text()
        if settings["username"] and password:
            try:
                save_password(settings["username"], password)
            except SecureStorageUnavailable:
                QMessageBox.warning(self, "", self.t("msg_keyring_unavailable"))
                return
        QMessageBox.information(self, "", self.t("msg_settings_saved"))

    def send_test(self):
        settings = self._collect_settings()
        password = self.password_edit.text()
        try:
            email_notifier.send_test_email(settings, password)
            QMessageBox.information(self, "", self.t("msg_test_sent"))
        except Exception as e:
            QMessageBox.critical(self, "", str(e))
