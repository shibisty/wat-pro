"""
Классы-обвязки над QtWebEngine: страница с перехватом console.log/warn/error,
перехватчик HTTP-заголовков, авто-подгоняемая область прокрутки под браузер,
и JS, который пробрасывает язык/тему приложения в саму веб-страницу.
"""

from PyQt6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineUrlRequestInterceptor, QWebEngineScript
)

from .inspect_js import RESOURCE_OBSERVER_INSTALL_JS


def build_page_init_script(navigator_language: str, theme: str) -> str:
    """
    JS, который встраивается в КАЖДУЮ страницу до её собственных скриптов:
    - подменяет navigator.language/languages под выбранный язык приложения;
    - подменяет window.matchMedia('(prefers-color-scheme: ...)') под текущую
      тему, чтобы JS-логика сайта (не CSS!) видела то же самое, что видит
      пользователь в самом приложении — примерно то, что делает эмуляция
      в Chrome DevTools.

    В отличие от первой версии, здесь заводится ПЕРСИСТЕНТНОЕ состояние
    (window.__qttThemeState) и реальные addEventListener('change', ...) на
    matchMedia реально сохраняются и вызываются — чтобы сайты, которые
    следят за сменой темы в реальном времени (а не только при загрузке),
    тоже реагировали, когда пользователь переключает тему/язык прямо в уже
    открытой странице (см. build_live_update_script — его гоняют повторно
    при каждом переключении, не переопределяя matchMedia заново).
    """
    is_dark = "true" if theme == "dark" else "false"
    return f"""
    (function() {{
        if (!window.__qttThemeState) {{
            window.__qttThemeState = {{ isDark: {is_dark}, listeners: [] }};

            try {{
                var __origMatchMedia = window.matchMedia ? window.matchMedia.bind(window) : null;
                window.matchMedia = function(query) {{
                    if (typeof query === 'string' && query.indexOf('prefers-color-scheme') !== -1) {{
                        var wantsDark = query.indexOf('dark') !== -1;
                        var mql = {{
                            media: query,
                            onchange: null,
                            get matches() {{
                                return wantsDark ? window.__qttThemeState.isDark : !window.__qttThemeState.isDark;
                            }},
                            addListener: function(cb) {{
                                window.__qttThemeState.listeners.push({{ cb: cb, wantsDark: wantsDark, mql: mql }});
                            }},
                            removeListener: function(cb) {{
                                window.__qttThemeState.listeners = window.__qttThemeState.listeners.filter(
                                    function(l) {{ return l.cb !== cb; }}
                                );
                            }},
                            addEventListener: function(type, cb) {{ if (type === 'change') mql.addListener(cb); }},
                            removeEventListener: function(type, cb) {{ if (type === 'change') mql.removeListener(cb); }},
                            dispatchEvent: function() {{ return false; }},
                        }};
                        return mql;
                    }}
                    return __origMatchMedia ? __origMatchMedia(query) : {{ matches: false, media: query }};
                }};
            }} catch (e) {{}}

            window.__qttSetTheme = function(isDark) {{
                window.__qttThemeState.isDark = isDark;
                try {{ document.documentElement.style.colorScheme = isDark ? 'dark' : 'light'; }} catch (e) {{}}
                window.__qttThemeState.listeners.slice().forEach(function(l) {{
                    try {{
                        var matches = l.wantsDark ? isDark : !isDark;
                        var evt = {{ matches: matches, media: l.mql.media }};
                        if (typeof l.cb === 'function') l.cb(evt);
                        if (typeof l.mql.onchange === 'function') l.mql.onchange(evt);
                    }} catch (e) {{}}
                }});
            }};

            window.__qttSetLanguage = function(lang) {{
                try {{
                    Object.defineProperty(navigator, 'language', {{ get: function() {{ return lang; }}, configurable: true }});
                    Object.defineProperty(navigator, 'languages', {{ get: function() {{ return [lang]; }}, configurable: true }});
                }} catch (e) {{}}
            }};
        }}

        window.__qttSetLanguage('{navigator_language}');
        window.__qttSetTheme({is_dark});
    }})();
    """


def build_live_update_script(navigator_language: str, theme: str) -> str:
    """
    Лёгкий скрипт для УЖЕ загруженной страницы — обновляет тему/язык через
    ранее установленные window.__qttSetTheme/__qttSetLanguage (не трогая
    matchMedia заново, чтобы не терять подписчиков на 'change'). Если
    страница ещё не содержит эту установку (например, полностью статичная
    страница без document, или скрипт почему-то не сработал) — тихо
    ничего не делает.
    """
    is_dark = "true" if theme == "dark" else "false"
    return f"""
    (function() {{
        if (window.__qttSetTheme) {{ window.__qttSetTheme({is_dark}); }}
        if (window.__qttSetLanguage) {{ window.__qttSetLanguage('{navigator_language}'); }}
    }})();
    """



def configure_profile(profile, interceptor, accept_language, navigator_language, theme):
    """
    Единая настройка любого профиля WebEngine — и общего (defaultProfile,
    обычный интерактивный браузинг), и одноразового off-the-record
    профиля для прогона сценария (см. ScenarioMixin._start_fresh_session):
    подставляет перехватчик заголовков, Accept-Language, JS-мост
    языка/темы и наблюдатель за загруженными ресурсами (вкладка "Кэш").
    Вынесено отдельно, чтобы не дублировать эту настройку в двух местах.
    """
    profile.setUrlRequestInterceptor(interceptor)
    profile.setHttpAcceptLanguage(accept_language)
    scripts = profile.scripts()
    scripts.clear()

    bridge_script = QWebEngineScript()
    bridge_script.setName("app-theme-lang-bridge")
    bridge_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    bridge_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    bridge_script.setRunsOnSubFrames(True)
    bridge_script.setSourceCode(build_page_init_script(navigator_language, theme))
    scripts.insert(bridge_script)

    # Ставим НАБЛЮДАТЕЛЬ за ресурсами максимально рано (до скриптов самой
    # страницы) — иначе на некоторых сайтах (напр. YouTube, у которого своя
    # телеметрия сама вызывает performance.clearResourceTimings()) к моменту
    # клика на вкладку "Кэш" список окажется пустым, хотя всё реально
    # грузилось. См. web/inspect_js.py.
    resource_observer_script = QWebEngineScript()
    resource_observer_script.setName("app-resource-observer")
    resource_observer_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    resource_observer_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    resource_observer_script.setRunsOnSubFrames(True)
    resource_observer_script.setSourceCode(RESOURCE_OBSERVER_INSTALL_JS)
    scripts.insert(resource_observer_script)


# ---------------------------------------------------------------------------
# Страница с перехватом console.log/warn/error из JS самой веб-страницы
# ---------------------------------------------------------------------------
class LoggingWebPage(QWebEnginePage):
    def __init__(self, profile, parent, on_console_message):
        super().__init__(profile, parent)
        self._on_console_message = on_console_message

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        self._on_console_message(level, message, line_number, source_id)




# ---------------------------------------------------------------------------
# Перехватчик запросов — сюда подставляются кастомные HTTP-заголовки
# ---------------------------------------------------------------------------
class HeaderInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self):
        super().__init__()
        self.headers = {}  # name -> value

    def interceptRequest(self, info):
        for name, value in self.headers.items():
            if name:
                info.setHttpHeader(name.encode("utf-8"), value.encode("utf-8"))
                