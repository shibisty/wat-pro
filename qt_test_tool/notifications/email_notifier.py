"""
Sends e-mail notifications about a scenario run's success/failure.
Settings (host/port/addresses/flags) come from notification_settings_repo,
the password from secure_storage (keyring).
"""

import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate

from ..core.config import APP_NAME
from ..data import notification_settings_repo
from .secure_storage import get_password, SecureStorageUnavailable


def build_message(scenario_name: str, success: bool, details: str, from_addr: str, to_addr: str) -> MIMEText:
    status = "УСПЕШНО" if success else "ОШИБКА"
    subject = f"[{APP_NAME}] Сценарий «{scenario_name}»: {status}"
    body = (
        f"Сценарий: {scenario_name}\n"
        f"Результат: {status}\n\n"
        f"{details}"
    )
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Date"] = formatdate(localtime=True)
    return msg


def send_notification(conn, scenario_name: str, success: bool, details: str = ""):
    """
    Sends a notification if it's enabled in the settings for this
    particular result (notify_on_success / notify_on_failure). Silently
    does nothing if notifications aren't configured — but propagates an
    exception if they ARE configured and sending genuinely failed (so the
    calling code can log the problem instead of losing it silently).
    """
    settings = notification_settings_repo.get_settings(conn)

    should_notify = (success and settings["notify_on_success"]) or (
        not success and settings["notify_on_failure"]
    )
    if not should_notify:
        return False

    return _send(conn, settings, scenario_name, success, details)


def send_manual_notification(conn, scenario_name: str, details: str = ""):
    """
    Sends from an explicit scenario step with notify=True — always fires
    (not tied to notify_on_success/notify_on_failure, which only apply to
    the scenario's overall final result), but still requires SMTP to be
    configured (host + recipient).
    """
    settings = notification_settings_repo.get_settings(conn)
    return _send(conn, settings, scenario_name, True, details, subject_note="Уведомление из сценария")


def _send(conn, settings, scenario_name, success, details, subject_note=None):
    if not settings["smtp_host"] or not settings["to_addr"]:
        raise RuntimeError("Рассылка включена, но SMTP не настроен (хост/получатель пусты)")

    password = get_password(settings["username"]) if settings["username"] else None

    msg = build_message(
        scenario_name, success, details,
        settings["from_addr"] or settings["username"], settings["to_addr"],
    )
    if subject_note:
        msg.replace_header("Subject", f"[{APP_NAME}] {subject_note}: {scenario_name}")

    with smtplib.SMTP(settings["smtp_host"], settings["smtp_port"], timeout=15) as server:
        if settings["use_tls"]:
            server.starttls()
        if settings["username"] and password:
            server.login(settings["username"], password)
        server.sendmail(msg["From"], [settings["to_addr"]], msg.as_string())

    return True


def send_test_email(settings: dict, password: str):
    """Sends a test email with explicitly passed-in settings (used by the "Send test" button in the UI)."""
    msg = build_message(
        "Тестовое письмо", True,
        "Если вы получили это письмо — настройки SMTP работают корректно.",
        settings["from_addr"] or settings["username"], settings["to_addr"],
    )
    with smtplib.SMTP(settings["smtp_host"], settings["smtp_port"], timeout=15) as server:
        if settings["use_tls"]:
            server.starttls()
        if settings["username"] and password:
            server.login(settings["username"], password)
        server.sendmail(msg["From"], [settings["to_addr"]], msg.as_string())
