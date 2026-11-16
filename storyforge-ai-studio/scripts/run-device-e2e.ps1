# On-device end-to-end test: real app on an Android emulator/device against the local Docker stack.
# Usage: powershell -File scripts/run-device-e2e.ps1 [-Device emulator-5554]
# Needs: docker compose stack running, a booted emulator/device visible to adb, ffmpeg on PATH.
param([string]$Device = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$mobile = Join-Path $root "mobile"
$pkg = "dev.storyforge.storyforge_mobile"
$adb = Join-Path $env:ANDROID_HOME "platform-tools\adb.exe"
$adbArgs = @(); if ($Device) { $adbArgs = @("-s", $Device) }

$ready = Invoke-RestMethod http://localhost:8000/api/v1/health/ready
if ($ready.status -ne "ready") { throw "Backend not ready: $($ready | ConvertTo-Json -Compress)" }

# 12 s portrait clip with a tone (the demo analysis proposes a 9.2-11.0 s pause cut).
$clip = Join-Path $env:TEMP "e2e_clip.mp4"
& ffmpeg -y -v error -f lavfi -i "testsrc=duration=12:size=720x1280:rate=30" -f lavfi -i "sine=frequency=330:duration=12" -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest $clip
if ($LASTEXITCODE -ne 0) { throw "ffmpeg failed" }

# Install the debug app so its private files dir exists, then copy the clip into it with run-as.
Push-Location $mobile
& flutter install --debug @(if ($Device) { @("-d", $Device) })
& $adb @adbArgs push $clip /data/local/tmp/e2e_clip.mp4 | Out-Null
& $adb @adbArgs shell "cat /data/local/tmp/e2e_clip.mp4 | run-as $pkg sh -c 'mkdir -p files && cat > files/e2e_clip.mp4'"
& $adb @adbArgs shell rm /data/local/tmp/e2e_clip.mp4

& flutter drive --driver=test_driver/integration_test.dart --target=integration_test/e2e_test.dart @(if ($Device) { @("-d", $Device) })
$code = $LASTEXITCODE
Pop-Location
Write-Host "flutter drive exit=$code (screenshots: mobile/build/e2e_screenshots)"
exit $code
