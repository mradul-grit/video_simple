# On-device end-to-end test: real app on an Android emulator against the local Docker stack.
# Usage: powershell -File scripts/run-device-e2e.ps1 [-Device emulator-5554]
# Needs: `docker compose up -d`, a booted emulator visible to adb, ffmpeg + flutter on PATH,
# backend/.venv (used only to serve the test clip on 127.0.0.1:8765 while the test runs).
param([string]$Device = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$mobile = Join-Path $root "mobile"
$python = Join-Path $root "backend\.venv\Scripts\python.exe"

$ready = Invoke-RestMethod http://localhost:8000/api/v1/health/ready
if ($ready.status -ne "ready") { throw "Backend not ready: $($ready | ConvertTo-Json -Compress)" }

# 12 s portrait clip; the tone is silent from 6 s to 8 s, so pause detection proposes one cut.
$dir = Join-Path $env:TEMP "sf_e2e_clip"
New-Item -ItemType Directory -Force $dir | Out-Null
$clip = Join-Path $dir "e2e_clip.mp4"
& ffmpeg -y -v error -f lavfi -i "testsrc=duration=12:size=720x1280:rate=30" -f lavfi -i "sine=frequency=330:duration=12" -af "volume='if(between(t,6,8),0,1)':eval=frame" -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest $clip
if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed" }

# Loopback only: the emulator reaches the host's 127.0.0.1 as 10.0.2.2.
$server = Start-Process -FilePath $python -ArgumentList @("-m", "http.server", "8765", "--bind", "127.0.0.1", "--directory", "`"$dir`"") -PassThru -WindowStyle Hidden
try {
    Start-Sleep 2
    Push-Location $mobile
    $deviceArgs = @(); if ($Device) { $deviceArgs = @("-d", $Device) }
    & flutter drive --driver=test_driver/integration_test.dart --target=integration_test/e2e_test.dart @deviceArgs
    $code = $LASTEXITCODE
    Pop-Location
} finally {
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
}
Write-Host "flutter drive exit=$code (screenshots: mobile/build/e2e_screenshots)"
exit $code
