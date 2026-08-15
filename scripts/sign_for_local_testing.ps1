# sign_for_local_testing.ps1
#
# Signs WATPro.msix with a self-signed certificate — ONLY to install and
# test the package on your own machine BEFORE submitting it to the Store.
# This is not required for actual publication: Partner Center will
# re-sign the package with its own certificate during the certification process.
#
# IMPORTANT: The certificate Subject (-Subject "CN=...") MUST MATCH
# the Publisher value from AppxManifest.xml character-for-character —
# otherwise Windows will refuse to install the package with an error such as
# "signature validation failed / publisher mismatch".
#
# Run from PowerShell AS ADMINISTRATOR (required to install the certificate
# into LocalMachine\TrustedPeople).

$ErrorActionPreference = "Stop"

$publisherCN = "[FILL IN FROM PARTNER CENTER: the same value as Publisher in AppxManifest.xml]"
$msixPath = "WATPro.msix"

if ($publisherCN -match "FILL IN") {
    Write-Host "First, replace the actual Publisher CN (the same value as in AppxManifest.xml) in the `$publisherCN variable of this script." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $msixPath)) {
    Write-Host "$msixPath not found — run: .\build_msix.ps1 first" -ForegroundColor Red
    exit 1
}

$cert = New-SelfSignedCertificate `
    -Type Custom `
    -Subject $publisherCN `
    -KeyUsage DigitalSignature `
    -FriendlyName "WAT Pro — test certificate (local testing only)" `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")

Write-Host "Certificate created, thumbprint: $($cert.Thumbprint)"

# Export the public part and add it to the trusted store — without this,
# Windows will refuse to install the self-signed package
Export-Certificate -Cert $cert -FilePath "WATProTestCert.cer" | Out-Null
Import-Certificate -FilePath "WATProTestCert.cer" -CertStoreLocation "Cert:\LocalMachine\TrustedPeople" | Out-Null

$signtool = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin" -Recurse -Filter "signtool.exe" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "x64" } | Select-Object -First 1 -ExpandProperty FullName

if (-not $signtool) {
    Write-Host "signtool.exe not found (it is also part of the Windows SDK)" -ForegroundColor Red
    exit 1
}

& $signtool sign /fd SHA256 /sha1 $cert.Thumbprint $msixPath

if ($LASTEXITCODE -eq 0) {
    Write-Host "Signed. Install for testing: Add-AppxPackage -Path $msixPath" -ForegroundColor Green
} else {
    Write-Host "signtool finished with an error (code $LASTEXITCODE)" -ForegroundColor Red
}
