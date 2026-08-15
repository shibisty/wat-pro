"""JS console: a log with history (for redrawing on theme change), command input."""

from ...core.theming import THEMES


class ConsoleMixin:
    def log(self, text, level="info"):
        self.log_entries.append((text, level))
        self._append_log_line(text, level)

    def _append_log_line(self, text, level):
        c = THEMES[self.theme]
        color = {
            "info": c["text"],
            "ok": c["success"],
            "error": c["error"],
            "warn": c["warning"],
        }.get(level, c["text"])
        safe = text.replace("<", "&lt;").replace(">", "&gt;")
        self.console_output.append(f'<span style="color:{color}">{safe}</span>')

    def _rerender_console(self):
        """Rebuilds the entire console output for the current theme —
        otherwise old lines stay colored for the previous theme and
        become unreadable against the new background."""
        self.console_output.clear()
        for text, level in self.log_entries:
            self._append_log_line(text, level)

    def clear_console(self):
        self.log_entries = []
        self.console_output.clear()

    def run_console_command(self):
        code = self.console_input.text()
        if not code.strip():
            return
        self.console_input.add_to_history(code)
        self.console_input.clear()
        self.log(f"> {code}")
        self.web_view.page().runJavaScript(code, self._console_result_cb)

    def _console_result_cb(self, result):
        self.log(f"= {result}", "ok")

