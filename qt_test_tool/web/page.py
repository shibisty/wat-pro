"""
Wrapper classes around QtWebEngine: a page with console.log/warn/error
interception, an HTTP header interceptor, an auto-fitting scroll area for
the browser, and JS that forwards the app's language/theme into the web
page itself.
"""

from PyQt6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineUrlRequestInterceptor, QWebEngineScript
)
from PyQt6.QtWebChannel import QWebChannel

from .inspect_js import RESOURCE_OBSERVER_INSTALL_JS
from .library_inject import build_library_inject_script
from .bridge import PyBridge, build_bridge_setup_script


def build_page_init_script(navigator_language: str, theme: str) -> str:
    """
    JS injected into EVERY page before its own scripts run:
    - overrides navigator.language/languages to match the app's chosen language;
    - overrides window.matchMedia('(prefers-color-scheme: ...)') to match
      the current theme, so the site's JS logic (not CSS!) sees the same
      thing the user sees in the app itself — roughly what Chrome
      DevTools' emulation does.

    Unlike the first version, this sets up PERSISTENT state
    (window.__qttThemeState), and real addEventListener('change', ...)
    calls on matchMedia are actually kept and invoked — so sites that
    watch for theme changes in real time (not just on load) also react
    when the user switches the theme/language right on an already-open
    page (see build_live_update_script — it's re-run on every switch,
    without redefining matchMedia again).
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
    A lightweight script for an ALREADY loaded page — updates the
    theme/language via the previously installed
    window.__qttSetTheme/__qttSetLanguage (without touching matchMedia
    again, so 'change' subscribers aren't lost). If the page doesn't have
    this setup yet (e.g. a fully static page with no document, or the
    script somehow didn't run) — it silently does nothing.
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
    Single point of configuration for any WebEngine profile — both the
    shared one (defaultProfile, regular interactive browsing) and a
    one-off off-the-record profile for a scenario run (see
    ScenarioMixin._start_fresh_session): sets the header interceptor,
    Accept-Language, the language/theme JS bridge, and the loaded-resource
    observer (the "Cache" tab). Factored out so this setup isn't
    duplicated in two places.
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

    # Set up the resource OBSERVER as early as possible (before the page's
    # own scripts) — otherwise on some sites (e.g. YouTube, whose own
    # telemetry calls performance.clearResourceTimings() itself) the list
    # would be empty by the time you click the "Cache" tab, even though
    # everything really did load. See web/inspect_js.py.
    resource_observer_script = QWebEngineScript()
    resource_observer_script.setName("app-resource-observer")
    resource_observer_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
    resource_observer_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    resource_observer_script.setRunsOnSubFrames(True)
    resource_observer_script.setSourceCode(RESOURCE_OBSERVER_INSTALL_JS)
    scripts.insert(resource_observer_script)

    # g$/g_ (jQuery/lodash under non-standard names, without touching the
    # page's own $/_ if present) — see web/library_inject.py.
    #
    # IMPORTANT: DocumentReady (~DOMContentLoaded), NOT DocumentCreation.
    # Originally used the earliest injection point (like the theme/lang
    # bridge), but on real sites with heavy trackers/redirects (TikTok
    # Pixel, reCAPTCHA, etc.) the document sometimes isn't fully settled
    # yet at DocumentCreation. lodash handles this fine (doesn't touch the
    # DOM while loading), but jQuery doesn't: it calls
    # document.createElement right during its own load, with no
    # protection at all, and fails with "Cannot read properties of
    # undefined (reading 'createElement')" (verified on a real site: g_
    # would load successfully every so often while g$ failed in the same
    # attempt — that's what pointed to the real cause). DocumentReady
    # removes the actual source of the race instead of just guarding
    # against its symptoms. g$/g_ aren't needed before DOMContentLoaded —
    # a scenario always reaches for them later anyway.
    #
    # setRunsOnSubFrames(False) stays as is — g$/g_ are only meant to be
    # used on the main page.
    library_script = QWebEngineScript()
    library_script.setName("app-jquery-lodash-inject")
    library_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
    library_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
    library_script.setRunsOnSubFrames(False)
    library_script.setSourceCode(build_library_inject_script())
    scripts.insert(library_script)


# ---------------------------------------------------------------------------
# A page that intercepts console.log/warn/error from the web page's own JS,
# plus the InsertToDB(data) bridge (QWebChannel — tied to a specific page,
# can't be configured on the profile as a whole, unlike everything else)
# ---------------------------------------------------------------------------
class LoggingWebPage(QWebEnginePage):
    def __init__(self, profile, parent, on_console_message):
        super().__init__(profile, parent)
        self._on_console_message = on_console_message

        # InsertToDB(data) from the JS side — see web/bridge.py.
        # self.bridge is accessible from outside (scenario_mixin.py
        # subscribes to bridge.dataInserted to write to the DB with the
        # current scenario_id).
        self.bridge = PyBridge(self)
        self._web_channel = QWebChannel(self)
        self._web_channel.registerObject("qttBridge", self.bridge)
        self.setWebChannel(self._web_channel)

        bridge_script = QWebEngineScript()
        bridge_script.setName("app-insert-to-db-bridge")
        bridge_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        bridge_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        bridge_script.setRunsOnSubFrames(True)
        bridge_script.setSourceCode(build_bridge_setup_script())
        self.scripts().insert(bridge_script)

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        self._on_console_message(level, message, line_number, source_id)


# ---------------------------------------------------------------------------
# Request interceptor — custom HTTP headers get plugged in here
# ---------------------------------------------------------------------------
class HeaderInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self):
        super().__init__()
        self.headers = {}  # name -> value

    def interceptRequest(self, info):
        for name, value in self.headers.items():
            if name:
                info.setHttpHeader(name.encode("utf-8"), value.encode("utf-8"))
