"""
InsertToDB(data) — a JS function available on every page that lets a
scenario step pass data into Python/the DB NOT only through the step's
return value (there it's one value per step, via the 💾 collect flag),
but any number of times from anywhere in the script, at any moment.

Mechanism — QWebChannel (Qt's official two-way bridge between JS and
Python), not a timer-polled queue (like recording actions/wait elsewhere
in the project) — here we specifically need a live, immediate call from
JS into Python at the moment InsertToDB() is actually called, not with a
delay until the next poll.

QWebChannel operates at the PAGE level (QWebEnginePage.setWebChannel),
not the profile as a whole — so the bridge is created in
LoggingWebPage.__init__ (see web/page.py), not in configure_profile()
(everything there is shared across the profile).
"""

from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal, QFile, QIODevice


class PyBridge(QObject):
    # emitted on every InsertToDB(...) call from the page's JS side —
    # whoever cares (scenario_mixin.py, at session start) subscribes and
    # writes to data/collected_data_repo with the scenario_id it already knows
    dataInserted = pyqtSignal(str)

    @pyqtSlot(str)
    def insertToDB(self, data):
        self.dataInserted.emit(data)


def _load_qwebchannel_js() -> str:
    """qwebchannel.js — a built-in Qt resource (registered automatically
    on importing PyQt6.QtWebChannel), not a separate file in the project."""
    f = QFile(":/qtwebchannel/qwebchannel.js")
    if not f.open(QIODevice.OpenModeFlag.ReadOnly):
        return ""
    try:
        return bytes(f.readAll()).decode("utf-8")
    finally:
        f.close()


def build_bridge_setup_script() -> str:
    """
    JS that sets up window.InsertToDB(data) on top of QWebChannel.

    window.InsertToDB is defined RIGHT AWAY (as a buffering stub) — we
    don't wait for the channel to be ready (that's an async handshake that
    takes some time after the page loads). If a scenario calls
    InsertToDB() before the channel actually connects, the call won't be
    lost — it goes into a queue and gets sent once the channel is ready.
    Without this, a scenario's first step (if it calls InsertToDB right
    after navigation) could hit a race and silently write nothing.
    """
    qwebchannel_js = _load_qwebchannel_js()
    return (
        qwebchannel_js + "\n"
        "(function() {\n"
        "    var __qttPendingInserts = [];\n"
        "    window.InsertToDB = function(data) {\n"
        "        __qttPendingInserts.push(String(data));\n"
        "    };\n"
        "\n"
        "    function setup() {\n"
        "        if (typeof qt === 'undefined' || !qt.webChannelTransport) {\n"
        "            setTimeout(setup, 50);\n"
        "            return;\n"
        "        }\n"
        "        new QWebChannel(qt.webChannelTransport, function(channel) {\n"
        "            window.InsertToDB = function(data) {\n"
        "                channel.objects.qttBridge.insertToDB(String(data));\n"
        "            };\n"
        "            // flush whatever accumulated before the channel was ready\n"
        "            __qttPendingInserts.forEach(function(d) { channel.objects.qttBridge.insertToDB(d); });\n"
        "            __qttPendingInserts = [];\n"
        "        });\n"
        "    }\n"
        "    setup();\n"
        "})();\n"
    )
