# build_msix.ps1
#
# Собирает WAT Pro в MSIX. Запускать из PowerShell на Windows, из корня
# проекта, ПОСЛЕ того как уже собрана PyInstaller-версия:
#
#   pyinstaller wat_pro.spec
#   .\build_msix.ps1
#
# Результат: WATPro.msix в корне проекта.
#
# Не тестировал этот скрипт вживую (MakeAppx.exe — только Windows, нет
# способа проверить в моей среде) — сверялся с официальной документацией
# Microsoft по MSIX, но на реальном прогоне могут вылезти мелочи вроде
# другого пути к Windows SDK на вашей машине.

$ErrorActionPreference = "Stop"

$distDir = "dist\WAT Pro"
$msixSrcDir = "msix_package_tmp"
$outputMsix = "WATPro.msix"

if (-not (Test-Path $distDir)) {
    Write-Host "Папка '$distDir' не найдена. Сначала: pyinstaller wat_pro.spec" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "msix\AppxManifest.xml")) {
    Write-Host "Не найден msix\AppxManifest.xml — проверьте, что заполнили Identity/Publisher из Partner Center" -ForegroundColor Red
    exit 1
}
if (Select-String -Path "msix\AppxManifest.xml" -Pattern "ЗАПОЛНИТЬ ИЗ PARTNER CENTER" -Quiet) {
    Write-Host "В AppxManifest.xml остались незаполненные плейсхолдеры 'ЗАПОЛНИТЬ ИЗ PARTNER CENTER' — сначала подставьте реальные Identity/Publisher." -ForegroundColor Red
    exit 1
}

# Собираем временную папку пакета: exe + _internal + манифест + картинки
if (Test-Path $msixSrcDir) { Remove-Item $msixSrcDir -Recurse -Force }
Copy-Item $distDir $msixSrcDir -Recurse
Copy-Item "msix\AppxManifest.xml" "$msixSrcDir\AppxManifest.xml"
Copy-Item "msix\Images" "$msixSrcDir\Images" -Recurse

# Ищем MakeAppx.exe (ставится вместе с Windows SDK, обычно через Visual
# Studio Installer -> Individual components -> Windows SDK)
$makeAppx = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin" -Recurse -Filter "makeappx.exe" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "x64" } | Select-Object -First 1 -ExpandProperty FullName

if (-not $makeAppx) {
    Write-Host "MakeAppx.exe не найден. Установите Windows SDK: Visual Studio Installer -> Individual components -> Windows 10/11 SDK" -ForegroundColor Red
    exit 1
}

Write-Host "Использую MakeAppx: $makeAppx"
& $makeAppx pack /d $msixSrcDir /p $outputMsix /o

if ($LASTEXITCODE -eq 0) {
    Write-Host "Готово: $outputMsix" -ForegroundColor Green
    Write-Host "Для локальной проверки перед отправкой в Store: .\sign_for_local_testing.ps1" -ForegroundColor Yellow
} else {
    Write-Host "MakeAppx завершился с ошибкой (код $LASTEXITCODE)" -ForegroundColor Red
}
