# -*- mode: python ; coding: utf-8 -*-
"""
Build WAT Pro as an executable.

Run (on Windows, from the folder containing run.py):
    pyinstaller wat_pro.spec

Build mode: --onedir (COLLECT), not --onefile — this is more reliable for
QtWebEngine: --onefile extracts everything to a temporary directory on every
launch (adding extra startup time, and WebEngine resources may occasionally
not be picked up on the first attempt); --onedir simply works.

Result: dist/WAT Pro/WAT Pro.exe — the entire "WAT Pro" folder must be
distributed (it can be zipped), not just the executable.

--- Custom Qt WebEngine build with proprietary codecs (H.264/AAC) ---
Adjust the path below to match your setup (the default is C:\qt6install).
"""

from PyInstaller.utils.hooks import collect_submodules
import glob
import os

block_cipher = None

# Adjust this to the path from the build instructions
# (C:\qt6install by default)
QT6_CUSTOM_BIN = r"C:\qt6install\bin"
QT6_CUSTOM_RESOURCES = r"C:\qt6install\resources"
QT6_CUSTOM_LOCALES = r"C:\qt6install\translations\qtwebengine_locales"
QT6_CUSTOM_PLUGINS = r"C:\qt6install\plugins"

hiddenimports = collect_submodules("qt_test_tool")

# Put translations/ and resources/ DIRECTLY in the bundle root (next to the
# executable in --onedir), rather than under qt_test_tool/... — this is exactly
# where core/config.py looks for them
# (BUNDLE_DIR/translations, BUNDLE_DIR/resources). collect_data_files()
# normally preserves the package structure (qt_test_tool/translations/...),
# which does not match this location, so we handle it explicitly here.
datas = []
for f in glob.glob("qt_test_tool/translations/*.json"):
    datas.append((f, "translations"))
for f in glob.glob("qt_test_tool/resources/*"):
    datas.append((f, "resources"))

# WebEngine resources/locales from the custom build — IMPORTANT: these must
# also be placed under PyQt6/Qt6/..., not in the bundle root. Previously,
# they were placed in the root ("resources"/"translations"), which (a) is not
# where Qt actually looks for them (see the comment about custom_qt_binaries
# below — the same reason: QLibraryInfo resolves paths relative to the
# location of Qt6Core.dll, which is now PyQt6/Qt6/bin), and (b) conflicted
# by name with the application's OWN resources/translations above (UI icons
# and translations) — both were being written to the same "resources" folder
# in the bundle root.
datas.append((QT6_CUSTOM_RESOURCES, os.path.join("PyQt6", "Qt6", "resources")))
datas.append((QT6_CUSTOM_LOCALES, os.path.join("PyQt6", "Qt6", "translations", "qtwebengine_locales")))

# plugins/ (platforms/imageformats/iconengines, etc.) — without them, Qt
# cannot even create a window ("Could not find the Qt platform plugin").
# PyInstaller normally picks these up through its PyQt6 hook, but we have
# already encountered cases where they were missing in a similar setup
# (see chat history), so we explicitly include them instead of relying on
# automatic detection.
if os.path.isdir(QT6_CUSTOM_PLUGINS):
    datas.append((QT6_CUSTOM_PLUGINS, os.path.join("PyQt6", "Qt6", "plugins")))
else:
    print(f"[wat_pro.spec] WARNING: directory {QT6_CUSTOM_PLUGINS} not found — "
          f"Qt platform plugins will be taken from PyInstaller's automatic detection (standard versions)")

# Custom DLLs/executables with proprietary codecs
#
# IMPORTANT: we take the ENTIRE bin\ directory, rather than manually selecting
# individual files. The reason: a full QtWebEngine build pulls in MANY
# dependencies besides Core/Gui/Widgets/WebEngineCore (Qt6Network,
# Qt6Quick, Qt6Qml, Qt6WebChannel, Qt6Positioning, Qt6Pdf, possibly
# OpenSSL libraries) — and if even one is missing, Windows reports
# "DLL load failed... module could not be found" for the TOP-LEVEL import
# (QtWebEngineCore), rather than identifying the actual missing file. Without
# external tools (see below), it is practically impossible to determine
# exactly which dependency is missing. It is simpler and more reliable to take
# all .dll/.exe files from the same build together — this guarantees internal
# consistency.
#
# IMPORTANT: the tuple format here is
# (destination_name, source_file_path, "BINARY"),
# NOT (source_file_path, destination_directory), as used by the CLI
# --add-binary flag.
# This is the low-level TOC format because we add the files directly to
# a.binaries AFTER creating Analysis() (see below). The simpler 2-element
# format would work through Analysis(binaries=[...]), but it performs its own
# normalization, which prevents us from reliably replacing automatically
# detected duplicates.
if not os.path.isdir(QT6_CUSTOM_BIN):
    raise FileNotFoundError(
        f"Custom Qt build directory not found: {QT6_CUSTOM_BIN}\n"
        f"Check QT6_CUSTOM_BIN at the beginning of wat_pro.spec"
    )

custom_qt_binaries = []
CUSTOM_QT_FILES = []  # populated below with the actual names of discovered files

# IMPORTANT: destination is PyQt6/Qt6/bin/<filename>, NOT simply <filename>
# (the bundle root). QtWebEngineProcess.exe itself looks for the process
# executable at the exact nested path
# "<exe folder>/_internal/PyQt6/Qt6/bin/QtWebEngineProcess.exe"
# (the same layout used in site-packages). With a flat "." destination,
# this check fails ("could not find Qt WebEngine Process") even if the file
# physically exists in the bundle, simply in the wrong location.
QT6_DEST_SUBDIR = os.path.join("PyQt6", "Qt6", "bin")

for filename in os.listdir(QT6_CUSTOM_BIN):
    if not filename.lower().endswith((".dll", ".exe")):
        continue
    src_path = os.path.join(QT6_CUSTOM_BIN, filename)
    if not os.path.isfile(src_path):
        continue
    CUSTOM_QT_FILES.append(filename)
    custom_qt_binaries.append((os.path.join(QT6_DEST_SUBDIR, filename), src_path, "BINARY"))

if not custom_qt_binaries:
    raise FileNotFoundError(
        f"No .dll/.exe files found in {QT6_CUSTOM_BIN} — "
        f"check the QT6_CUSTOM_BIN path"
    )

print(f"[wat_pro.spec] Taking {len(custom_qt_binaries)} files from custom Qt build: {QT6_CUSTOM_BIN}")

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

# --- Important: remove Analysis() copies of these same DLLs ---
# PyInstaller automatically finds Qt6Core.dll/Qt6WebEngineCore.dll and
# similar files as dependencies of PyQt6 .pyd modules — these are the
# STANDARD versions from the regular PyQt6-Qt6 pip package, without
# proprietary codecs.
#
# If we simply ADD our own files through binaries=[...], there will be two
# files with the same destination name. Which one actually ends up in the
# build is not guaranteed (it depends on TOC merge order in the specific
# PyInstaller version). Therefore, explicitly remove the automatically
# detected copies of EXACTLY these files, leaving their destinations only
# for our custom-built versions.
_custom_names = {name.lower() for name in CUSTOM_QT_FILES}

a.binaries = [
    entry for entry in a.binaries
    if os.path.basename(entry[0]).lower() not in _custom_names
]

a.binaries += custom_qt_binaries

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="WAT Pro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="qt_test_tool/resources/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="WAT Pro",
)
