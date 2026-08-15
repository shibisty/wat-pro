"""
Scenarios are stored again as separate JSON files in scenarios/ — that
makes them easier to hand off to other users (just copy the file). Each
scenario has a stable `id` (UUID), generated once on creation — that's
what collected_data and cron_jobs in SQLite reference it by (there it's
just a plain text field, no FK to the files).

A scenario file stores: name, url (start address), width/height (browser
window size for mobile/tablet/desktop testing), zoom_auto/zoom_percent,
steps (the list of steps).
"""

import json
import os
import uuid
from datetime import datetime, timezone

from ..core.config import SCENARIOS_DIR


def _path(scenario_id: str) -> str:
    return os.path.join(SCENARIOS_DIR, f"{scenario_id}.json")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def list_scenarios() -> list:
    items = []
    if not os.path.isdir(SCENARIOS_DIR):
        return items
    for filename in os.listdir(SCENARIOS_DIR):
        if not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(SCENARIOS_DIR, filename), "r", encoding="utf-8") as f:
                data = json.load(f)
            items.append({
                "id": data.get("id", filename[:-5]),
                "name": data.get("name", filename[:-5]),
                "url": data.get("url", ""),
                "updated_at": data.get("updated_at", ""),
            })
        except Exception:
            continue
    items.sort(key=lambda x: (x["name"] or "").lower())
    return items


def get_scenario(scenario_id: str):
    path = _path(scenario_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("steps", [])
    data.setdefault("url", "")
    data.setdefault("width", 1366)
    data.setdefault("height", 768)
    data.setdefault("zoom_auto", True)
    data.setdefault("zoom_percent", 100)
    return data


def get_scenario_by_name(name: str):
    for item in list_scenarios():
        if item["name"] == name:
            return get_scenario(item["id"])
    return None


def _write(data: dict):
    data["updated_at"] = _now()
    with open(_path(data["id"]), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def create_scenario(name: str, steps: list, url: str = "", width: int = 1366,
                     height: int = 768, zoom_auto: bool = True, zoom_percent: int = 100) -> str:
    scenario_id = str(uuid.uuid4())
    data = {
        "id": scenario_id,
        "name": name,
        "url": url,
        "width": width,
        "height": height,
        "zoom_auto": zoom_auto,
        "zoom_percent": zoom_percent,
        "steps": steps,
        "created_at": _now(),
    }
    _write(data)
    return scenario_id


def update_scenario(scenario_id: str, name: str, steps: list, url: str = "", width: int = 1366,
                     height: int = 768, zoom_auto: bool = True, zoom_percent: int = 100):
    data = get_scenario(scenario_id) or {"id": scenario_id, "created_at": _now()}
    data.update({
        "name": name, "url": url, "steps": steps,
        "width": width, "height": height,
        "zoom_auto": zoom_auto, "zoom_percent": zoom_percent,
    })
    _write(data)


def upsert_scenario_by_name(name: str, steps: list, url: str = "", width: int = 1366,
                             height: int = 768, zoom_auto: bool = True, zoom_percent: int = 100) -> str:
    """Save a scenario: update it if one with this name already exists, otherwise create it."""
    existing = get_scenario_by_name(name)
    if existing:
        update_scenario(existing["id"], name, steps, url, width, height, zoom_auto, zoom_percent)
        return existing["id"]
    return create_scenario(name, steps, url, width, height, zoom_auto, zoom_percent)


def delete_scenario(scenario_id: str):
    path = _path(scenario_id)
    if os.path.exists(path):
        os.remove(path)


def ensure_ready():
    os.makedirs(SCENARIOS_DIR, exist_ok=True)
