# -*- mode: python ; coding: utf-8 -*-
"""
Сборка WAT Pro в exe.

Запуск (на Windows, из папки с run.py):
    pyinstaller wat_pro.spec

Собирается в режиме --onedir (COLLECT), не --onefile — так надёжнее для
QtWebEngine: --onefile распаковывает всё во временную папку при каждом
запуске (лишние секунды старта, и ресурсы WebEngine иногда подхватываются
не с первого раза); --onedir просто работает.

Результат: dist/WAT Pro/WAT Pro.exe — раздавать нужно всю папку
"WAT Pro" целиком (можно зазипованную), не один exe.
"""

from PyInstaller.utils.hooks import collect_submodules
import glob

block_cipher = None

hiddenimports = collect_submodules("qt_test_tool")

# Кладём translations/ и resources/ ПРЯМО в корень бандла (рядом с exe в
# --onedir), а не под qt_test_tool/... — именно там их ищет core/config.py
# (BUNDLE_DIR/translations, BUNDLE_DIR/resources). collect_data_files()
# по умолчанию сохраняет структуру пакета (qt_test_tool/translations/...),
# что не совпадает с этим расположением — поэтому здесь делаем явно.
datas = []
for f in glob.glob("qt_test_tool/translations/*.json"):
    datas.append((f, "translations"))
for f in glob.glob("qt_test_tool/resources/*"):
    datas.append((f, "resources"))

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
