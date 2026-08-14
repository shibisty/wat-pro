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

--- Своя сборка Qt WebEngine с проприетарными кодеками (H.264/AAC) ---
Поправьте путь ниже под своё расположение (там, куда `cmake --install`
положил результат сборки из гайда — Шаг 5).
"""

from PyInstaller.utils.hooks import collect_submodules
import glob
import os

block_cipher = None

# Поправьте под свой путь из инструкции сборки (C:\qt6install по умолчанию)
QT6_CUSTOM_BIN = r"C:\qt6install\bin"
QT6_CUSTOM_RESOURCES = r"C:\qt6install\resources"
QT6_CUSTOM_LOCALES = r"C:\qt6install\translations\qtwebengine_locales"
QT6_CUSTOM_PLUGINS = r"C:\qt6install\plugins"

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

# Ресурсы/локали WebEngine из своей сборки — ВАЖНО: тоже под PyQt6/Qt6/...,
# не в корень бандла. Раньше клали в корень ("resources"/"translations"),
# и это (а) не то место, где Qt их реально ищет (см. комментарий у
# custom_qt_binaries ниже — та же причина: QLibraryInfo резолвит пути
# относительно расположения Qt6Core.dll, теперь это PyQt6/Qt6/bin), и
# (б) конфликтовало по имени с СОБСТЫВЕННЫМИ resources/translations
# приложения (иконка/переводы UI) чуть выше — то и другое писалось в
# одну и ту же папку "resources" в корне бандла.
datas.append((QT6_CUSTOM_RESOURCES, os.path.join("PyQt6", "Qt6", "resources")))
datas.append((QT6_CUSTOM_LOCALES, os.path.join("PyQt6", "Qt6", "translations", "qtwebengine_locales")))

# plugins/ (platforms/imageformats/iconengines и т.д.) — без него Qt не
# может даже создать окно ("Could not find the Qt platform plugin").
# PyInstaller обычно подхватывает это сам через свой hook для PyQt6, но
# мы уже дважды ловили ситуацию, когда его не хватало в похожем сценарии
# (см. историю чата) — явно подстраховываемся, а не полагаемся на auto.
if os.path.isdir(QT6_CUSTOM_PLUGINS):
    datas.append((QT6_CUSTOM_PLUGINS, os.path.join("PyQt6", "Qt6", "plugins")))
else:
    print(f"[wat_pro.spec] ВНИМАНИЕ: не найдена папка {QT6_CUSTOM_PLUGINS} — "
          f"платформенные плагины Qt возьмутся из автообнаружения PyInstaller (стандартные)")

# Свои DLL/exe с проприетарными кодеками
#
# ВАЖНО: берём ВСЮ папку bin\ целиком, а не отдельные вручную выбранные
# файлы. Причина: полноценная сборка QtWebEngine тянет за собой МНОГО
# зависимостей помимо Core/Gui/Widgets/WebEngineCore (Qt6Network,
# Qt6Quick, Qt6Qml, Qt6WebChannel, Qt6Positioning, Qt6Pdf, возможно
# OpenSSL-библиотеки) — и если не хватает хотя бы одной, Windows пишет
# "DLL load failed... module could not be found" ПРО ВЕРХНЕУРОВНЕВЫЙ
# импорт (QtWebEngineCore), а не про реально отсутствующий файл — понять,
# чего конкретно не хватает, без сторонних инструментов (см. ниже)
# практически невозможно. Проще и надёжнее взять все .dll/.exe из одной
# и той же сборки разом — тогда внутренняя согласованность гарантирована.
#
# ВАЖНО: формат кортежа тут — (имя_назначения, путь_к_файлу, "BINARY"),
# а НЕ (путь_к_файлу, папка_назначения), как в CLI-флаге --add-binary.
# Это низкоуровневый формат TOC, потому что мы добавляем файлы напрямую
# в a.binaries ПОСЛЕ создания Analysis() (см. ниже) — через параметр
# конструктора Analysis(binaries=[...]) сработал бы более простой
# 2-элементный формат, но там своя нормализация, которая нам мешает
# (не даёт гарантированно вытеснить автообнаруженные дубликаты).
if not os.path.isdir(QT6_CUSTOM_BIN):
    raise FileNotFoundError(
        f"Не найдена папка своей сборки Qt: {QT6_CUSTOM_BIN}\n"
        f"Проверьте QT6_CUSTOM_BIN в начале wat_pro.spec"
    )

custom_qt_binaries = []
CUSTOM_QT_FILES = []  # заполняется ниже реальными именами найденных файлов
# ВАЖНО: назначение — PyQt6/Qt6/bin/<имя>, а НЕ просто <имя> (корень
# бандла). Сам QtWebEngineProcess.exe при старте ищет себя строго по
# вложенному пути "<папка exe>/_internal/PyQt6/Qt6/bin/QtWebEngineProcess.exe"
# (так же, как эти файлы лежат в site-packages) — с плоским "." эта
# проверка проваливается ("could not find Qt WebEngine Process"), даже
# если сам файл физически присутствует в бандле, просто не в том месте.
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
        f"В папке {QT6_CUSTOM_BIN} не найдено ни одного .dll/.exe — "
        f"проверьте путь QT6_CUSTOM_BIN"
    )
print(f"[wat_pro.spec] Беру {len(custom_qt_binaries)} файлов из своей сборки Qt: {QT6_CUSTOM_BIN}")

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

# --- Важно: убираем автообнаруженные Analysis() копии этих же DLL ---
# PyInstaller сам находит Qt6Core.dll/Qt6WebEngineCore.dll и т.п. как
# зависимости .pyd-модулей PyQt6 — это СТАНДАРТНЫЕ версии из обычного
# pip-пакета PyQt6-Qt6, без кодеков. Если просто ДОБАВИТЬ свои через
# binaries=[...], получится два файла с одинаковым именем назначения —
# какой из них реально попадёт в сборку, не гарантировано (зависит от
# порядка слияния TOC в конкретной версии PyInstaller). Поэтому явно
# вычищаем автообнаруженные копии ИМЕННО этих файлов, оставляя место
# только для собранных вручную.
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
