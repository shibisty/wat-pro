"""
JS for building the page content tree (for the "Tree" tab in the HTML
panel) and highlighting an element in the browser on hover.

DOM_TREE_JS is based on a supplied HTMLToTree, with a few bugs from the
original fixed:
- `node.parentNode.tagName  null` -> `node.parentNode.tagName || null`
  (the || operator was missing)
- `element.innerText  ''` -> `element.innerText || ''` (same mistake)
- `const upeClass = upe-node- + makeid(7)` -> the string wasn't actually
  a string literal (no quotes) and there was no concatenation operator
- `makeid` wasn't defined anywhere — an implementation was added

On top of that: every classified node gets assigned a unique CSS class
upe-node-XXXXXXX right in the live DOM — this gives a stable selector
that lets us precisely highlight the element in the browser, and which
also stays in the HTML on a subsequent page.toHtml() (i.e. it's visible
in the "Code" tab too).
"""

DOM_TREE_JS = r"""
(function() {
    try {
        function makeid(length) {
            var result = '';
            var chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
            for (var i = 0; i < length; i++) {
                result += chars.charAt(Math.floor(Math.random() * chars.length));
            }
            return result;
        }

        var HTMLToTree = function () {
            this.getNodeTree = function (node) {
                if (node.hasChildNodes()) {
                    var children = [];

                    for (var j = 0; j < node.childNodes.length; j++) {
                        var childNode = this.getNodeTree(node.childNodes[j]);

                        if (typeof childNode !== 'undefined') {
                            children.push(childNode);
                        }
                    }

                    if (typeof node.tagName !== 'undefined') {
                        var upeClass = 'upe-node-' + makeid(7);
                        node.classList.add(upeClass);
                        return {
                            nodeName: node.tagName,
                            parentName: node.parentNode ? (node.parentNode.tagName || null) : null,
                            content: String(this.getTextContent(node)).trim(),
                            attributes: this.getAttributes(node),
                            children: children,
                            upeSelector: '.' + upeClass,
                        };
                    }
                }
            };

            this.getTextContent = function (node) {
                var element = node.cloneNode(true);
                var length = element.childNodes.length;

                if (length) {
                    for (var i = length - 1; i >= 0; i--) {
                        if (element.childNodes[i].tagName) {
                            element.removeChild(element.childNodes[i]);
                        }
                    }
                }

                return element.innerText || element.textContent || '';
            };

            this.getAttributes = function (node) {
                var length = node.attributes.length;
                var attributes = [];

                if (length) {
                    for (var i = length - 1; i >= 0; i--) {
                        var attribute = node.attributes[i];

                        attributes.push({
                            name: attribute.name,
                            value: attribute.value,
                        });
                    }
                }

                return attributes;
            };
        };

        var builder = new HTMLToTree();
        var tree = builder.getNodeTree(document.documentElement);
        return JSON.stringify(tree);
    } catch (e) {
        return JSON.stringify({ error: String(e && e.message ? e.message : e) });
    }
})();
"""


def build_highlight_script(selector) -> str:
    """
    Highlights the element matching the CSS selector (usually
    .upe-node-XXXXXXX) on the live page with an outline; clears the
    highlight from the previously highlighted element. selector=None/empty
    just clears the highlight.
    """
    selector_js = "null"
    if selector:
        safe = selector.replace("\\", "\\\\").replace("'", "\\'")
        selector_js = f"'{safe}'"

    return f"""
    (function(selector) {{
        var prev = document.querySelectorAll('[data-qtt-hl]');
        prev.forEach(function(el) {{
            el.style.outline = '';
            el.style.outlineOffset = '';
            el.removeAttribute('data-qtt-hl');
        }});
        if (selector) {{
            var el = document.querySelector(selector);
            if (el) {{
                el.style.outline = '2px solid #ff4081';
                el.style.outlineOffset = '-1px';
                el.setAttribute('data-qtt-hl', '1');
            }}
        }}
    }})({selector_js});
    """
