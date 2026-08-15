"""
Injects jQuery and lodash into every page under NON-STANDARD names
(window.g$ and window.g_) — so as not to clash with the page's own $/_
if it already uses them (a common case — most sites already pull in jQuery).

Libraries live locally in web/vendor/ (not via CDN):
- works even when testing sites with no internet access
- doesn't break against a restrictive page CSP (script-src with no third-party domain)
- version is deterministic, not "whatever is on the CDN right now"

Isolation mechanism from the page's own $/_/jQuery: before running the
library we remember what was in window.$/window.jQuery/window._
(undefined if there was nothing), run the library (it defines itself
under these standard names as usual), grab the result under g$/g_, and
RESTORE the original values. If the page had its own jQuery/lodash — it
keeps working as if nothing happened; if it didn't — the corresponding
window.$/window._ simply won't appear from our injection (so it doesn't
give the false impression that they're "native" to the site).

IMPORTANT: the minified library contents are NOT substituted via
f-string/.format() — they contain hundreds of curly braces that would
conflict with the formatting syntax. Plain string concatenation only.
"""

import os

_VENDOR_DIR = os.path.join(os.path.dirname(__file__), "vendor")


def _read_vendor_file(name: str) -> str:
    path = os.path.join(_VENDOR_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def build_library_inject_script() -> str:
    jquery_src = _read_vendor_file("jquery.min.js")
    lodash_src = _read_vendor_file("lodash.min.js")

    return (
        "(function() {\n"
        "    if (window.g$ && window.g_) return;  // already injected for this document\n"
        "    // Check independent of the Qt setting (setRunsOnSubFrames) —\n"
        "    // if for any reason the script still runs outside the main\n"
        "    // frame (an ad/tracking iframe etc.), bail out immediately.\n"
        "    // window.top is accessible without throwing even from a\n"
        "    // cross-origin subframe (unlike reading its properties) —\n"
        "    // comparing references is safe in any case.\n"
        "    try {\n"
        "        if (window.top !== window) return;\n"
        "    } catch (e) { return; }\n"
        "    if (typeof document === 'undefined') return;  // just in case, a second barrier\n"
        "\n"
        "    // ---- jQuery under g$ ----\n"
        "    // try/catch per library SEPARATELY, with an explicit console.error:\n"
        "    // without this, one uncaught exception inside jQuery on a\n"
        "    // particular site would abort the whole script (including\n"
        "    // lodash after it) COMPLETELY SILENTLY — neither g$ nor g_\n"
        "    // would show up, with no way to see why anywhere.\n"
        "    try {\n"
        "        var prevDollar = window.$;\n"
        "        var prevJQuery = window.jQuery;\n"
        + jquery_src + "\n"
        "        window.g$ = window.jQuery;\n"
        "        if (prevJQuery === undefined) { delete window.jQuery; } else { window.jQuery = prevJQuery; }\n"
        "        if (prevDollar === undefined) { delete window.$; } else { window.$ = prevDollar; }\n"
        "    } catch (e) {\n"
        "        console.error('[WAT Pro] g$ (jQuery) injection failed: ' + (e && e.message ? e.message : e));\n"
        "    }\n"
        "\n"
        "    // ---- lodash under g_ (independent of the block above) ----\n"
        "    try {\n"
        "        var prevUnderscore = window._;\n"
        + lodash_src + "\n"
        "        window.g_ = window._;\n"
        "        if (prevUnderscore === undefined) { delete window._; } else { window._ = prevUnderscore; }\n"
        "    } catch (e) {\n"
        "        console.error('[WAT Pro] g_ (lodash) injection failed: ' + (e && e.message ? e.message : e));\n"
        "    }\n"
        "})();\n"
    )
