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
    [string]$LoginPassword = "",
    # Select the target disk non-interactively. -1 means prompt.
    [int]$DiskNumber = -1,
    # Validate everything (prereqs, disk choice, generated config) WITHOUT
    # writing the card. A safe rehearsal.
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
function Info($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[OK] $m" -ForegroundColor Green }
function Die($m)  { Write-Host "[FAIL] $m" -ForegroundColor Red; exit 1 }

if ($DryRun) { Write-Host "*** DRY RUN: no disk will be written ***" -ForegroundColor Magenta }

# --- Identify the system disk(s) up front so we can NEVER target them ---
# The disk hosting C:\ (and the Windows boot/system volumes) is off-limits.
$protectedDiskNumbers = New-Object System.Collections.Generic.HashSet[int]
try {
    $sysPart = Get-Partition -DriveLetter C -ErrorAction Stop
    [void]$protectedDiskNumbers.Add([int]$sysPart.DiskNumber)
} catch {
    # If we cannot even resolve C:, refuse to continue — too risky to guess.
    Die "Could not determine which disk hosts C:\. Aborting for safety."
}
# Also protect any disk marked as the system/boot disk.
foreach ($d in (Get-Disk | Where-Object { $_.IsSystem -or $_.IsBoot })) {
    [void]$protectedDiskNumbers.Add([int]$d.Number)
}
Ok ("Protected (system) disk number(s): " + (($protectedDiskNumbers | Sort-Object) -join ", "))

# --- Must be admin (dry run may skip, since it writes nothing) ---
$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    if ($DryRun) {
        Write-Host "[warn] Not elevated. Dry run continues, but a real flash needs an Administrator PowerShell." -ForegroundColor Yellow
    } else {
        Die "Run this script from an elevated (Administrator) PowerShell."
    }
}

# --- Locate Raspberry Pi Imager CLI ---
$imager = $null
foreach ($c in @(
    "$env:ProgramFiles\Raspberry Pi Imager\rpi-imager.exe",
    "${env:ProgramFiles(x86)}\Raspberry Pi Imager\rpi-imager.exe"
)) { if (Test-Path $c) { $imager = $c; break } }
if (-not $imager) {
    if ($DryRun) {
        Write-Host "[warn] Raspberry Pi Imager not found. Install from https://www.raspberrypi.com/software/ before a real flash. (Dry run continues.)" -ForegroundColor Yellow
    } else {
        Die "Raspberry Pi Imager not found. Install it from https://www.raspberrypi.com/software/ then re-run. (The GUI alone can also do this whole step.)"
    }
} else {
    Ok "Found Imager: $imager"
}

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
    if ($DryRun) {
        Write-Host "[warn] No SSH key at $keyPub. A real run would generate one." -ForegroundColor Yellow
        $pubKey = "ssh-ed25519 AAAA...DRY_RUN_PLACEHOLDER... you@host"
    } else {
        Info "No SSH key found -- generating one (~/.ssh/id_ed25519)..."
        if (-not (Test-Path $sshDir)) { New-Item -ItemType Directory -Path $sshDir | Out-Null }
        & ssh-keygen -t ed25519 -f (Join-Path $sshDir "id_ed25519") -N '""' | Out-Null
        $pubKey = (Get-Content $keyPub -Raw).Trim()
    }
} else {
    $pubKey = (Get-Content $keyPub -Raw).Trim()
}
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

if ($DiskNumber -ge 0) {
    $diskNum = $DiskNumber
    Info "Using disk number $diskNum (from -DiskNumber)."
} else {
    $diskNum = Read-Host "Enter the DISK NUMBER of your SD card from the list above"
    if ($diskNum -notmatch '^\d+$') { Die "Disk number must be numeric." }
    $diskNum = [int]$diskNum
}
$disk = Get-Disk -Number $diskNum -ErrorAction SilentlyContinue
if (-not $disk) { Die "Disk $diskNum not found." }

# --- SAFETY GUARDS: never touch the system disk / C: drive ---
if ($protectedDiskNumbers.Contains([int]$disk.Number)) {
    Die "Disk $diskNum hosts the Windows system/boot volume (C:). REFUSING to write to it."
}
if ($disk.IsSystem -or $disk.IsBoot) {
    Die "Disk $diskNum is a system/boot disk. REFUSING to write to it."
}
# Double-check no volume on this disk is the C: drive.
$letters = @(Get-Partition -DiskNumber $disk.Number -ErrorAction SilentlyContinue |
    Where-Object { $_.DriveLetter } | ForEach-Object { $_.DriveLetter })
if ($letters -contains 'C') {
    Die "Disk $diskNum contains the C: volume. REFUSING to write to it."
}
if (-not ($disk.IsRemovable -or $disk.BusType -in @("USB","SD"))) {
    Die "Disk $diskNum is not removable (BusType=$($disk.BusType)). Refusing to write to it."
}
$sizeGB = [math]::Round($disk.Size/1GB,1)
if ($sizeGB -gt 256) {
    Die "Disk $diskNum is $sizeGB GB - far larger than an SD card. Refusing as a safety precaution."
}

Write-Host ""
Write-Host "About to ERASE and flash:" -ForegroundColor Yellow
Write-Host "  Disk $($disk.Number): $($disk.FriendlyName) ($sizeGB GB, BusType=$($disk.BusType))" -ForegroundColor Yellow
if ($letters.Count -gt 0) {
    Write-Host ("  Drive letters on this disk: " + ($letters -join ', ')) -ForegroundColor Yellow
}

if ($DryRun) {
    Ok "DRY RUN: disk $diskNum passed all safety checks and would be flashed."
} else {
    $confirm = Read-Host "Type YES to continue (anything else aborts)"
    if ($confirm -ne "YES") { Die "Aborted by user." }
}

# --- Flash with Imager CLI ---
$physical = "\\.\PhysicalDrive$($disk.Number)"
if ($DryRun) {
    Info "DRY RUN: would run: `"$imager`" --cli --disable-verify `"$ImageUrlOrPath`" `"$physical`""
} else {
    Info "Writing image (this can take several minutes)..."
    & $imager --cli --disable-verify $ImageUrlOrPath $physical
    if ($LASTEXITCODE -ne 0) { Die "Imager failed to write the card." }
    Ok "Image written"
}

# --- Build the custom.toml first so dry run can show it ---
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

if ($DryRun) {
    Write-Host ""
    Write-Host "DRY RUN: custom.toml that would be written to the boot partition:" -ForegroundColor Magenta
    Write-Host "------------------------------------------------------------"
    # Mask secrets in the preview.
    ($toml -replace '(password = ").*(")', '$1********$2') | Write-Host
    Write-Host "------------------------------------------------------------"
    Ok "DRY RUN complete - nothing was written. Re-run without -DryRun (elevated) to flash."
    return
}

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
