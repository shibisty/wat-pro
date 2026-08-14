"""
Console test for a manually built PyQt6-WebEngine.

Run:
python check_webengine.py

Checks:
0. Module import and basic User-Agent

1. H.264/AAC — via JS canPlayType() on an empty page (no network)
2. Spellchecker — enabling it + list of supported languages
3. Printing/PDF — actual printToPdf() to the current directory
4. WebRTC — presence of navigator.mediaDevices.getUserMedia in the JS environment

The script runs without a GUI (offscreen platform), so it is safe
to run from the console/CI without a display.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QUrl, QTimer
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
except ImportError as e:
    print(f"[FAIL] Failed to import PyQt6/PyQt6-WebEngine: {e}")
    print("       Make sure you are using the correct venv "
          "(for example: C:\\envs\\wat_pro_custom_qt\\Scripts\\activate)")
    sys.exit(1)

RESULTS = {}


def mark(name: str, ok: bool, detail: str = ""):
    RESULTS[name] = ok
    status = "OK  " if ok else "FAIL"
    line = f"[{status}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)


def main():
    app = QApplication(sys.argv)

    profile = QWebEngineProfile.defaultProfile()
    ua = profile.httpUserAgent()
    mark("Module import / profile created", bool(ua), ua)

    # --- Spellchecker ---------------------------------------------------
    try:
        profile.setSpellCheckEnabled(True)
        profile.setSpellCheckLanguages(["en-US"])
        enabled = profile.isSpellCheckEnabled()
        langs = profile.spellCheckLanguages()
        mark(
            "Spellchecker can be enabled",
            enabled and "en-US" in langs,
            f"enabled={enabled}, languages={langs}",
        )
    except Exception as e:
        mark("Spellchecker can be enabled", False, str(e))

    page = QWebEnginePage(profile)

    pending = {"codec": False, "webrtc": False, "pdf": False}
    exit_timer = QTimer()
    exit_timer.setSingleShot(True)
    exit_timer.timeout.connect(app.quit)

    def maybe_quit():
        if all(pending.values()):
            QTimer.singleShot(200, app.quit)

    # --- H.264/AAC via canPlayType ---------------------------------
    def check_codecs():
        js = """
        (function() {
            var v = document.createElement('video');
            return JSON.stringify({
                h264: v.canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"'),
                vp9:  v.canPlayType('video/webm; codecs="vp9"')
            });
        })();
        """
        page.runJavaScript(js, on_codec_result)

    def on_codec_result(result):
        import json
        try:
            data = json.loads(result)
            h264 = data.get("h264", "")
            ok = h264 in ("probably", "maybe")
            mark(
                "H.264/AAC (proprietary codecs)",
                ok,
                f"canPlayType H.264 = '{h264}' (empty/'' means NOT enabled at build time)",
            )
        except Exception as e:
            mark(
                "H.264/AAC (proprietary codecs)",
                False,
                f"JS returned: {result!r} ({e})",
            )
        pending["codec"] = True
        maybe_quit()

    # --- WebRTC: API availability -----------------------------------------
    def check_webrtc():
        js = """
        (function() {
            return JSON.stringify({
                hasGetUserMedia: !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
                hasRTCPeerConnection: typeof RTCPeerConnection !== 'undefined'
            });
        })();
        """
        page.runJavaScript(js, on_webrtc_result)

    def on_webrtc_result(result):
        import json
        try:
            data = json.loads(result)
            ok = data.get("hasGetUserMedia") and data.get("hasRTCPeerConnection")
            mark("WebRTC API available in page", bool(ok), str(data))
        except Exception as e:
            mark(
                "WebRTC API available in page",
                False,
                f"JS returned: {result!r} ({e})",
            )
        pending["webrtc"] = True
        maybe_quit()

    # --- Printing/PDF ----------------------------------------------------
    pdf_path = os.path.abspath("webengine_test_print.pdf")

    def check_pdf():
        page.printToPdf(pdf_path)

    def on_pdf_finished(path, ok):
        exists = os.path.exists(path) and os.path.getsize(path) > 0
        mark(
            "Printing/PDF (printToPdf)",
            ok and exists,
            f"file: {path} (exists={exists})",
        )
        pending["pdf"] = True
        maybe_quit()

    page.pdfPrintingFinished.connect(on_pdf_finished)

    def on_load_finished(ok):
        if not ok:
            mark("Test page loading", False)
            app.quit()
            return
        check_codecs()
        check_webrtc()
        check_pdf()

    page.loadFinished.connect(on_load_finished)
    page.setHtml(
        "<html><body><h1>WebEngine self-test</h1></body></html>",
        QUrl("about:blank"),
    )

    # Safety timeout in case of a hang
    exit_timer.start(15000)

    app.exec()

    print("\n--- Summary ---")
    total = len(RESULTS)
    passed = sum(1 for v in RESULTS.values() if v)
    print(f"Passed: {passed}/{total}")

    if passed < total:
        print("\nTips:")
        if not RESULTS.get("H.264/AAC (proprietary codecs)", True):
            print(" - H.264: make sure configure.bat included "
                  "-webengine-proprietary-codecs, and that you are using "
                  "your manually built Qt (where qmake), not PyQt6-Qt6 from pip.")
        if not RESULTS.get("Spellchecker can be enabled", True):
            print(" - Spellchecker: make sure -webengine-spellchecker was explicitly specified.")
        if not RESULTS.get("WebRTC API available in page", True):
            print(" - WebRTC: check the -webengine-webrtc flag in configure.bat.")
        if not RESULTS.get("Printing/PDF (printToPdf)", True):
            print(" - PDF: check the -webengine-printing-and-pdf flag.")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
