"""
Тема оформления, язык интерфейса и проброс языка/темы в саму веб-страницу.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineScript

from ...core.i18n import (
    SUPPORTED_LANGUAGES, RTL_LANGUAGES, ACCEPT_LANGUAGE_MAP, NAVIGATOR_LOCALE_MAP,
    load_translations,
)
from ...core.theming import THEMES, build_stylesheet
from ...core.system_theme import apply_native_titlebar_theme
from ...web.page import build_page_init_script


class ThemeLangMixin:
    def t(self, key: str) -> str:
        """Перевод строки интерфейса по ключу текущего языка (с фолбэком на английский/сам ключ)."""
        return self.tr_dict.get(key, key)

    def retranslate_ui(self):
        """Проставляет тексты/тултипы текущего языка на все виджеты интерфейса."""
        t = self.t
        self.new_scen_btn.setToolTip(t("tooltip_new_scenario"))
        self.scenario_combo.setToolTip(t("tooltip_scenario_select"))
        self.load_scen_btn.setText("📂  " + t("btn_load"))
        self.save_btn.setToolTip(t("btn_save"))
        self.lang_combo.setToolTip(t("tooltip_language_select"))
        self.theme_btn.setToolTip(t("tooltip_theme_toggle"))

        self.headers_btn.setText("⚙  " + t("btn_headers"))
        self.randomize_btn.setText("🎲  " + t("btn_randomize_form"))
        self.randomize_btn.setToolTip(t("tooltip_randomize_form"))

        self.scenario_section_label.setText(t("section_scenario_steps"))
        self.add_step_btn.setToolTip(t("tooltip_add_step"))
        self.edit_step_btn.setToolTip(t("tooltip_edit_step"))
        self.delete_step_btn.setToolTip(t("tooltip_delete_step"))
        self.move_up_btn.setToolTip(t("tooltip_move_up"))
        self.move_down_btn.setToolTip(t("tooltip_move_down"))
        self.play_btn.setText("▶  " + t("btn_play"))

        self.console_title.setText(t("section_console"))
        self.clear_console_btn.setText("🗑  " + t("btn_clear_console"))
        self.console_input.setPlaceholderText(t("console_placeholder"))

        self.back_btn.setToolTip(t("tooltip_back"))
        self.fwd_btn.setToolTip(t("tooltip_forward"))
        self.reload_btn.setToolTip(t("tooltip_reload"))
        self.address_edit.setPlaceholderText(t("address_placeholder"))
        self.go_btn.setText(t("btn_go"))

        self.device_screen_label.setText(t("device_label_screen"))
        self.device_preset_combo.setItemText(0, t("device_preset_placeholder"))
        self.device_zoom_label.setText(t("device_label_zoom"))
        self.zoom_combo.blockSignals(True)
        self.zoom_combo.setItemText(0, t("zoom_auto"))
        if self.zoom_auto:
            self.zoom_combo.setEditText(t("zoom_auto"))
        self.zoom_combo.blockSignals(False)

        self.html_section_label.setText(t("section_html_source"))

    def _install_page_scripts(self):
        """
        Устанавливает JS-скрипт, который выполняется на КАЖДОЙ странице ДО
        её собственного кода — так же, как эмуляция языка/темы в Chrome
        DevTools влияет на то, что видит сайт.

        Регистрируем скрипт и на уровне профиля (применяется ко всем
        страницам, использующим этот профиль), и на уровне конкретной
        страницы (page.scripts()) — на случай версионных особенностей
        конкретной сборки Qt WebEngine, где применение скриптов профиля
        к уже созданному QWebEngineView может отличаться.
        """
        nav_lang = NAVIGATOR_LOCALE_MAP.get(self.language, "en-US")
        source = build_page_init_script(nav_lang, self.theme)

        def _make_script():
            script = QWebEngineScript()
            script.setName("app-theme-lang-bridge")
            script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            script.setRunsOnSubFrames(True)
            script.setSourceCode(source)
            return script

        profile = QWebEngineProfile.defaultProfile()
        profile_scripts = profile.scripts()
        profile_scripts.clear()
        profile_scripts.insert(_make_script())

        if hasattr(self, "web_view") and self.web_view.page() is not None:
            page_scripts = self.web_view.page().scripts()
            page_scripts.clear()
            page_scripts.insert(_make_script())

    # ---------------- UI ----------------

    def apply_theme(self):
        self.setStyleSheet(build_stylesheet(self.theme))
        # переприменяем стиль ко всем виджетам с "class"-свойством (Qt не делает это сам)
        for w in self.findChildren(QWidget):
            w.style().unpolish(w)
            w.style().polish(w)
        apply_native_titlebar_theme(self, self.theme == "dark")
        c = THEMES[self.theme]
        self.web_view.page().setBackgroundColor(QColor(c["surface"]))
        if hasattr(self, "console_output"):
            self._rerender_console()
        if hasattr(self, "html_viewer"):
            self.html_viewer.set_editor_colors(
                c["code_bg"], c["code_text"], c["code_linenum_bg"], c["code_linenum_text"]
            )
            self.html_highlighter.set_colors(c)
        if self.theme == "light":
            self.theme_btn.setText("🌙")
        else:
            self.theme_btn.setText("☀️")
        # пробрасываем тему в саму страницу браузера (prefers-color-scheme)
        self._install_page_scripts()
        nav_lang = NAVIGATOR_LOCALE_MAP.get(self.language, "en-US")
        self.web_view.page().runJavaScript(build_page_init_script(nav_lang, self.theme))

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.settings.setValue("profile/theme", self.theme)
        self.settings.sync()
        self.apply_theme()

    def on_language_changed(self, index):
        code = self.lang_combo.itemData(index)
        if not code or code == self.language:
            return
        self.language = code
        self.settings.setValue("profile/language", self.language)
        self.settings.sync()
        self.tr_dict = load_translations(self.language)
        QApplication.instance().setLayoutDirection(
            Qt.LayoutDirection.RightToLeft if self.language in RTL_LANGUAGES else Qt.LayoutDirection.LeftToRight
        )
        QWebEngineProfile.defaultProfile().setHttpAcceptLanguage(
            ACCEPT_LANGUAGE_MAP.get(self.language, ACCEPT_LANGUAGE_MAP["en"])
        )
        self._install_page_scripts()
        nav_lang = NAVIGATOR_LOCALE_MAP.get(self.language, "en-US")
        self.web_view.page().runJavaScript(build_page_init_script(nav_lang, self.theme))
        self.retranslate_ui()
        self.log(f"Язык интерфейса: {SUPPORTED_LANGUAGES[self.language]}")

