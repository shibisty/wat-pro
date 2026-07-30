"""
Точка входа приложения.

Обычный запуск (GUI):
    python run.py

Headless-прогон одного сценария (вызывается Windows Task Scheduler'ом,
см. scheduler/task_scheduler_bridge.py):
    python -m qt_test_tool.main --run-scenario 3
"""

import argparse
import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from .core.config import APP_NAME, APP_FULL_NAME, ICON_PATH


def run_gui():
    from .ui.shell import AppShell

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_FULL_NAME)
    app.setWindowIcon(QIcon(ICON_PATH))
    win = AppShell()
    win.show()
    sys.exit(app.exec())


def run_headless(scenario_id: str):
    """
    Открывает URL сценария, прогоняет шаги через тот же ScenarioRunner,
    что и интерактивный редактор, пишет collect-результаты в БД, обновляет
    статус последнего запуска в cron_jobs и (если настроено) отправляет
    e-mail уведомление об успехе/неудаче.

    Как и интерактивный прогон (см. ScenarioMixin._start_fresh_session),
    использует off-the-record профиль — каждый запуск (даже в отдельном
    процессе, как здесь) получает чистую сессию без куки/кэша от прошлого
    раза. Это важно и для headless-режима: обычный defaultProfile хранит
    данные на диске между отдельными запусками процесса, так что без
    явного off-the-record тут тоже можно было бы словить "уже лежит в
    корзине" при повторном прогоне по расписанию.
    """
    from PyQt6.QtCore import QUrl
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineProfile

    from .core.scenario_runner import ScenarioRunner
    from .core.i18n import ACCEPT_LANGUAGE_MAP, NAVIGATOR_LOCALE_MAP
    from .data import database, scenarios_repo, collected_data_repo, cron_jobs_repo
    from .notifications import email_notifier
    from .web.page import LoggingWebPage, HeaderInterceptor, configure_profile

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    conn = database.ensure_ready()
    scenarios_repo.ensure_ready()
    scenario = scenarios_repo.get_scenario(scenario_id)
    if not scenario:
        print(f"Сценарий id={scenario_id} не найден", file=sys.stderr)
        sys.exit(1)

    profile = QWebEngineProfile()  # анонимный конструктор = off-the-record, свежая сессия
    interceptor = HeaderInterceptor()
    configure_profile(profile, interceptor, ACCEPT_LANGUAGE_MAP["en"], NAVIGATOR_LOCALE_MAP["en"], "light")

    view = QWebEngineView()
    view.setPage(LoggingWebPage(profile, view, lambda *a: None))
    view.setFixedSize(scenario.get("width", 1366), scenario.get("height", 768))
    # Зум — чисто визуальный масштаб для просмотра глазами (см.
    # web/zoomable_canvas.py), в headless-режиме показывать нечего, а
    # применение zoomFactor исказило бы window.innerWidth/innerHeight и
    # тестировало бы не тот viewport, что задан в сценарии — поэтому здесь
    # он намеренно не применяется.
    log_lines = []

    def log(text, level="info"):
        log_lines.append(f"[{level}] {text}")
        print(text)

    def on_collect(index, step, result):
        text = "" if result is None else str(result)
        collected_data_repo.insert_row(conn, scenario_id, text)

    def finish(success):
        for job in cron_jobs_repo.list_jobs(conn):
            if job["scenario_id"] == scenario_id:
                cron_jobs_repo.report_run_result(conn, job["task_name"], success)

        details = "\n".join(log_lines[-20:])
        try:
            email_notifier.send_notification(conn, scenario["name"], success, details)
        except Exception as e:
            print(f"Не удалось отправить уведомление: {e}", file=sys.stderr)

        conn.close()
        app.quit()

    def on_load_finished(ok):
        if not ok:
            log("Не удалось загрузить страницу", "error")
            finish(False)
            return
        runner = ScenarioRunner(view.page())
        runner.run(
            scenario["steps"],
            on_log=log,
            on_collect=on_collect,
            on_finished=finish,
            start_message=f"=== Headless-прогон сценария '{scenario['name']}' ===",
        )

    url = (scenario.get("url") or "").strip()
    if not url:
        log("У сценария не задан URL — нечего открывать", "error")
        finish(False)
    else:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        view.page().loadFinished.connect(on_load_finished)
        view.load(QUrl(url))

    sys.exit(app.exec())


def main():
    parser = argparse.ArgumentParser(description=APP_FULL_NAME)
    parser.add_argument(
        "--run-scenario", type=str, metavar="ID",
        help="Headless-прогон сценария по id (для запуска из Планировщика заданий)",
    )
    args = parser.parse_args()

    if args.run_scenario is not None:
        run_headless(args.run_scenario)
    else:
        run_gui()


if __name__ == "__main__":
    main()
    