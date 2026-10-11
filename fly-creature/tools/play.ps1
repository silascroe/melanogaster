# One-step launcher: starts the Python neural service, opens the Godot scene,
# and stops the service when the game window closes. Errors show in a dialog
# because Play-Fly-Creature.cmd runs this script without a console window.
param(
    [int]$Port = 8768,
    [ValidateSet('main', 'playground')][string]$Scene = 'main'
)
$ErrorActionPreference = 'Stop'
$creatureDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$workspaceDir = Split-Path $creatureDir -Parent
$logDir = Join-Path $creatureDir 'outputs\launcher'

function Show-Error([string]$message) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($message, 'Fly Creature', 'OK', 'Error') | Out-Null
}

function Find-First([string[]]$candidates) {
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
    }
    return $null
}

$serverProcess = $null
try {
    $python = Find-First @(
        (Join-Path $creatureDir '.venv\Scripts\python.exe'),
        (Join-Path $workspaceDir '.venv\Scripts\python.exe'))
    if (-not $python) {
        throw "No Python environment found.`nCreate one in fly-creature\.venv (see README, 'Run')."
    }
    $onPath = Get-Command godot -ErrorAction SilentlyContinue
    $godot = Find-First @(
        $env:FLY_CREATURE_GODOT,
        (Join-Path $workspaceDir 'tools\godot\4.7\Godot_v4.7-stable_win64.exe'),
        (Join-Path $env:USERPROFILE '.codex\tools\godot\4.7\Godot_v4.7-stable_win64.exe'),
        $(if ($onPath) { $onPath.Source }))
    if (-not $godot) {
        throw "Godot 4 not found.`nSet FLY_CREATURE_GODOT to your Godot .exe path."
    }
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $endpoint = "http://127.0.0.1:$Port"
    $reuse = $false
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
        try { $health = Invoke-RestMethod "$endpoint/health" -TimeoutSec 2 } catch { $health = $null }
        if ($null -eq $health -or $health.project -ne 'Fly Creature') {
            throw "Port $Port is used by another program.`nRun tools\play.ps1 -Port <other number>."
        }
        $reuse = $true  # A service is already running (e.g. started by hand); leave it alone.
    }
    if (-not $reuse) {
        $serverProcess = Start-Process $python -ArgumentList @('-m', 'fly_creature.server', '--port', $Port) `
            -WorkingDirectory $creatureDir -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $logDir 'server.out.log') `
            -RedirectStandardError (Join-Path $logDir 'server.err.log')
        $ready = $false
        for ($attempt = 0; $attempt -lt 100; $attempt++) {
            if ($serverProcess.HasExited) { break }
            try { Invoke-RestMethod "$endpoint/health" -TimeoutSec 1 | Out-Null; $ready = $true; break }
            catch { Start-Sleep -Milliseconds 100 }
        }
        if (-not $ready) {
            throw "The neural service did not start.`nSee $logDir\server.err.log"
        }
    }
    $env:FLY_CREATURE_ENDPOINT = $endpoint
    $godotArgs = @('--path', ('"' + (Join-Path $creatureDir 'godot') + '"'))
    if ($Scene -eq 'playground') { $godotArgs += 'res://playground.tscn' }
    Start-Process $godot -ArgumentList $godotArgs -WindowStyle Normal -Wait
} catch {
    Show-Error $_.Exception.Message
    exit 1
} finally {
    if ($null -ne $serverProcess -and -not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force
    }
}
