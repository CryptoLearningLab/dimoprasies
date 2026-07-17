$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

$TailscaleCandidates = @(
    "$env:ProgramFiles\Tailscale\tailscale.exe",
    "${env:ProgramFiles(x86)}\Tailscale\tailscale.exe",
    "$env:LocalAppData\Tailscale\tailscale.exe"
) | Where-Object { $_ -and (Test-Path $_) }

$TailscaleIp = $null
if ($TailscaleCandidates.Count -gt 0) {
    try {
        $TailscaleIp = (& $TailscaleCandidates[0] ip -4 | Select-Object -First 1).Trim()
    } catch {
        $TailscaleIp = $null
    }
}

if (-not $TailscaleIp) {
    Write-Host "Could not detect a Tailscale IPv4 address."
    Write-Host "Starting on 0.0.0.0. Use only on a trusted private/Tailscale network."
    $HostAddress = "0.0.0.0"
    $OpenUrl = "http://127.0.0.1:8765/"
} else {
    $HostAddress = $TailscaleIp
    $OpenUrl = "http://${TailscaleIp}:8765/"
}

Write-Host ""
Write-Host "Tender Radar UI"
Write-Host "Local URL:     http://127.0.0.1:8765/"
Write-Host "Tailscale URL: $OpenUrl"
Write-Host ""
Write-Host "Open the Tailscale URL from your phone while Tailscale is connected."
Write-Host "Keep this window open while using the app."
Write-Host ""

Start-Process $OpenUrl
& $Python -m tender_radar.ui_server --host $HostAddress --port 8765
