<#
.SYNOPSIS
    Flash Raspberry Pi OS to an SD card and pre-configure it for headless boot.
    (ADVANCED / EXPERIMENTAL -- the Raspberry Pi Imager GUI is the recommended,
    fully-supported alternative; see README "Flash the SD card".)

.DESCRIPTION
    Run on your Windows laptop as Administrator with the SD card inserted. It:
      1. Uses Raspberry Pi Imager's CLI to write Raspberry Pi OS Lite 64-bit.
      2. Writes a `custom.toml` to the boot partition so the Pi comes up
         headless with: hostname nfc-jukebox, your user, SSH enabled (key auth),
         Wi-Fi, and locale. No keyboard/monitor needed.

    SAFETY: it lists disks and makes you type the target disk number and then
    YES before writing. It refuses non-removable disks unless you force it.

    Because this performs a raw disk write and depends on your exact machine
    setup, VERIFY the target disk carefully. If anything looks off, use the
    Imager GUI instead.

.PARAMETER ImageUrlOrPath
    URL or local path to a .img/.img.xz. Default: latest Raspberry Pi OS Lite
    arm64 (verify it is Trixie / Python 3.12+ -- required by aioamazondevices).

.PARAMETER Hostname
    Pi hostname. Default: nfc-jukebox

.PARAMETER User
    Pi username to create. Default: pi

.EXAMPLE
    # From an elevated PowerShell:
    .\provision\flash_sd_card.ps1
#>
param(
    [string]$ImageUrlOrPath = "https://downloads.raspberrypi.com/raspios_lite_arm64_latest",
    [string]$Hostname = "nfc-jukebox",
    [string]$User = "pi",
    # Provide these to skip the interactive prompts (Wi-Fi setup baked in).
    [string]$WifiSsid = "",
    [string]$WifiPassword = "",
    [string]$WifiCountry = "US",
    [string]$Timezone = "America/New_York",
    [string]$LoginPassword = ""
)

$ErrorActionPreference = "Stop"
function Info($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[OK] $m" -ForegroundColor Green }
function Die($m)  { Write-Host "[FAIL] $m" -ForegroundColor Red; exit 1 }

# --- Must be admin ---
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Die "Run this script from an elevated (Administrator) PowerShell." }

# --- Locate Raspberry Pi Imager CLI ---
$imager = $null
foreach ($c in @(
    "$env:ProgramFiles\Raspberry Pi Imager\rpi-imager.exe",
    "${env:ProgramFiles(x86)}\Raspberry Pi Imager\rpi-imager.exe"
)) { if (Test-Path $c) { $imager = $c; break } }
if (-not $imager) {
    Die "Raspberry Pi Imager not found. Install it from https://www.raspberrypi.com/software/ then re-run. (The GUI alone can also do this whole step.)"
}
Ok "Found Imager: $imager"

# --- Locate openssl (Git for Windows ships it) for password hashing ---
$openssl = (Get-Command openssl -ErrorAction SilentlyContinue).Source
if (-not $openssl) {
    foreach ($c in @("$env:ProgramFiles\Git\usr\bin\openssl.exe")) {
        if (Test-Path $c) { $openssl = $c; break }
    }
}
if (-not $openssl) { Die "openssl not found (needed to hash the login password). Install Git for Windows, or use the Imager GUI." }
Ok "Found openssl: $openssl"

# --- Ensure an SSH key exists (used for passwordless SSH to the Pi) ---
$sshDir = Join-Path $env:USERPROFILE ".ssh"
$keyPub = Join-Path $sshDir "id_ed25519.pub"
if (-not (Test-Path $keyPub)) {
    Info "No SSH key found -- generating one (~/.ssh/id_ed25519)..."
    if (-not (Test-Path $sshDir)) { New-Item -ItemType Directory -Path $sshDir | Out-Null }
    & ssh-keygen -t ed25519 -f (Join-Path $sshDir "id_ed25519") -N '""' | Out-Null
}
$pubKey = (Get-Content $keyPub -Raw).Trim()
Ok "SSH public key ready"

# --- Collect settings (parameters skip the prompts) ---
if ($LoginPassword -ne "") {
    $pwPlain = $LoginPassword
} else {
    $pw = Read-Host "Set a login password for user '$User'" -AsSecureString
    $pwPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($pw))
}
$pwHash = (& $openssl passwd -6 $pwPlain).Trim()

$wifiSsid = $WifiSsid
$wifiPass = $WifiPassword
if ($wifiSsid -eq "") {
    $wifiSsid = Read-Host "Wi-Fi network name (SSID) (leave blank if using Ethernet)"
    if ($wifiSsid -ne "") {
        $wsec = Read-Host "Wi-Fi password" -AsSecureString
        $wifiPass = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($wsec))
    }
}
$country = $WifiCountry
$tz = $Timezone

# --- Select target disk ---
Info "Removable disks detected:"
$disks = Get-Disk | Where-Object { $_.BusType -in @("USB", "SD") -or $_.IsRemovable }
if (-not $disks) { Die "No removable disks found. Insert the SD card (or its reader) and retry." }
$disks | Format-Table Number, FriendlyName, @{N="Size(GB)";E={[math]::Round($_.Size/1GB,1)}}, BusType -AutoSize

$diskNum = Read-Host "Enter the DISK NUMBER of your SD card from the list above"
$disk = Get-Disk -Number $diskNum -ErrorAction SilentlyContinue
if (-not $disk) { Die "Disk $diskNum not found." }
if (-not ($disk.IsRemovable -or $disk.BusType -in @("USB","SD"))) {
    Die "Disk $diskNum is not removable. Refusing to write to it."
}

Write-Host ""
Write-Host "About to ERASE and flash:" -ForegroundColor Yellow
Write-Host "  Disk $($disk.Number): $($disk.FriendlyName) ($([math]::Round($disk.Size/1GB,1)) GB)" -ForegroundColor Yellow
$confirm = Read-Host "Type YES to continue (anything else aborts)"
if ($confirm -ne "YES") { Die "Aborted by user." }

# --- Flash with Imager CLI ---
$physical = "\\.\PhysicalDrive$($disk.Number)"
Info "Writing image (this can take several minutes)..."
& $imager --cli --disable-verify $ImageUrlOrPath $physical
if ($LASTEXITCODE -ne 0) { Die "Imager failed to write the card." }
Ok "Image written"

# --- Write custom.toml to the boot partition for headless first boot ---
Info "Locating boot partition..."
Start-Sleep -Seconds 5
$bootVol = $null
for ($i = 0; $i -lt 12; $i++) {
    $bootVol = Get-Volume -FileSystemLabel "bootfs" -ErrorAction SilentlyContinue
    if ($bootVol -and $bootVol.DriveLetter) { break }
    Start-Sleep -Seconds 2
}
if (-not $bootVol -or -not $bootVol.DriveLetter) {
    Die "Could not find the 'bootfs' partition with a drive letter. Re-insert the card, or use the Imager GUI customization (Option A in the README) instead."
}
$bootRoot = "$($bootVol.DriveLetter):\"

$wlanBlock = ""
if ($wifiSsid -ne "") {
@"
[wlan]
ssid = "$wifiSsid"
password = "$wifiPass"
password_encrypted = false
country = "$country"
hidden = false
"@ | Set-Variable -Name wlanBlock
}

$toml = @"
# Generated by flash_sd_card.ps1 -- Raspberry Pi OS first-boot configuration.
[system]
hostname = "$Hostname"

[user]
name = "$User"
password = "$pwHash"
password_encrypted = true

[ssh]
enabled = true
password_authentication = false
authorized_keys = [ "$pubKey" ]

$wlanBlock
[locale]
keymap = "us"
timezone = "$tz"
"@

$tomlPath = Join-Path $bootRoot "custom.toml"
$toml | Out-File -FilePath $tomlPath -Encoding ascii -NoNewline
Ok "Wrote $tomlPath"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " SD card is ready." -ForegroundColor Green
Write-Host ""
Write-Host " Next steps:" -ForegroundColor Green
Write-Host "  1. Eject the card, insert it into the Pi, and power on."
Write-Host "  2. Wait ~90 seconds for first boot."
Write-Host "  3. Find the Pi's IP (router device list, or try '$Hostname.local')."
Write-Host "  4. Finish setup from this laptop:"
Write-Host "       .\provision\finish_setup.ps1 -PiHost <IP> -User $User"
Write-Host "============================================================" -ForegroundColor Green
