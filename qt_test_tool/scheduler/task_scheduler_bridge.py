"""
Обёртка над Windows Task Scheduler (schtasks.exe). Именно ОС отвечает за
"будить" процесс в нужное время, даже если приложение закрыто — сама
таблица cron_jobs в SQLite только зеркалит состояние для отображения.

Работает только на Windows; на других ОС create_task()/run_task_now()
поднимают RuntimeError с понятным сообщением.
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
    Предпочитаем pythonw.exe (без консольного окна) — типичный трюк:
    рядом с python.exe в том же окружении почти всегда лежит pythonw.exe.
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
      - 'once' / 'daily' / 'weekly' -> время в формате "HH:MM"
      - 'minutely' -> число минут между запусками, например "15"
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
    