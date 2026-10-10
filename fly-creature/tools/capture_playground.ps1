param([int]$Port = 18771, [switch]$ChecksOnly)
$ErrorActionPreference = 'Stop'
$creatureDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $creatureDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = Join-Path (Split-Path $creatureDir -Parent) '.venv\Scripts\python.exe' }
$godot = 'C:\Users\ringd\.codex\tools\godot\4.7\Godot_v4.7-stable_win64_console.exe'
$ffmpeg = 'C:\Users\ringd\.codex\tools\ffmpeg\ffmpeg-9.0.2-essentials_build\bin\ffmpeg.exe'
$outputDir = Join-Path $creatureDir 'outputs\playground'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$overridePath = Join-Path $creatureDir 'godot\override.cfg'
if (Test-Path -LiteralPath $overridePath) { throw 'Existing viewport override; refusing to overwrite.' }
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw 'Capture port occupied.' }
$previousEndpoint = $env:FLY_CREATURE_ENDPOINT
$serverProcess = $null
try {
    $env:FLY_CREATURE_ENDPOINT = "http://127.0.0.1:$Port"
    [System.IO.File]::WriteAllText($overridePath, "[display]`nwindow/size/viewport_width=1920`nwindow/size/viewport_height=1080`n")
    $serverProcess = Start-Process $python -ArgumentList @('-m','fly_creature.server','--port',$Port) -WorkingDirectory $creatureDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $outputDir 'server.out.log') -RedirectStandardError (Join-Path $outputDir 'server.err.log')
    $ready = $false
    for ($attempt=0; $attempt -lt 50; $attempt++) {
        try { Invoke-RestMethod "$env:FLY_CREATURE_ENDPOINT/health" -TimeoutSec 1 | Out-Null; $ready=$true; break } catch { Start-Sleep -Milliseconds 100 }
    }
    if (-not $ready) { throw 'Service not ready.' }
    $scenes = if ($ChecksOnly) { @('playground_check') } else { @('playground_check','playground') }
    foreach ($scene in $scenes) {
        $stem = Join-Path $outputDir $scene
        $argsList = @('--path',('"'+(Join-Path $creatureDir 'godot')+'"'), '--display-driver','windows','--rendering-method','gl_compatibility','--audio-driver','Dummy','--position','-5000,-5000','--log-file',('"'+$stem+'.log"'))
        if ($scene -eq 'playground') { $argsList += @('--fixed-fps','60','--write-movie',('"'+$stem+'.avi"')) }
        $argsList += @("res://$scene.tscn",'--','--playground-seconds=8','--playground-trace')
        $render = Start-Process $godot -ArgumentList $argsList -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput ($stem+'.stdout.log') -RedirectStandardError ($stem+'.stderr.log')
        if ($render.ExitCode -ne 0) { throw "Godot failed: $scene" }
        if (Select-String -LiteralPath ($stem+'.log') -Pattern 'SCRIPT ERROR|ERROR:' -Quiet) { throw "Godot errors: $scene" }
        if ($scene -eq 'playground_check' -and -not (Select-String -LiteralPath ($stem+'.log') -Pattern 'PLAYGROUND_UI_CHECK' -Quiet)) { throw 'UI check did not finish.' }
    }
    if ($ChecksOnly) { Write-Output 'Graphical playground checks passed.'; return }
    $stem = Join-Path $outputDir 'playground'
    & $ffmpeg -hide_banner -loglevel error -y -i ($stem+'.avi') -an -c:v libx264 -crf 18 -preset fast -pix_fmt yuv420p -movflags +faststart ($stem+'.mp4')
    if ($LASTEXITCODE -ne 0) { throw 'Encoding failed.' }
    & $ffmpeg -hide_banner -loglevel error -y -ss 4 -i ($stem+'.mp4') -frames:v 1 ($stem+'.png')
    if ($LASTEXITCODE -ne 0) { throw 'Frame extraction failed.' }
    Write-Output ($stem+'.mp4')
} finally {
    if ($null -ne $serverProcess -and -not $serverProcess.HasExited) { Stop-Process -Id $serverProcess.Id }
    $env:FLY_CREATURE_ENDPOINT = $previousEndpoint
    if (Test-Path -LiteralPath $overridePath) { Remove-Item -LiteralPath $overridePath }
}
