"""
Replays Chrome DevTools Recorder recordings (Puppeteer Replay schema)
directly on the page, as one opaque scenario step (see
ui/mixins/scenario_mixin.py: import_recorder_file / kind == "recorder"
steps). We deliberately do NOT decompose a recording into several of our
own steps — see the conversation this was designed in for the tradeoffs;
the short version is: a recording stays a single, re-importable/
re-exportable unit instead of N separately-editable steps.

Coverage: navigate, click, doubleClick, hover, change, keyDown, keyUp,
scroll. setViewport is intentionally NOT handled here — page JS can't
resize the actual browser window; see ScenarioRunner, which pulls
setViewport out and applies it on the Python side (width_spin/height_spin)
before this script ever runs. Unsupported step types (waitForElement,
waitForExpression, emulateNetworkConditions, close, customStep, and any
future ones) are skipped with a console.warn rather than aborting the
whole recording — most recordings still work fine minus that one action.

Selector resolution: a Recorder step's "selectors" field is a list of
alternative ways to find the SAME element (Chrome itself records several
in case one breaks later) — we try each in order, first match wins:
- plain CSS
- "xpath/..." — document.evaluate
- "text/..." — element whose own text content matches
- "aria/..." — approximated via aria-label/alt/textContent (Puppeteer
  itself uses the real Accessibility Tree via CDP for this, which we
  don't have direct access to from page JS — this is a best-effort
  substitute, not full parity)
- "pierce/..." — CSS that also searches inside shadow roots
"""

import json

RECORDER_REPLAY_INSTALL_JS = r"""
(function() {
    if (window.__qttRunRecorderSteps) return;  // already installed for this document

    function pierceQuerySelector(root, css) {
        var found = root.querySelector(css);
        if (found) return found;
        var all = root.querySelectorAll('*');
        for (var i = 0; i < all.length; i++) {
            if (all[i].shadowRoot) {
                var inner = pierceQuerySelector(all[i].shadowRoot, css);
                if (inner) return inner;
            }
        }
        return null;
    }

    function resolveOneSelector(sel) {
        if (sel.indexOf('xpath/') === 0) {
            var xp = sel.slice(6);
            var r = document.evaluate(xp, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
            return r.singleNodeValue;
        }
        if (sel.indexOf('text/') === 0) {
            var text = decodeURIComponent(sel.slice(5)).trim();
            var candidates = document.querySelectorAll('*');
            for (var i = 0; i < candidates.length; i++) {
                var el = candidates[i];
                if (el.children.length === 0 && el.textContent && el.textContent.trim() === text) return el;
            }
            return null;
        }
        if (sel.indexOf('aria/') === 0) {
            var name = sel.slice(5).trim();
            var ariaCandidates = document.querySelectorAll('[aria-label], [role], a, button, input, [alt]');
            for (var j = 0; j < ariaCandidates.length; j++) {
                var c = ariaCandidates[j];
                var label = c.getAttribute('aria-label') || c.getAttribute('alt') || (c.textContent || '').trim();
                if (label && label.trim() === name) return c;
            }
            return null;
        }
        if (sel.indexOf('pierce/') === 0) {
            return pierceQuerySelector(document, sel.slice(7));
        }
        return document.querySelector(sel);
    }

    function findElement(selectorGroups) {
        for (var g = 0; g < selectorGroups.length; g++) {
            var group = selectorGroups[g];
            for (var s = 0; s < group.length; s++) {
                try {
                    var el = resolveOneSelector(group[s]);
                    if (el) return el;
                } catch (e) {}
            }
        }
        return null;
    }

    function dispatchClick(el, offsetX, offsetY) {
        var rect = el.getBoundingClientRect();
        var x = rect.left + (offsetX !== undefined ? offsetX : rect.width / 2);
        var y = rect.top + (offsetY !== undefined ? offsetY : rect.height / 2);
        var opts = { bubbles: true, cancelable: true, clientX: x, clientY: y, view: window };
        el.dispatchEvent(new MouseEvent('mousedown', opts));
        el.dispatchEvent(new MouseEvent('mouseup', opts));
        el.dispatchEvent(new MouseEvent('click', opts));
    }

    function wait(ms) {
        return new Promise(function (resolve) { setTimeout(resolve, ms); });
    }

    async function runOne(step) {
        switch (step.type) {
            case 'navigate':
                window.location.href = step.url;
                return;
            case 'click':
            case 'doubleClick': {
                var el = findElement(step.selectors);
                if (!el) throw new Error('Element not found for ' + step.type + ': ' + JSON.stringify(step.selectors));
                dispatchClick(el, step.offsetX, step.offsetY);
                if (step.type === 'doubleClick') {
                    await wait(30);
                    dispatchClick(el, step.offsetX, step.offsetY);
                }
                return;
            }
            case 'hover': {
                var elH = findElement(step.selectors);
                if (!elH) throw new Error('Element not found for hover: ' + JSON.stringify(step.selectors));
                elH.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                elH.dispatchEvent(new MouseEvent('mousemove', { bubbles: true }));
                return;
            }
            case 'change': {
                var elC = findElement(step.selectors);
                if (!elC) throw new Error('Element not found for change: ' + JSON.stringify(step.selectors));
                elC.focus();
                elC.value = step.value;
                elC.dispatchEvent(new Event('input', { bubbles: true }));
                elC.dispatchEvent(new Event('change', { bubbles: true }));
                return;
            }
            case 'keyDown':
                if (document.activeElement) {
                    document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key: step.key, bubbles: true }));
                }
                return;
            case 'keyUp':
                if (document.activeElement) {
                    document.activeElement.dispatchEvent(new KeyboardEvent('keyup', { key: step.key, bubbles: true }));
                }
                return;
            case 'scroll': {
                if (step.selectors) {
                    var elS = findElement(step.selectors);
                    if (elS) {
                        elS.scrollTop = step.y || 0;
                        elS.scrollLeft = step.x || 0;
                        return;
                    }
                }
                window.scrollTo(step.x || 0, step.y || 0);
                return;
            }
            case 'setViewport':
                // handled on the Python side before this script runs — see
                // ScenarioRunner / core/scenario_runner.py
                return;
            default:
                console.warn('[WAT Pro] Recorder step type not supported yet, skipped: ' + step.type);
                return;
        }
    }

    window.__qttRunRecorderSteps = async function (steps) {
        for (var i = 0; i < steps.length; i++) {
            try {
                await runOne(steps[i]);
                // a short pause between actions — mirrors how the
                // recording actually happened and gives the page time to
                // react (e.g. a click-triggered animation/render) before
                // the next selector lookup runs
                await wait(80);
            } catch (e) {
                window.__qttRecorderResult = {
                    success: false,
                    error: String(e && e.message ? e.message : e),
                    atStep: i,
                };
                return;
            }
        }
        window.__qttRecorderResult = { success: true };
    };
})();
"""

RECORDER_RESULT_CHECK_JS = r"""
(function() {
    if (window.__qttRecorderResult === undefined) return null;
    var result = window.__qttRecorderResult;
    window.__qttRecorderResult = undefined;
    return JSON.stringify(result);
})();
"""


def build_recorder_run_script(recorder_steps: list) -> str:
    """
    Kicks off replay of the given (non-setViewport) Recorder steps.
    Doesn't wait for a Promise (runJavaScript never does — see
    core/scenario_runner.py) — the caller polls RECORDER_RESULT_CHECK_JS
    for the outcome instead.
    """
    steps_json = json.dumps(recorder_steps)
    return f"""
    window.__qttRecorderResult = undefined;
    window.__qttRunRecorderSteps({steps_json});
    """
    