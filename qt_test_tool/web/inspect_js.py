"""
JS for the "localStorage" and "Cache" tabs in the HTML panel.

LOCAL_STORAGE_JS — a simple enumeration of localStorage.

RESOURCE_OBSERVER_INSTALL_JS — installed EARLY (DocumentCreation, before
the page's own scripts, see configure_profile() in web/page.py) and
collects the list of loaded resources into our own array,
window.__qttResourceLog, independent of the browser, via a
PerformanceObserver.

This matters: many sites (YouTube included) call
performance.clearResourceTimings() themselves as part of their own
telemetry — if you just read the "live"
performance.getEntriesByType('resource') at an arbitrary moment, the
list can suddenly turn out empty even though resources really did load
(this is exactly what the user saw). Our own log isn't subject to a
third party's clearResourceTimings() — only to the page itself if it
fully reloads (a new window).

RESOURCE_ENTRIES_JS — reads from __qttResourceLog (with a fallback to
the live performance.getEntriesByType, in case for some reason the
observer didn't manage to install before the very first check).
"""

import json

LOCAL_STORAGE_JS = r"""
(function() {
    try {
        var items = [];
        for (var i = 0; i < localStorage.length; i++) {
            var key = localStorage.key(i);
            var value = localStorage.getItem(key);
            items.push({
                key: key,
                value: value,
                size: new Blob([key + value]).size,
            });
        }
        return JSON.stringify(items);
    } catch (e) {
        return JSON.stringify({ error: String(e && e.message ? e.message : e) });
    }
})();
"""

RESOURCE_OBSERVER_INSTALL_JS = r"""
(function() {
    if (window.__qttResourceLog) return;  // already installed for this document
    window.__qttResourceLog = [];
    try {
        var seen = {};
        function addEntries(list) {
            list.getEntries().forEach(function (e) {
                // rough deduplication — in case the same entry is
                // delivered twice via buffered:true + a later callback
                var key = e.name + '|' + e.startTime;
                if (seen[key]) return;
                seen[key] = true;
                window.__qttResourceLog.push({
                    name: e.name,
                    initiatorType: e.initiatorType,
                    encodedBodySize: e.encodedBodySize,
                    transferSize: e.transferSize,
                    decodedBodySize: e.decodedBodySize,
                });
            });
        }
        var observer = new PerformanceObserver(addEntries);
        observer.observe({ type: 'resource', buffered: true });
    } catch (e) {}
})();
"""

RESOURCE_ENTRIES_JS = r"""
(function() {
    try {
        var raw = (window.__qttResourceLog && window.__qttResourceLog.length)
            ? window.__qttResourceLog
            : performance.getEntriesByType('resource');
        var items = raw.map(function (e) {
            var name = e.name;
            try {
                var url = new URL(e.name);
                name = url.pathname.split('/').pop() || e.name;
            } catch (err) {}
            var size = e.encodedBodySize || e.transferSize || 0;
            var cached = (e.transferSize === 0 && (e.encodedBodySize > 0 || e.decodedBodySize > 0));
            return {
                name: name,
                fullUrl: e.name,
                type: e.initiatorType || 'other',
                size: size,
                cached: cached,
            };
        });
        return JSON.stringify(items);
    } catch (e) {
        return JSON.stringify({ error: String(e && e.message ? e.message : e) });
    }
})();
"""


def build_fetch_resource_start_script(url: str) -> str:
    """
    Starts re-downloading the resource's content (by its URL) and stores
    the result (base64) in window.__qttFetchResult — runJavaScript()
    itself doesn't wait for a Promise (verified empirically, see
    core/scenario_runner.py), so the result needs to be fetched
    separately by polling via FETCH_RESOURCE_CHECK_JS.

    For third-party domains without CORS headers, fetch() won't give us
    the body — in that case you'll get {success: false, error: ...},
    not a crash.
    """
    safe_url = json.dumps(url)
    return f"""
    (function(url) {{
        window.__qttFetchResult = undefined;
        fetch(url)
            .then(function(resp) {{
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                return resp.arrayBuffer();
            }})
            .then(function(buf) {{
                var bytes = new Uint8Array(buf);
                var binary = '';
                var chunkSize = 0x8000;
                for (var i = 0; i < bytes.length; i += chunkSize) {{
                    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize));
                }}
                window.__qttFetchResult = {{ success: true, base64: btoa(binary) }};
            }})
            .catch(function(err) {{
                window.__qttFetchResult = {{ success: false, error: String(err && err.message ? err.message : err) }};
            }});
    }})({safe_url});
    """


FETCH_RESOURCE_CHECK_JS = r"""
(function() {
    if (window.__qttFetchResult === undefined) return null;
    var result = window.__qttFetchResult;
    window.__qttFetchResult = undefined;
    return JSON.stringify(result);
})();
"""
