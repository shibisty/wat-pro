"""
JS для построения дерева контента страницы (для вкладки "Дерево" в
HTML-панели) и подсветки элемента в браузере при наведении.

DOM_TREE_JS основан на присланном HTMLToTree, с исправлением нескольких
багов оригинала:
- `node.parentNode.tagName  null` -> `node.parentNode.tagName || null`
  (пропущен оператор ||)
- `element.innerText  ''` -> `element.innerText || ''` (та же ошибка)
- `const upeClass = upe-node- + makeid(7)` -> строка не была строкой
  (нет кавычек) и не было оператора конкатенации
- `makeid` нигде не была определена — добавлена реализация

Дополнительно: каждому классифицируемому узлу присваивается уникальный
CSS-класс upe-node-XXXXXXX прямо в живом DOM — это даёт stable selector,
по которому можно точно подсветить элемент в браузере, и который также
остаётся в HTML при последующем page.toHtml() (то есть виден и во
вкладке "Код").
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
    Подсвечивает элемент по CSS-селектору (обычно .upe-node-XXXXXXX) на
    живой странице контуром; снимает подсветку с ранее выделенного
    элемента. selector=None/пусто — просто снять подсветку.
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
