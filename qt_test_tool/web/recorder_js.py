"""
JS for recording user actions on the page (clicks, input into
input/textarea/select, scrolling) — used by the "⏺ Record" button in the
scenario editor to auto-generate a scenario draft that can be tweaked by
hand afterward.

Mechanism: click/change/scroll listeners write events into the
window.__qttRecordedActions queue; Python periodically (while recording
is on) calls RECORDER_POLL_JS, which drains and clears the queue.

Scrolling — the event fires very often during the scroll gesture itself
(dozens of times a second), so we don't record every single event, but
debounce it: only the final position after 400ms of silence following
the last scroll event — otherwise a single gesture would produce
hundreds of nearly identical scenario steps.
"""

RECORDER_INSTALL_JS = r"""
(function() {
    if (window.__qttRecorderInstalled) return;
    window.__qttRecorderInstalled = true;
    window.__qttRecordedActions = [];

    function cssPath(el) {
        if (!(el instanceof Element)) return '';
        if (el.id) return '#' + CSS.escape(el.id);
        var path = [];
        var node = el;
        while (node && node.nodeType === Node.ELEMENT_NODE && node.tagName.toLowerCase() !== 'html') {
            var selector = node.tagName.toLowerCase();
            if (node.id) {
                selector = '#' + CSS.escape(node.id);
                path.unshift(selector);
                break;
            } else {
                var sibling = node;
                var nth = 1;
                while ((sibling = sibling.previousElementSibling)) {
                    if (sibling.tagName === node.tagName) nth++;
                }
                selector += ':nth-of-type(' + nth + ')';
            }
            path.unshift(selector);
            node = node.parentElement;
        }
        return path.join(' > ');
    }

    document.addEventListener('click', function (e) {
        var selector = cssPath(e.target);
        if (selector) {
            window.__qttRecordedActions.push({ type: 'click', selector: selector, ts: Date.now() });
        }
    }, true);

    document.addEventListener('change', function (e) {
        var target = e.target;
        if (!target || !target.tagName) return;
        var tag = target.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
            var selector = cssPath(target);
            var isCheckable = target.type === 'checkbox' || target.type === 'radio';
            var value = isCheckable ? target.checked : target.value;
            window.__qttRecordedActions.push({
                type: isCheckable ? 'check' : 'input',
                selector: selector,
                value: value,
                ts: Date.now(),
            });
        }
    }, true);

    var scrollDebounceTimer = null;
    window.addEventListener('scroll', function () {
        if (scrollDebounceTimer) clearTimeout(scrollDebounceTimer);
        scrollDebounceTimer = setTimeout(function () {
            window.__qttRecordedActions.push({
                type: 'scroll',
                x: window.scrollX,
                y: window.scrollY,
                ts: Date.now(),
            });
        }, 400);
    }, true);
})();
"""

RECORDER_POLL_JS = """
(function() {
    var actions = window.__qttRecordedActions || [];
    window.__qttRecordedActions = [];
    return JSON.stringify(actions);
})();
"""


def action_to_step_js(action: dict) -> str:
    """Converts one recorded action into the JS code of a scenario step."""
    selector = action.get("selector", "")
    safe_selector = selector.replace("\\", "\\\\").replace("'", "\\'")
    action_type = action.get("type")

    if action_type == "click":
        return f"document.querySelector('{safe_selector}').click();"

    if action_type == "check":
        checked = "true" if action.get("value") else "false"
        return (
            f"(function(){{ var el = document.querySelector('{safe_selector}'); "
            f"el.checked = {checked}; "
            f"el.dispatchEvent(new Event('change', {{bubbles: true}})); }})();"
        )

    if action_type == "scroll":
        x = int(action.get("x", 0) or 0)
        y = int(action.get("y", 0) or 0)
        return f"window.scrollTo({x}, {y});"

    # input / select
    value = str(action.get("value", "")).replace("\\", "\\\\").replace("'", "\\'")
    return (
        f"(function(){{ var el = document.querySelector('{safe_selector}'); "
        f"el.value = '{value}'; "
        f"el.dispatchEvent(new Event('input', {{bubbles: true}})); "
        f"el.dispatchEvent(new Event('change', {{bubbles: true}})); }})();"
    )
