# sign_for_local_testing.ps1
#
# Подписывает WATPro.msix самоподписанным сертификатом — ТОЛЬКО чтобы
# самому установить и проверить пакет на своей машине ДО отправки в
# Store. Для реальной публикации это не нужно: Partner Center сам
# пересобирает подпись своим сертификатом при прохождении сертификации.
#
# ВАЖНО: Subject сертификата (-Subject "CN=...") ДОЛЖЕН СОВПАДАТЬ 1-в-1
# с Publisher из AppxManifest.xml — иначе Windows откажется устанавливать
# пакет с ошибкой "signature validation failed / publisher mismatch".
#
# Запускать из PowerShell С ПРАВАМИ АДМИНИСТРАТОРА (нужно для установки
# сертификата в LocalMachine\TrustedPeople).

$ErrorActionPreference = "Stop"

$publisherCN = "[ЗАПОЛНИТЬ ИЗ PARTNER CENTER: то же значение, что Publisher в AppxManifest.xml]"
$msixPath = "WATPro.msix"

if ($publisherCN -match "ЗАПОЛНИТЬ") {
    Write-Host "Сначала подставьте реальный Publisher CN (тот же, что в AppxManifest.xml) в переменную `$publisherCN этого скрипта." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $msixPath)) {
    Write-Host "$msixPath не найден — сначала: .\build_msix.ps1" -ForegroundColor Red
    exit 1
}

$cert = New-SelfSignedCertificate `
    -Type Custom `
    -Subject $publisherCN `
    -KeyUsage DigitalSignature `
    -FriendlyName "WAT Pro — тестовый сертификат (только для локальной проверки)" `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")

Write-Host "Сертификат создан, thumbprint: $($cert.Thumbprint)"

# Экспортируем публичную часть и добавляем в доверенные — без этого
# Windows откажется устанавливать самоподписанный пакет
Export-Certificate -Cert $cert -FilePath "WATProTestCert.cer" | Out-Null
Import-Certificate -FilePath "WATProTestCert.cer" -CertStoreLocation "Cert:\LocalMachine\TrustedPeople" | Out-Null

$signtool = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin" -Recurse -Filter "signtool.exe" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "x64" } | Select-Object -First 1 -ExpandProperty FullName

if (-not $signtool) {
    Write-Host "signtool.exe не найден (тоже часть Windows SDK)" -ForegroundColor Red
    exit 1
}

& $signtool sign /fd SHA256 /sha1 $cert.Thumbprint $msixPath

if ($LASTEXITCODE -eq 0) {
    Write-Host "Подписано. Установить для проверки: Add-AppxPackage -Path $msixPath" -ForegroundColor Green
} else {
    Write-Host "signtool завершился с ошибкой (код $LASTEXITCODE)" -ForegroundColor Red
}
