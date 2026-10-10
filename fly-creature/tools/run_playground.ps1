param([int]$Port = 8768)
$ErrorActionPreference = 'Stop'
$creatureDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $creatureDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = Join-Path (Split-Path $creatureDir -Parent) '.venv\Scripts\python.exe' }
$godot = 'C:\Users\ringd\.codex\tools\godot\4.7\Godot_v4.7-stable_win64_console.exe'
foreach ($path in @($python,$godot)) { if (-not (Test-Path -LiteralPath $path)) { throw "Missing runtime: $path" } }
$serverProcess = $null
$previousEndpoint = $env:FLY_CREATURE_ENDPOINT
$outputDir = Join-Path $creatureDir 'outputs\playground'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
try {
    $env:FLY_CREATURE_ENDPOINT = "http://127.0.0.1:$Port"
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        $health = Invoke-RestMethod "$env:FLY_CREATURE_ENDPOINT/health" -TimeoutSec 2
        if ($health.project -ne 'Fly Creature' -or -not $health.comparison_playground) { throw 'Port belongs to another/older service. Choose another -Port.' }
    } else {
        $serverProcess = Start-Process $python -ArgumentList @('-m','fly_creature.server','--port',$Port) -WorkingDirectory $creatureDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $outputDir 'interactive_server.out.log') -RedirectStandardError (Join-Path $outputDir 'interactive_server.err.log')
        $ready = $false
        for ($attempt=0; $attempt -lt 50; $attempt++) {
            try { Invoke-RestMethod "$env:FLY_CREATURE_ENDPOINT/health" -TimeoutSec 1 | Out-Null; $ready=$true; break } catch { Start-Sleep -Milliseconds 100 }
        }
        if (-not $ready) { throw 'Comparison service did not start.' }
    }
    # This launcher is for the user to play locally; show the interactive game window.
    $game = Start-Process $godot -ArgumentList @('--path',('"'+(Join-Path $creatureDir 'godot')+'"'),'--rendering-method','gl_compatibility','res://playground.tscn') -WindowStyle Normal -PassThru -Wait
    if ($game.ExitCode -ne 0) { throw 'Godot exited with an error.' }
} finally {
    if ($null -ne $serverProcess -and -not $serverProcess.HasExited) { Stop-Process -Id $serverProcess.Id }
    $env:FLY_CREATURE_ENDPOINT = $previousEndpoint
}
