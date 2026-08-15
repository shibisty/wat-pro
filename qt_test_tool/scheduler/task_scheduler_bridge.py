"""
A wrapper around the Windows Task Scheduler (schtasks.exe). It's the OS
that's responsible for "waking up" the process at the right time, even
if the app is closed — the cron_jobs table in SQLite just mirrors the
state for display purposes.

Only works on Windows; on other OSes create_task()/run_task_now() raise
a RuntimeError with a clear message.
"""

import os
import platform
import subprocess
import sys

TASK_PREFIX = "QtTestTool_"


def is_supported() -> bool:
    return platform.system() == "Windows"


def _pythonw_executable() -> str:
    """
    Prefer pythonw.exe (no console window) — a common trick: pythonw.exe
    almost always sits right next to python.exe in the same environment.
    """
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        candidate = exe[: -len("python.exe")] + "pythonw.exe"
        if os.path.exists(candidate):
            return candidate
    return exe


def _build_run_command(scenario_id: str) -> str:
    pythonw = _pythonw_executable()
    return f'"{pythonw}" -m qt_test_tool.main --run-scenario {scenario_id}'


def create_task(task_name: str, scenario_id: str, schedule_type: str, schedule_value: str) -> bool:
    """
    schedule_type: 'once' | 'daily' | 'weekly' | 'minutely'
    schedule_value:
      - 'once' / 'daily' / 'weekly' -> time in "HH:MM" format
      - 'minutely' -> number of minutes between runs, e.g. "15"
    """
    if not is_supported():
        raise RuntimeError("Планировщик задач (Task Scheduler) доступен только на Windows")

    command = _build_run_command(scenario_id)
    args = ["schtasks", "/create", "/tn", task_name, "/tr", command, "/f"]

    if schedule_type == "daily":
        args += ["/sc", "daily", "/st", schedule_value]
    elif schedule_type == "weekly":
        args += ["/sc", "weekly", "/st", schedule_value]
    elif schedule_type == "once":
        args += ["/sc", "once", "/st", schedule_value]
    elif schedule_type == "minutely":
        args += ["/sc", "minute", "/mo", str(int(schedule_value))]
    else:
        raise ValueError(f"Неизвестный тип расписания: {schedule_type}")

    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"schtasks завершился с ошибкой: {(result.stderr or result.stdout).strip()}")
    return True


def delete_task(task_name: str):
    if not is_supported():
        return
    subprocess.run(["schtasks", "/delete", "/tn", task_name, "/f"], capture_output=True, text=True)


def run_task_now(task_name: str):
    if not is_supported():
        raise RuntimeError("Планировщик задач (Task Scheduler) доступен только на Windows")
    result = subprocess.run(["schtasks", "/run", "/tn", task_name], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Не удалось запустить задачу: {(result.stderr or result.stdout).strip()}")


def task_exists(task_name: str) -> bool:
    if not is_supported():
        return False
    result = subprocess.run(["schtasks", "/query", "/tn", task_name], capture_output=True, text=True)
    return result.returncode == 0
    