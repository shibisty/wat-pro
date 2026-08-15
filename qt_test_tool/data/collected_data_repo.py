"""
CRUD for data that scenarios save via a "collect" step
(row_id, scenario_id, content_text, created_at). scenario_id is the
scenario's text UUID (scenarios are now JSON files, not a table in this
DB), so the scenario name is fetched via a separate call to
scenarios_repo, not a SQL JOIN.
"""

from . import scenarios_repo


def _scenario_name_map() -> dict:
    return {s["id"]: s["name"] for s in scenarios_repo.list_scenarios()}


def insert_row(conn, scenario_id, content_text: str) -> int:
    cur = conn.execute(
        "INSERT INTO collected_data (scenario_id, content_text) VALUES (?, ?)",
        (scenario_id, content_text),
    )
    conn.commit()
    return cur.lastrowid


def list_rows(conn, scenario_id=None) -> list:
    if scenario_id:
        rows = conn.execute(
            "SELECT row_id, scenario_id, content_text, created_at "
            "FROM collected_data WHERE scenario_id = ? ORDER BY row_id DESC",
            (scenario_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT row_id, scenario_id, content_text, created_at "
            "FROM collected_data ORDER BY row_id DESC"
        ).fetchall()

    names = _scenario_name_map()
    result = []
    for r in rows:
        d = dict(r)
        d["scenario_name"] = names.get(d["scenario_id"], d["scenario_id"] or "—")
        result.append(d)
    return result


def update_row(conn, row_id: int, content_text: str):
    conn.execute("UPDATE collected_data SET content_text = ? WHERE row_id = ?", (content_text, row_id))
    conn.commit()


def delete_row(conn, row_id: int):
    conn.execute("DELETE FROM collected_data WHERE row_id = ?", (row_id,))
    conn.commit()


def delete_all_for_scenario(conn, scenario_id: str):
    conn.execute("DELETE FROM collected_data WHERE scenario_id = ?", (scenario_id,))
    conn.commit()
