# build_msix.ps1
#
# Builds WAT Pro as an MSIX package. Run from PowerShell on Windows,
# from the project root, AFTER the PyInstaller version has already been built:
#
#   pyinstaller wat_pro.spec
#   .\build_msix.ps1
#
# Result: WATPro.msix in the project root.
#
# This script has not been tested in a live environment (MakeAppx.exe is
# Windows-only, so there is no way to test it in my current environment).
# It was checked against Microsoft's official MSIX documentation, but
# minor issues such as a different Windows SDK path on your machine
# may occur during an actual run.

$ErrorActionPreference = "Stop"

$distDir = "dist\WAT Pro"
$msixSrcDir = "msix_package_tmp"
$outputMsix = "WATPro.msix"

if (-not (Test-Path $distDir)) {
    Write-Host "Directory '$distDir' not found. Run: pyinstaller wat_pro.spec first" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "msix\AppxManifest.xml")) {
    Write-Host "msix\AppxManifest.xml not found — make sure you filled in Identity/Publisher from Partner Center" -ForegroundColor Red
    exit 1
}
if (Select-String -Path "msix\AppxManifest.xml" -Pattern "FILL IN FROM PARTNER CENTER" -Quiet) {
    Write-Host "Unfilled 'FILL IN FROM PARTNER CENTER' placeholders remain in AppxManifest.xml — replace them with the actual Identity/Publisher values first." -ForegroundColor Red
    exit 1
}

# Build a temporary package directory: exe + _internal + manifest + images
if (Test-Path $msixSrcDir) { Remove-Item $msixSrcDir -Recurse -Force }
Copy-Item $distDir $msixSrcDir -Recurse
Copy-Item "msix\AppxManifest.xml" "$msixSrcDir\AppxManifest.xml"
Copy-Item "msix\Images" "$msixSrcDir\Images" -Recurse

# Find MakeAppx.exe (installed with the Windows SDK, usually through
# Visual Studio Installer -> Individual components -> Windows SDK)
$makeAppx = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin" -Recurse -Filter "makeappx.exe" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "x64" } | Select-Object -First 1 -ExpandProperty FullName

if (-not $makeAppx) {
    Write-Host "MakeAppx.exe not found. Install the Windows SDK: Visual Studio Installer -> Individual components -> Windows 10/11 SDK" -ForegroundColor Red
    exit 1
}

Write-Host "Using MakeAppx: $makeAppx"
& $makeAppx pack /d $msixSrcDir /p $outputMsix /o

if ($LASTEXITCODE -eq 0) {
    Write-Host "Done: $outputMsix" -ForegroundColor Green
    Write-Host "For local testing before submitting to the Store: .\sign_for_local_testing.ps1" -ForegroundColor Yellow
} else {
    Write-Host "MakeAppx finished with an error (code $LASTEXITCODE)" -ForegroundColor Red
}
