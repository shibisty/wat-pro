# Web Automation Tools

![Screenshot](_example/logo.png)

## Launch

```bash
pip install PyQt6 PyQt6-WebEngine keyring
python run.py
```

## Five Latest Fixes (Before Testing)

### 1 & 2. Live Theme/Language Injection into an Already Open Page
Previously, switching the theme or language would recreate the bridge script,
causing the website to lose all of its `matchMedia('change', ...)`
subscriptions. The state is now persistent (`window.__qttThemeState`), and
switching calls `window.__qttSetTheme()` / `window.__qttSetLanguage()`,
which triggers the site's existing callbacks without reloading the page.

Verified: the JavaScript `change` event handler is triggered when switching
the theme from the application, and `navigator.language` updates in the
same way.

### 3. Zoom Fixed Properly, Not Just Visually
Confirmed through testing that `QWebEngineView.setZoomFactor()` changes
`window.innerWidth/innerHeight`, meaning it actually zooms the page content
inside the viewport (at 50% zoom the page sees twice as much space) rather
than emulating a smaller device.

The mechanism has been replaced with `QGraphicsView` +
`QGraphicsProxyWidget` (`web/zoomable_canvas.py`), so only the visual
representation is scaled while the `web_view` always remains at its
configured pixel size. `innerWidth/innerHeight` stay unchanged regardless
of the zoom level, verified by tests (900×700 remains 900×700 even at 40%
zoom).

### 4. Panels No Longer Disappear Permanently
The three panels (Tools + Scenario, HTML, Console) have been migrated from
`QSplitter` to `QDockWidget` inside an embedded `QMainWindow`, providing:

- proper minimum size while resizing (panels no longer collapse to 0);
- a close button on every panel;
- a **🗔** button next to the scenario address bar that opens the native
  `QMainWindow.createPopupMenu()` (the standard Windows dropdown menu)
  listing all panels with show/hide checkboxes.

Verified: after closing and restoring a panel through the menu, its width is
**non-zero** (actual test result: 533px, not 0).

### 5. HTML Source and DOM Tree Update on Demand
The automatic refresh timer (once per second) has been removed since it made
the content difficult to inspect.

Now the HTML view refreshes automatically only once when navigating to a new
page. After that, refreshing is done manually using the **🔄 Refresh**
button in the HTML panel header.

## Package Structure (Current)

```
run.py
qt_test_tool/
├── main.py                    # GUI; --run-scenario <id> → headless execution
├── core/                      # theme, i18n, system detection, ScenarioRunner
├── web/
│   ├── page.py                # LoggingWebPage, HeaderInterceptor,
│   │                           # build_page_init_script + build_live_update_script
│   ├── zoomable_canvas.py      # QGraphicsView canvas: visual zoom without viewport distortion
│   ├── randomizer_js.py
│   ├── dom_tree_js.py
│   └── recorder_js.py
├── widgets/
│   ├── html_viewer.py          # source viewer + syntax highlighting + hover spans
│   ├── dom_tree_view.py
│   ├── history_line_edit.py
│   ├── dialogs.py
│   └── cards.py
├── data/                       # SQLite: collected_data, cron_jobs, notification_settings
├── scheduler/task_scheduler_bridge.py
├── notifications/
└── ui/
    ├── shell.py                 # AppBar (screen switching, theme/language, window geometry)
    ├── mixins/
    └── pages/
        ├── scenario_editor_page.py   # now uses QDockWidget instead of QSplitter
        ├── scheduler_page.py
        ├── notifications_page.py
        └── database_page.py
```

## What Was Tested During This Session

A single automated run (Qt offscreen) verified:

- live theme switching (`change` event triggered correctly);
- live language switching;
- zoom preserving `innerWidth/innerHeight`;
- closing and restoring dock widgets with a non-zero width;
- manual HTML refresh button working correctly;
- automatic refresh timer is confirmed to be removed.

## Known Limitations

- `QGraphicsProxyWidget` + `QWebEngineView` is a well-known Qt combination
  that had compositing issues (blank widgets) in some Qt5 versions. Under
  PyQt6/Qt6-WebEngine (tested with Chromium 140), everything works
  correctly (JavaScript executes, zoom behaves properly). However,
  **visual rendering on a real Windows display should be the first thing to
  verify**, since the sandbox's offscreen mode cannot validate actual
  on-screen rendering.
- Cron scheduling is still Windows-only (`schtasks.exe`).
