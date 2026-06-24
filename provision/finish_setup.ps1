<#
.SYNOPSIS
    Finish configuring a freshly-booted Raspberry Pi for NFC Jukebox, over SSH.

.DESCRIPTION
    Run this on your Windows laptop AFTER the Pi has booted and is on your
    network. It copies this repo to the Pi, runs the installer (system packages,
    SPI, virtualenv, systemd service), optionally sets the Echo device name, and
    starts the service. When it finishes, open the printed URL to connect your
    Amazon account.

    Reliable and safe: it only talks to the Pi over SSH/SCP. Nothing is written
    to local disks.

.PARAMETER PiHost
    The Pi's IP address or hostname, e.g. 192.168.1.42 or nfc-jukebox.local

.PARAMETER User
    The Pi username you set when flashing. Default: pi

.PARAMETER DeviceName
    Optional. Your Echo's exact name (as in the Alexa app). Sets ALEXA_DEVICE_NAME.

.EXAMPLE
    .\provision\finish_setup.ps1 -PiHost 192.168.1.42 -User pi -DeviceName "Kitchen Echo"
#>
param(
    [Parameter(Mandatory = $true)] [string]$PiHost,
    [string]$User = "pi",
    [string]$DeviceName = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$target = "$User@$PiHost"

function Info($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[OK] $m" -ForegroundColor Green }
function Die($m)  { Write-Host "[FAIL] $m" -ForegroundColor Red; exit 1 }

# --- Preflight: ssh/scp/tar present (all ship with Windows 10/11) ---
foreach ($tool in @("ssh", "scp", "tar")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Die "$tool not found. Install the Windows OpenSSH client (Settings > Apps > Optional Features) and ensure tar is available (Windows 10 1803+)."
    }
}
Ok "ssh, scp, tar available"

# --- Wait for SSH to come up (Pi may still be booting) ---
Info "Waiting for SSH on $target (up to 2 minutes)..."
$deadline = (Get-Date).AddMinutes(2)
$connected = $false
while ((Get-Date) -lt $deadline) {
    # BatchMode avoids hanging on password prompts during the probe.
    & ssh -o BatchMode=no -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new $target "echo ok" *> $null
    if ($LASTEXITCODE -eq 0) { $connected = $true; break }
    Start-Sleep -Seconds 5
    Write-Host "." -NoNewline
}
Write-Host ""
if (-not $connected) {
    Die "Could not reach $target over SSH. Check the IP, that the Pi finished booting, and that SSH was enabled when flashing."
}
Ok "SSH reachable"

# --- Package the local repo (exclude junk) and copy it over ---
$tarball = Join-Path $env:TEMP "nfc-jukebox.tgz"
Info "Packaging local repo..."
& tar -czf $tarball `
    --exclude=".git" --exclude=".venv" --exclude="data" `
    --exclude=".claude" --exclude="__pycache__" --exclude="*.pyc" `
    -C $repoRoot .
if ($LASTEXITCODE -ne 0) { Die "Failed to create archive of the repo." }
Ok "Archive created"

Info "Copying to Pi..."
& scp -o StrictHostKeyChecking=accept-new $tarball "${target}:/tmp/nfc-jukebox.tgz"
if ($LASTEXITCODE -ne 0) { Die "scp failed." }
Ok "Copied"

# --- Remote install. Single bash script run with a TTY so sudo can prompt. ---
$envLine = ""
if ($DeviceName -ne "") {
    # Escape single quotes for the remote shell.
    $safe = $DeviceName.Replace("'", "'\''")
    $envLine = "sudo sed -i `"s/^ALEXA_DEVICE_NAME=.*/ALEXA_DEVICE_NAME=$safe/`" /opt/nfc-jukebox/.env;"
}

$remote = @"
set -e
echo '==> Unpacking repo...'
rm -rf ~/nfc-jukebox && mkdir -p ~/nfc-jukebox
tar -xzf /tmp/nfc-jukebox.tgz -C ~/nfc-jukebox
cd ~/nfc-jukebox
echo '==> Running installer (you may be asked for your sudo password)...'
sudo ./scripts/install_pi.sh
$envLine
sudo systemctl restart nfc-jukebox.service || true
echo '==> Service status:'
systemctl is-active nfc-jukebox.service || true
"@

Info "Running installer on the Pi (this takes a few minutes)..."
# Write the remote script to a temp file with LF line endings (bash requires
# LF, not CRLF), copy it over, and run it with a TTY so sudo can prompt.
$remoteScript = Join-Path $env:TEMP "nfc_remote_setup.sh"
[System.IO.File]::WriteAllText(
    $remoteScript,
    ($remote -replace "`r`n", "`n"),
    (New-Object System.Text.UTF8Encoding $false)
)
& scp -o StrictHostKeyChecking=accept-new $remoteScript "${target}:/tmp/nfc_remote_setup.sh"
if ($LASTEXITCODE -ne 0) { Die "Failed to copy the setup script to the Pi." }
& ssh -t -o StrictHostKeyChecking=accept-new $target "bash /tmp/nfc_remote_setup.sh"
if ($LASTEXITCODE -ne 0) { Die "Remote install failed. SSH in and run 'sudo ./scripts/install_pi.sh' manually to see the error." }

Ok "Installed and service started"
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " NFC Jukebox is installed on $PiHost" -ForegroundColor Green
Write-Host ""
Write-Host " Next steps:" -ForegroundColor Green
Write-Host "  1. Open the web UI:        http://$PiHost`:8080"
Write-Host "  2. Connect Amazon (passkey): http://$PiHost`:8080/setup"
Write-Host "  3. Add albums and write NFC tags from the Albums page."
Write-Host "============================================================" -ForegroundColor Green
