"""
The cron_jobs table is NOT the source of truth for scheduling (that's
Windows Task Scheduler itself) — it's a mirror for display in the UI:
what jobs exist, when they last ran and with what status. scenario_id is
the scenario's text UUID (a JSON file); the name is fetched separately
from scenarios_repo, not via a SQL JOIN.
"""

from . import scenarios_repo


def _scenario_name_map() -> dict:
    return {s["id"]: s["name"] for s in scenarios_repo.list_scenarios()}


def list_jobs(conn) -> list:
    rows = conn.execute(
        """
        SELECT id, scenario_id, task_name, schedule_type, schedule_value,
               enabled, last_run_at, last_status
        FROM cron_jobs
        ORDER BY id DESC
        """
    ).fetchall()
    names = _scenario_name_map()
    result = []
    for r in rows:
        d = dict(r)
        d["scenario_name"] = names.get(d["scenario_id"], d["scenario_id"] or "—")
        result.append(d)
    return result


def get_job(conn, job_id: int):
    row = conn.execute("SELECT * FROM cron_jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def get_job_by_task_name(conn, task_name: str):
    row = conn.execute("SELECT * FROM cron_jobs WHERE task_name = ?", (task_name,)).fetchone()
    return dict(row) if row else None


def create_job(conn, scenario_id, task_name, schedule_type, schedule_value, enabled=True) -> int:
    cur = conn.execute(
        """
        INSERT INTO cron_jobs (scenario_id, task_name, schedule_type, schedule_value, enabled)
        VALUES (?, ?, ?, ?, ?)
        """,
        (scenario_id, task_name, schedule_type, schedule_value, 1 if enabled else 0),
    )
    conn.commit()
    return cur.lastrowid


def delete_job(conn, job_id: int):
    conn.execute("DELETE FROM cron_jobs WHERE id = ?", (job_id,))
    conn.commit()


def set_enabled(conn, job_id: int, enabled: bool):
    conn.execute("UPDATE cron_jobs SET enabled = ? WHERE id = ?", (1 if enabled else 0, job_id))
    conn.commit()


def report_run_result(conn, task_name: str, success: bool):
    conn.execute(
        "UPDATE cron_jobs SET last_run_at = datetime('now'), last_status = ? WHERE task_name = ?",
        ("success" if success else "failure", task_name),
    )
    conn.commit()
