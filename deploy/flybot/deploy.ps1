[CmdletBinding()]
param(
    [string]$HostAlias = "first-droplet",
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$ErrorActionPreference = "Stop"

$sourceRoot = (Resolve-Path -LiteralPath $RepositoryRoot).Path
$sources = @(
    @{
        Local = Join-Path $sourceRoot "src\flytest\__init__.py"
        RemoteName = "__init__.py"
    },
    @{
        Local = Join-Path $sourceRoot "src\flytest\discord_bridge.py"
        RemoteName = "discord_bridge.py"
    },
    @{
        Local = Join-Path $sourceRoot "deploy\flybot\flybot.service"
        RemoteName = "flybot.service"
    }
)

foreach ($source in $sources) {
    if (-not (Test-Path -LiteralPath $source.Local -PathType Leaf)) {
        throw "Required deployment source is missing: $($source.Local)"
    }
}

$localStage = Join-Path ([System.IO.Path]::GetTempPath()) ("flybot-deploy-" + [guid]::NewGuid().ToString("N"))
$remoteStage = $null

$remoteScript = @'
set -eu

remote_stage="$1"
case "$remote_stage" in
  /tmp/flybot-deploy-*) ;;
  *) echo "refusing unsafe staging path" >&2; exit 1 ;;
esac

cleanup() {
  case "$remote_stage" in
    /tmp/flybot-deploy-*) rm -rf -- "$remote_stage" ;;
  esac
}
trap cleanup EXIT

secret_file=/etc/flytest/flybot.env
if [ ! -f "$secret_file" ]; then
  echo "missing $secret_file" >&2
  exit 1
fi
secret_mode=$(stat -c '%a' "$secret_file")
if [ "$secret_mode" != "600" ]; then
  echo "$secret_file must be mode 600" >&2
  exit 1
fi
grep -Eq '^FLYTEST_DISCORD_BOT_TOKEN=[^[:space:]].*$' "$secret_file"
grep -Eq '^FLYTEST_DISCORD_CHANNEL_ID=[^[:space:]].*$' "$secret_file"

if ! id -u flybot >/dev/null 2>&1; then
  useradd --system --user-group --home-dir /var/lib/flytest-discord --no-create-home --shell /usr/sbin/nologin flybot
fi

install -d -o root -g root -m 755 /opt/flytest-discord
install -d -o root -g root -m 755 /opt/flytest-discord/src
install -d -o root -g root -m 755 /opt/flytest-discord/src/flytest
install -d -o flybot -g flybot -m 750 /var/lib/flytest-discord

install -o root -g root -m 644 "$remote_stage/__init__.py" /opt/flytest-discord/src/flytest/__init__.py
install -o root -g root -m 644 "$remote_stage/discord_bridge.py" /opt/flytest-discord/src/flytest/discord_bridge.py
install -o root -g root -m 644 "$remote_stage/flybot.service" /etc/systemd/system/flybot.service

systemctl daemon-reload
systemctl enable flybot.service >/dev/null 2>&1
systemctl restart flybot.service
systemctl is-enabled flybot.service
systemctl is-active flybot.service
'@

function Invoke-SshBashScript {
    param(
        [string]$TargetHost,
        [string]$RemoteStage,
        [string]$Script
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = (Get-Command ssh.exe -CommandType Application -ErrorAction Stop).Source
    $startInfo.Arguments = "-o BatchMode=yes `"$TargetHost`" `"bash -s -- '$RemoteStage'`""
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    if (-not $process.Start()) {
        throw "Could not start ssh for $TargetHost"
    }

    try {
        $encoding = [System.Text.UTF8Encoding]::new($false)
        $bytes = $encoding.GetBytes($Script)
        $process.StandardInput.BaseStream.Write($bytes, 0, $bytes.Length)
        $process.StandardInput.Close()
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        $exitCode = $process.ExitCode
    }
    finally {
        $process.Dispose()
    }

    if ($exitCode -ne 0) {
        if ($stderr.Trim()) {
            throw $stderr.Trim()
        }
        throw "Remote FlyBot deployment failed on $TargetHost"
    }
    if ($stdout.Trim()) {
        Write-Output $stdout.TrimEnd()
    }
}

try {
    New-Item -ItemType Directory -Path $localStage -Force | Out-Null
    foreach ($source in $sources) {
        Copy-Item -LiteralPath $source.Local -Destination (Join-Path $localStage $source.RemoteName)
    }

    $remoteStage = (& ssh -o BatchMode=yes $HostAlias "umask 077; mktemp -d /tmp/flybot-deploy-XXXXXX" 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $remoteStage -notmatch '^/tmp/flybot-deploy-[A-Za-z0-9]+$') {
        throw "Could not create a safe remote staging directory on $HostAlias"
    }

    foreach ($source in $sources) {
        $stagedPath = Join-Path $localStage $source.RemoteName
        $remotePath = "${HostAlias}:$remoteStage/$($source.RemoteName)"
        & scp -o BatchMode=yes -- $stagedPath $remotePath
        if ($LASTEXITCODE -ne 0) {
            throw "Could not copy $($source.RemoteName) to $HostAlias"
        }
    }

    $remoteScript = $remoteScript -replace "`r`n", "`n"
    Invoke-SshBashScript -TargetHost $HostAlias -RemoteStage $remoteStage -Script $remoteScript
}
finally {
    if ($localStage -and (Test-Path -LiteralPath $localStage)) {
        Remove-Item -LiteralPath $localStage -Recurse -Force
    }
}
