"""
Runs a scenario's steps as JS on the page — independent of Qt widgets
(other than the QWebEnginePage itself, without which there's no JS to
run, and QTimer for delays/polling). Used by the interactive scenario
editor window, and in the future by the headless CLI mode for cron jobs,
so step-execution logic isn't duplicated in two places.

Page-load synchronization (three mechanisms):

- Automatic navigation detection (ALWAYS on, no configuration needed): if
  a step (e.g. a link click) triggers navigation, the runner notices it
  itself via loadStarted/loadFinished and waits for it to finish before
  the next step. This is the main scenario that used to run "without
  waiting for the load" — now it works out of the box, nothing needs to
  be flagged manually.
- wait_for_navigation (optional step flag): forces waiting for
  navigation, even if auto-detection somehow missed it (e.g. navigation
  starts noticeably later — outside the short check window right after
  the step itself).
- wait_for_selector: before running the step's JS, wait (by polling)
  until an element matching the CSS selector appears on the page — needed
  for modals/popups that appear with a delay (unrelated to page
  navigation, so it can't be auto-detected).
- delay_ms: a simple fixed pause after the step — a blunt but reliable
  fallback for cases the options above don't cover.

Technical details of auto-detection: we first tried waiting via
`return new Promise(...)` inside the JS — didn't work, verified
empirically: QWebEnginePage.runJavaScript() in this particular Qt/Chromium
combo does NOT wait for a Promise to resolve, it returns an empty object
almost instantly. Instead of connect/disconnect on loadFinished (which
creates a race: on a fast/local navigation, loadFinished can sometimes
fire BEFORE we even decide to wait for it — then waiting for a new signal
would hang until the timeout), we use a persistent subscription to
loadStarted/loadFinished with two flags and explicit polling of those flags.
"""

from PyQt6.QtCore import QTimer

_POLL_INTERVAL_MS = 200
_NAVIGATION_TIMEOUT_MS = 15000
_NAV_DETECT_GRACE_MS = 350  # window after a step to notice a slightly delayed navigation start


class ScenarioRunner:
    def __init__(self, page):
        self.page = page
        self.running = False
        self._steps = []
        self._on_log = lambda text, level="info": None
        self._on_step_result = lambda index, success, result: None
        self._on_finished = lambda success: None
        self._on_collect = lambda index, step, result: None
        self._on_notify = lambda index, step, result: None
        self._on_paused = lambda index: None

        # Pause: requested via request_pause(), actually applied in
        # _continue_after_step() — the single "junction point" between
        # steps. Stopping JS execution RIGHT IN THE MIDDLE of a step isn't
        # possible (it's already off inside runJavaScript), so pause
        # always kicks in "after the current step, before the next one" —
        # which is exactly what's needed for debugging: you see the state
        # strictly between two steps.
        self._pause_requested = False
        self.paused_at_index = None  # not None = the scenario is paused, can resume from this index

        # Automatic navigation detection: a persistent subscription plus
        # two flags, instead of connect/disconnect on every step — this
        # removes the race where a fast navigation manages to start and
        # finish BEFORE we even decide whether to wait for it or not.
        self._nav_started = False
        self._nav_finished = False
        self.page.loadStarted.connect(self._mark_nav_started)
        self.page.loadFinished.connect(self._mark_nav_finished)

    def _mark_nav_started(self):
        self._nav_started = True
        self._nav_finished = False

    def _mark_nav_finished(self, ok=None):
        self._nav_finished = True

    def run(self, steps, on_log=None, on_step_result=None, on_finished=None,
            start_message=None, on_collect=None, on_notify=None, on_paused=None,
            resume_from=0):
        """
        steps: [{
            "js": str, "expected": str, "collect": bool, "notify": bool,
            "wait_for_navigation": bool,       # force waiting for navigation
            "wait_for_selector": str,          # CSS selector, wait before the step
            "wait_timeout_ms": int,            # selector wait timeout
            "delay_ms": int,                   # extra pause after the step
        }, ...]
        on_log(text, level="info"|"ok"|"error")
        on_step_result(index, success: bool, result) — called after each step
        on_finished(success: bool) — called once at the end (success/failure,
            NOT called on pause — see on_paused)
        on_paused(next_index: int) — called when the scenario is paused
            (request_pause()); next_index is which step to resume from
        on_collect(index, step, result) — called for steps with collect=True
        on_notify(index, step, result) — called for steps with notify=True
        start_message: if set, printed instead of the standard "Running scenario"
        resume_from: step index to start from (0 — from the beginning; to
            resume after a pause, pass runner.paused_at_index)
        """
        if self.running:
            if on_log:
                on_log("Сценарий уже выполняется", "error")
            return
        if not steps:
            if on_log:
                on_log("Нет шагов для выполнения", "error")
            return

        self._steps = steps
        self._on_log = on_log or self._on_log
        self._on_step_result = on_step_result or self._on_step_result
        self._on_finished = on_finished or self._on_finished
        self._on_collect = on_collect or self._on_collect
        self._on_notify = on_notify or self._on_notify
        self._on_paused = on_paused or self._on_paused

        self.running = True
        self._pause_requested = False
        self.paused_at_index = None
        self._on_log(start_message or "=== Запуск сценария ===")
        self._run_step(resume_from)

    def request_pause(self):
        """
        Ask to stop after the current step (not instantly — a step that's
        already running will finish first). The session/page is NOT
        touched — it just stops the step loop, so you can inspect the
        state and continue from the same point via
        run(steps, resume_from=runner.paused_at_index).
        """
        if self.running:
            self._pause_requested = True

    # ---------------- Main loop ----------------

    def _run_step(self, index):
        if index >= len(self._steps):
            self.running = False
            self._on_log("=== Сценарий завершён успешно ===", "ok")
            self._on_finished(True)
            return

        step = self._steps[index]
        selector = (step.get("wait_for_selector") or "").strip()

        if selector:
            timeout_ms = int(step.get("wait_timeout_ms") or 5000)
            self._on_log(f"Шаг {index + 1}: жду появления элемента «{selector}»…")
            self._poll_for_selector(index, selector, timeout_ms, 0)
        else:
            self._execute_step(index)

    def _poll_for_selector(self, index, selector, timeout_ms, elapsed_ms):
        if not self.running:
            return  # the scenario was stopped while we were waiting

        if elapsed_ms >= timeout_ms:
            self._on_log(
                f"Шаг {index + 1}: элемент «{selector}» не появился за {timeout_ms} мс — "
                f"выполняю шаг как есть",
                "error",
            )
            self._execute_step(index)
            return

        safe_selector = selector.replace("\\", "\\\\").replace("'", "\\'")
        check_js = f"document.querySelector('{safe_selector}') !== null"

        def on_check(found):
            if not self.running:
                return
            if found:
                self._execute_step(index)
            else:
                QTimer.singleShot(
                    _POLL_INTERVAL_MS,
                    lambda: self._poll_for_selector(index, selector, timeout_ms, elapsed_ms + _POLL_INTERVAL_MS),
                )

        self.page.runJavaScript(check_js, on_check)

    def _execute_step(self, index):
        step = self._steps[index]
        self._on_log(f"Шаг {index + 1}: {step['js'].strip()[:80]}")

        # reset the flags before the step — from here on we watch whether
        # THIS step triggered page navigation (e.g. a link click)
        self._nav_started = False
        self._nav_finished = False

        def callback(result):
            if step.get("collect"):
                try:
                    self._on_collect(index, step, result)
                except Exception as e:
                    self._on_log(f"Не удалось сохранить результат шага {index + 1} в БД: {e}", "error")

            if step.get("notify"):
                try:
                    self._on_notify(index, step, result)
                except Exception as e:
                    self._on_log(f"Не удалось отправить уведомление на шаге {index + 1}: {e}", "error")

            expected = step.get("expected", "")
            if expected.strip():
                actual_str = "" if result is None else str(result)
                if actual_str != expected:
                    self._on_log(
                        f"✗ Шаг {index + 1} провален. Ожидалось: {expected!r}, "
                        f"получено: {actual_str!r}",
                        "error",
                    )
                    self._on_step_result(index, False, result)
                    self.running = False
                    self._on_log(f"=== Сценарий остановлен на шаге {index + 1} ===", "error")
                    self._on_finished(False)
                    return
                self._on_log(f"✓ Шаг {index + 1} успешен", "ok")
                self._on_step_result(index, True, result)
            else:
                self._on_log(f"✓ Шаг {index + 1} выполнен, результат: {result}", "ok")
                self._on_step_result(index, True, result)

            # short window to notice navigation that started not
            # synchronously during JS execution but slightly later (the
            # next event loop tick) — without this, fast steps would race
            # ahead before the page even had a chance to start loading
            QTimer.singleShot(_NAV_DETECT_GRACE_MS, lambda: self._after_step_grace(index))

        self.page.runJavaScript(step["js"], callback)

    def _after_step_grace(self, index):
        if not self.running:
            return
        step = self._steps[index]
        if step.get("wait_for_navigation") or self._nav_started:
            self._poll_nav_finished(index, 0)
        else:
            self._continue_after_step(index)

    def _poll_nav_finished(self, index, elapsed_ms):
        if not self.running:
            return
        if self._nav_finished:
            self._on_log(f"Шаг {index + 1}: переход завершён", "ok")
            self._continue_after_step(index)
            return
        if elapsed_ms >= _NAVIGATION_TIMEOUT_MS:
            self._on_log(
                f"Шаг {index + 1}: не дождался перехода за {_NAVIGATION_TIMEOUT_MS} мс, продолжаю",
                "error",
            )
            self._continue_after_step(index)
            return
        QTimer.singleShot(
            _POLL_INTERVAL_MS,
            lambda: self._poll_nav_finished(index, elapsed_ms + _POLL_INTERVAL_MS),
        )

    def _continue_after_step(self, index):
        if self._pause_requested:
            self._pause_requested = False
            self.running = False
            self.paused_at_index = index + 1
            self._on_log(f"=== Сценарий поставлен на паузу после шага {index + 1} ===", "info")
            self._on_paused(self.paused_at_index)
            return

        delay_ms = int(self._steps[index].get("delay_ms") or 0)
        if delay_ms > 0:
            QTimer.singleShot(delay_ms, lambda: self._run_step(index + 1))
        else:
            self._run_step(index + 1)
