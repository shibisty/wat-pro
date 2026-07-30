"""
SQLite-подключение и схема БД — только рантайм-данные, которые не нужно
передавать между пользователями как файл: собранные данные, зеркало
задач Task Scheduler, настройки уведомлений (кроме пароля — тот в
keyring). Сами сценарии — снова JSON-файлы в scenarios/ (см.
scenarios_repo.py), поэтому scenario_id здесь — просто текстовый UUID
без внешнего ключа на таблицу (такой таблицы больше нет).
"""

import os
import sqlite3

from ..core.config import APP_DIR

DB_PATH = os.path.join(APP_DIR, "app_data.sqlite3")


SCHEMA = """
CREATE TABLE IF NOT EXISTS collected_data (
    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id TEXT,
    content_text TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cron_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id TEXT NOT NULL,
    task_name TEXT NOT NULL UNIQUE,
    schedule_type TEXT NOT NULL,      -- 'once' | 'daily' | 'weekly' | 'minutely'
    schedule_value TEXT NOT NULL,     -- напр. "14:30" или "5" (минут) — интерпретация зависит от schedule_type
    enabled INTEGER NOT NULL DEFAULT 1,
    last_run_at TEXT,
    last_status TEXT,                 -- 'success' | 'failure' | NULL (ещё не запускался)
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notification_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    smtp_host TEXT,
    smtp_port INTEGER DEFAULT 587,
    username TEXT,
    from_addr TEXT,
    to_addr TEXT,
    notify_on_success INTEGER NOT NULL DEFAULT 0,
    notify_on_failure INTEGER NOT NULL DEFAULT 1,
    use_tls INTEGER NOT NULL DEFAULT 1
);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection):
    conn.executescript(SCHEMA)
    conn.commit()


def ensure_ready() -> sqlite3.Connection:
    conn = get_connection()
    init_schema(conn)
    return conn
