"""
JS for randomly filling forms on the page, taking type/min/max/
minlength/maxlength into account, plus heuristics based on name/id/
placeholder (email, phone, name, city, zip, url, date) — so the values
look plausible.
"""

RANDOMIZE_FORM_JS = r"""
(function () {
    function randomInt(min, max) { return Math.floor(Math.random() * (max - min + 1)) + min; }
    function pick(arr) { return arr[randomInt(0, arr.length - 1)]; }

    var firstNames = ["Олена", "Іван", "Марія", "Петро", "Наталія", "Андрій", "Софія", "Максим", "Катерина", "Дмитро"];
    var lastNames = ["Коваленко", "Шевченко", "Бондаренко", "Ткаченко", "Кравченко", "Олійник", "Іщенко", "Мельник"];
    var words = ["тест", "приклад", "дані", "перевірка", "значення", "інформація", "опис", "коментар", "система", "проєкт"];
    var domains = ["example.com", "test.org", "mail.com", "demo.net"];
    var cities = ["Київ", "Одеса", "Львів", "Харків", "Дніпро", "Полтава"];

    function randomWord() { return pick(words); }
    function randomSentence(n) {
        n = n || randomInt(4, 10);
        var parts = [];
        for (var i = 0; i < n; i++) parts.push(randomWord());
        var s = parts.join(" ");
        return s.charAt(0).toUpperCase() + s.slice(1) + ".";
    }
    function randomName() { return pick(firstNames) + " " + pick(lastNames); }
    function randomEmail() {
        var local = (pick(firstNames) + pick(lastNames)).toLowerCase().replace(/[^a-z]/g, "") + randomInt(1, 999);
        return local + "@" + pick(domains);
    }
    function randomPhone() { return "+380" + randomInt(50, 99) + randomInt(1000000, 9999999); }
    function randomUrl() { return "https://" + pick(domains) + "/" + randomWord(); }
    function randomDateISO(minStr, maxStr) {
        var min = minStr ? new Date(minStr).getTime() : new Date(1990, 0, 1).getTime();
        var max = maxStr ? new Date(maxStr).getTime() : Date.now();
        if (isNaN(min) || isNaN(max) || min >= max) { min = new Date(1990, 0, 1).getTime(); max = Date.now(); }
        var d = new Date(min + Math.random() * (max - min));
        return d.toISOString().slice(0, 10);
    }
    function randomColor() { return "#" + Math.floor(Math.random() * 16777215).toString(16).padStart(6, "0"); }

    function fireEvents(el) {
        ["input", "change", "blur"].forEach(function (type) {
            el.dispatchEvent(new Event(type, { bubbles: true }));
        });
    }

    function guessKind(el) {
        var hay = ((el.name || "") + " " + (el.id || "") + " " + (el.placeholder || "") + " " +
            (el.getAttribute("autocomplete") || "")).toLowerCase();
        if (/e-?mail/.test(hay)) return "email";
        if (/phone|tel|телефон|моб/.test(hay)) return "tel";
        if (/name|ім'я|имя|fio|фио|піб/.test(hay)) return "name";
        if (/city|місто|город/.test(hay)) return "city";
        if (/zip|postal|індекс|индекс/.test(hay)) return "zip";
        if (/url|сайт|website/.test(hay)) return "url";
        if (/date|дата/.test(hay)) return "date";
        return null;
    }

    var filled = 0, skipped = 0;
    var fields = document.querySelectorAll("input, textarea, select");
    var handledRadioGroups = {};

    fields.forEach(function (el) {
        if (el.disabled || el.readOnly) { skipped++; return; }
        var tag = el.tagName.toLowerCase();
        var type = (el.getAttribute("type") || "text").toLowerCase();

        try {
            if (tag === "select") {
                var options = Array.prototype.filter.call(el.options, function (o) { return !o.disabled && o.value !== ""; });
                if (options.length) { el.value = pick(options).value; fireEvents(el); filled++; }
                else skipped++;
                return;
            }

            if (tag === "textarea") {
                el.value = randomSentence();
                fireEvents(el);
                filled++;
                return;
            }

            switch (type) {
                case "checkbox":
                    el.checked = Math.random() > 0.5;
                    fireEvents(el); filled++;
                    break;
                case "radio": {
                    var group = el.name || el.id;
                    if (!group) { el.checked = true; fireEvents(el); filled++; break; }
                    if (handledRadioGroups[group]) { skipped++; break; }
                    var groupEls = document.querySelectorAll('input[type="radio"][name="' + el.name + '"]');
                    var chosen = pick(Array.prototype.slice.call(groupEls));
                    chosen.checked = true;
                    fireEvents(chosen);
                    handledRadioGroups[group] = true;
                    filled++;
                    break;
                }
                case "email":
                    el.value = randomEmail(); fireEvents(el); filled++;
                    break;
                case "tel":
                    el.value = randomPhone(); fireEvents(el); filled++;
                    break;
                case "number":
                case "range": {
                    var min = el.min !== "" ? parseFloat(el.min) : 1;
                    var max = el.max !== "" ? parseFloat(el.max) : 100;
                    var step = el.step && el.step !== "any" ? parseFloat(el.step) : 1;
                    var val = min + Math.round(Math.random() * (max - min) / step) * step;
                    el.value = val; fireEvents(el); filled++;
                    break;
                }
                case "date":
                    el.value = randomDateISO(el.min, el.max); fireEvents(el); filled++;
                    break;
                case "month":
                    el.value = randomDateISO(el.min, el.max).slice(0, 7); fireEvents(el); filled++;
                    break;
                case "url":
                    el.value = randomUrl(); fireEvents(el); filled++;
                    break;
                case "color":
                    el.value = randomColor(); fireEvents(el); filled++;
                    break;
                case "password": {
                    var minLen = el.minLength && el.minLength > 0 ? el.minLength : 8;
                    el.value = "Aa1!" + Math.random().toString(36).slice(2, 2 + Math.max(4, minLen - 4));
                    fireEvents(el); filled++;
                    break;
                }
                case "search":
                case "text":
                default: {
                    var kind = guessKind(el);
                    var value;
                    if (kind === "email") value = randomEmail();
                    else if (kind === "tel") value = randomPhone();
                    else if (kind === "name") value = randomName();
                    else if (kind === "city") value = pick(cities);
                    else if (kind === "zip") value = String(randomInt(10000, 99999));
                    else if (kind === "url") value = randomUrl();
                    else if (kind === "date") value = randomDateISO();
                    else value = randomSentence(randomInt(2, 5));

                    var maxLength = el.maxLength && el.maxLength > 0 ? el.maxLength : null;
                    if (maxLength && value.length > maxLength) value = value.slice(0, maxLength);
                    var minLength = el.minLength && el.minLength > 0 ? el.minLength : null;
                    if (minLength && value.length < minLength) {
                        value = (value + " " + randomSentence()).slice(0, Math.max(minLength, value.length));
                    }

                    el.value = value;
                    fireEvents(el);
                    filled++;
                }
            }
        } catch (e) {
            skipped++;
        }
    });

    return JSON.stringify({ filled: filled, skipped: skipped, total: fields.length });
})();
"""
