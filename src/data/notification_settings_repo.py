"""
SMTP notification settings — everything except the password (that's
stored in keyring, see notifications/secure_storage.py). One row with
id=1 — a single configuration for the whole app.
"""

DEFAULTS = {
    "smtp_host": "",
    "smtp_port": 587,
    "username": "",
    "from_addr": "",
    "to_addr": "",
    "notify_on_success": False,
    "notify_on_failure": True,
    "use_tls": True,
}


def get_settings(conn) -> dict:
    row = conn.execute("SELECT * FROM notification_settings WHERE id = 1").fetchone()
    if not row:
        return dict(DEFAULTS)
    data = dict(row)
    data.pop("id", None)
    data["notify_on_success"] = bool(data["notify_on_success"])
    data["notify_on_failure"] = bool(data["notify_on_failure"])
    data["use_tls"] = bool(data["use_tls"])
    return data


def save_settings(conn, settings: dict):
    existing = conn.execute("SELECT id FROM notification_settings WHERE id = 1").fetchone()
    values = {**DEFAULTS, **settings}
    if existing:
        conn.execute(
            """
            UPDATE notification_settings
            SET smtp_host=?, smtp_port=?, username=?, from_addr=?, to_addr=?,
                notify_on_success=?, notify_on_failure=?, use_tls=?
            WHERE id = 1
            """,
            (
                values["smtp_host"], values["smtp_port"], values["username"],
                values["from_addr"], values["to_addr"],
                int(values["notify_on_success"]), int(values["notify_on_failure"]),
                int(values["use_tls"]),
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO notification_settings
                (id, smtp_host, smtp_port, username, from_addr, to_addr,
                 notify_on_success, notify_on_failure, use_tls)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["smtp_host"], values["smtp_port"], values["username"],
                values["from_addr"], values["to_addr"],
                int(values["notify_on_success"]), int(values["notify_on_failure"]),
                int(values["use_tls"]),
            ),
        )
    conn.commit()
