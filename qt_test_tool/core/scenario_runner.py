"""
Прогон шагов сценария через JS на странице — не зависит от виджетов Qt
(кроме самого QWebEnginePage, без которого JS не выполнить, и QTimer для
задержек/поллинга). Используется интерактивным окном редактора сценариев,
а в будущем — headless CLI-режимом для крон-задач, чтобы не дублировать
логику выполнения шагов в двух местах.

Синхронизация с загрузкой страницы (три механизма):

- Автоопределение перехода (ВСЕГДА включено, без настройки): если шаг
  (например клик по ссылке) запускает навигацию, раннер сам это заметит
  через loadStarted/loadFinished и дождётся её завершения перед
  следующим шагом. Это основной сценарий, который раньше проходил "не
  дожидаясь загрузки" — теперь работает из коробки, ничего помечать
  вручную не нужно.
- wait_for_navigation (опциональный флаг шага): форсирует ожидание
  перехода, даже если автоопределение почему-то не сработало (например,
  навигация начинается заметно позже — за пределами короткого окна
  проверки после самого шага).
- wait_for_selector: перед выполнением JS шага дождаться (поллингом),
  пока на странице не появится элемент по CSS-селектору — нужно для
  модальных окон/воронок, которые появляются с задержкой (не связано с
  переходом страницы, поэтому не может быть определено автоматически).
- delay_ms: простая фиксированная пауза после шага — грубый, но
  надёжный fallback на случай, который не покрывают варианты выше.

Технические детали автоопределения: сначала пробовали ожидание через
`return new Promise(...)` внутри JS — не сработало, проверено
эмпирически: QWebEnginePage.runJavaScript() в этой связке Qt/Chromium
НЕ дожидается резолва Promise, а возвращает пустой объект почти
мгновенно. Вместо connect/disconnect на loadFinished (что создаёт гонку:
при быстрой/локальной навигации loadFinished иногда успевает сработать
ДО того, как мы вообще решаем его ждать — тогда ожидание нового сигнала
зависло бы до таймаута) используется постоянная подписка на
loadStarted/loadFinished с двумя флагами и явным поллингом этих флагов.
"""

from PyQt6.QtCore import QTimer

_POLL_INTERVAL_MS = 200
_NAVIGATION_TIMEOUT_MS = 15000
_NAV_DETECT_GRACE_MS = 350  # окно после шага, чтобы заметить чуть отложенный старт навигации


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

        # Пауза: запрашивается через request_pause(), а реально
        # применяется в _continue_after_step() — единственной "точке
        # стыка" между шагами. Остановить JS-выполнение ПРЯМО ПОСРЕДИ
        # шага нельзя (он уже ушёл в runJavaScript), поэтому пауза всегда
        # срабатывает "после текущего шага, перед следующим" — что как раз
        # и нужно для отладки: видно состояние строго между двумя шагами.
        self._pause_requested = False
        self.paused_at_index = None  # не None = сценарий на паузе, можно продолжить с этого индекса

        # Автоопределение перехода: постоянная подписка + два флага,
        # вместо connect/disconnect на каждый шаг — это устраняет гонку,
        # когда быстрая навигация успевает начаться и завершиться ДО того,
        # как мы вообще решаем, ждать её или нет.
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
            "wait_for_navigation": bool,       # форсировать ожидание перехода
            "wait_for_selector": str,          # CSS-селектор, ждать перед шагом
            "wait_timeout_ms": int,            # таймаут ожидания селектора
            "delay_ms": int,                   # доп. пауза после шага
        }, ...]
        on_log(text, level="info"|"ok"|"error")
        on_step_result(index, success: bool, result) — вызывается после каждого шага
        on_finished(success: bool) — вызывается один раз в конце (успех/провал,
            НЕ вызывается при паузе — см. on_paused)
        on_paused(next_index: int) — вызывается, когда сценарий поставлен на
            паузу (request_pause()); next_index — с какого шага продолжать
        on_collect(index, step, result) — вызывается для шагов с collect=True
        on_notify(index, step, result) — вызывается для шагов с notify=True
        start_message: если задано — печатается вместо стандартного "Запуск сценария"
        resume_from: индекс шага, с которого начать (0 — с начала; для
            продолжения после паузы передайте runner.paused_at_index)
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
        Попросить остановиться после текущего шага (не мгновенно — шаг,
        который уже выполняется, доработает до конца). Сессия/страница НЕ
        трогается — просто останавливается цикл шагов, чтобы можно было
        посмотреть состояние и продолжить с того же места через
        run(steps, resume_from=runner.paused_at_index).
        """
        if self.running:
            self._pause_requested = True

    # ---------------- Основной цикл ----------------

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
            return  # сценарий остановили, пока ждали

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

        # сбрасываем флаги перед шагом — далее следим, не вызвал ли ЭТОТ
        # шаг переход страницы (клик по ссылке и т.п.)
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

            # короткое окно, чтобы заметить навигацию, которая стартовала
            # не синхронно в момент выполнения JS, а чуть позже (следующий
            # тик event loop) — без этого быстрые шаги срывались бы дальше
            # до того, как страница вообще успевала начать грузиться
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
            