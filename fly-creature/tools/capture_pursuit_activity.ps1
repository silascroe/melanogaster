param(
    [int]$Port = 18769,
    [string]$Godot = 'C:\Users\ringd\.codex\tools\godot\4.7\Godot_v4.7-stable_win64_console.exe',
    [string]$FFmpeg = 'C:\Users\ringd\.codex\tools\ffmpeg\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe'
)
$ErrorActionPreference = 'Stop'
$creatureDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $creatureDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $python = Join-Path (Split-Path $creatureDir -Parent) '.venv\Scripts\python.exe'
}
foreach ($toolPath in @($python, $Godot, $FFmpeg)) {
    if (-not (Test-Path -LiteralPath $toolPath)) { throw "Missing tool: $toolPath" }
}
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    throw "Port $Port is already occupied; choose another -Port."
}
$outputDir = Join-Path $creatureDir 'outputs\pursuit_activity'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$previousEndpoint = $env:FLY_CREATURE_ENDPOINT
$serverProcess = $null
$overridePath = Join-Path $creatureDir 'godot\override.cfg'
if (Test-Path -LiteralPath $overridePath) { throw 'Existing override.cfg must be preserved; capture aborted.' }
try {
    # MovieWriter chooses its size before _ready/window overrides run.
    [System.IO.File]::WriteAllText($overridePath, "[display]`nwindow/size/viewport_width=1920`nwindow/size/viewport_height=1080`n")
    $env:FLY_CREATURE_ENDPOINT = "http://127.0.0.1:$Port"
    $serverProcess = Start-Process -FilePath $python -ArgumentList @('-m', 'fly_creature.server', '--port', $Port) -WorkingDirectory $creatureDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $outputDir 'capture_server.out.log') -RedirectStandardError (Join-Path $outputDir 'capture_server.err.log')
    $ready = $false
    for ($attempt = 0; $attempt -lt 50; $attempt++) {
        if ($serverProcess.HasExited) { throw 'Capture service exited before readiness.' }
        try {
            Invoke-RestMethod "$env:FLY_CREATURE_ENDPOINT/health" -TimeoutSec 1 | Out-Null
            $ready = $true
            break
        } catch { Start-Sleep -Milliseconds 100 }
    }
    if (-not $ready) { throw 'Capture service did not become ready.' }
    foreach ($condition in @('intact', 'disconnected')) {
        $stem = Join-Path $outputDir "activity_$condition"
        $userArgs = @('--pursuit-experimental', '--pursuit-seconds=8', '--pursuit-trace', '--capture-hd')
        if ($condition -eq 'disconnected') { $userArgs += '--pursuit-control' }
        $godotArgs = @('--path', ('"' + (Join-Path $creatureDir 'godot') + '"'), '--display-driver', 'windows', '--rendering-method', 'gl_compatibility', '--audio-driver', 'Dummy', '--resolution', '1920x1080', '--position', '-5000,-5000', '--disable-vsync', '--fixed-fps', '60', '--quit-after', '1200', '--log-file', ('"' + $stem + '.log"'), '--write-movie', ('"' + $stem + '.avi"'), '--') + $userArgs
        Write-Output "Recording $condition..."
        $renderProcess = Start-Process -FilePath $Godot -ArgumentList $godotArgs -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput ($stem + '.stdout.log') -RedirectStandardError ($stem + '.stderr.log')
        if ($renderProcess.ExitCode -ne 0) { throw "Godot failed: $condition" }
        if (Select-String -LiteralPath ($stem + '.log') -Pattern 'SCRIPT ERROR|ERROR:' -Quiet) { throw "Godot log contains errors: $condition" }
        & $FFmpeg -hide_banner -loglevel error -y -i ($stem + '.avi') -an -c:v libx264 -crf 18 -preset fast -pix_fmt yuv420p -movflags +faststart ($stem + '.mp4')
        if ($LASTEXITCODE -ne 0) { throw "Video encoding failed: $condition" }
        & $FFmpeg -hide_banner -loglevel error -y -ss 4 -i ($stem + '.mp4') -frames:v 1 ($stem + '.png')
        if ($LASTEXITCODE -ne 0) { throw "Preview extraction failed: $condition" }
        Write-Output ($stem + '.mp4')
    }
} finally {
    if ($null -ne $serverProcess -and -not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id
    }
    $env:FLY_CREATURE_ENDPOINT = $previousEndpoint
    if (Test-Path -LiteralPath $overridePath) { Remove-Item -LiteralPath $overridePath }
}
