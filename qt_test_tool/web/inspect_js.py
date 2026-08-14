"""
JS для вкладок "localStorage" и "Кэш" в HTML-панели.

LOCAL_STORAGE_JS — простое перечисление localStorage.

RESOURCE_OBSERVER_INSTALL_JS — устанавливается РАНО (DocumentCreation,
до скриптов самой страницы, см. configure_profile() в web/page.py) и
копит список загруженных ресурсов в собственный, независимый от
браузера массив window.__qttResourceLog через PerformanceObserver.

Это важно: многие сайты (в том числе YouTube) сами вызывают
performance.clearResourceTimings() как часть своей телеметрии — если
просто читать "живой" performance.getEntriesByType('resource') в
произвольный момент, список может внезапно оказаться пустым, хотя
ресурсы реально грузились (это и увидел пользователь). Наш собственный
лог такому стороннему clearResourceTimings() не подчиняется — только
самой странице, если она полностью перезагрузится (новый window).

RESOURCE_ENTRIES_JS — читает из __qttResourceLog (с фолбэком на живой
performance.getEntriesByType, если по какой-то причине обсёрвер не
успел установиться раньше самой первой проверки).
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
    if (window.__qttResourceLog) return;  // уже установлен для этого документа
    window.__qttResourceLog = [];
    try {
        var seen = {};
        function addEntries(list) {
            list.getEntries().forEach(function (e) {
                // грубая дедупликация — на случай повторной доставки одной
                // и той же записи через buffered:true + последующий callback
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
    Запускает скачивание содержимого ресурса заново (по его URL) и
    складывает результат (base64) в window.__qttFetchResult — само
    runJavaScript() Promise не дожидается (проверено эмпирически, см.
    core/scenario_runner.py), поэтому забирать результат нужно отдельным
    поллингом через FETCH_RESOURCE_CHECK_JS.

    Для чужих доменов без CORS-заголовков fetch() тела не даст — тогда
    придёт {success: false, error: ...}, а не крэш.
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
