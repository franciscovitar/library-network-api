<#
.SYNOPSIS
  Starts Docker Desktop on Windows, first moving aside stale socket files that make it crash.

.DESCRIPTION
  Docker Desktop (verified on 4.51.0) creates AF_UNIX socket files such as `dockerInference`
  and `userAnalyticsOtlpHttp.sock` in %LOCALAPPDATA%\Docker\run. If the backend dies
  abruptly they are left behind, and the next start aborts with:
    "listening on unix://...\run\dockerInference: remove ...: The file cannot be accessed
     by the system."
  Individual stale socket files cannot be removed or renamed, but their parent folder can
  be renamed.

  This script is deliberately conservative:
    * If Docker Desktop is already running it changes NOTHING.
    * If it is not running and `run` is non-empty, it RENAMES `run` to
      `run.stale-<timestamp>`. It never deletes anything; Docker recreates `run` itself.
    * It never touches volumes, images, containers, WSL distributions or settings.

  To revert: close Docker Desktop and rename the folder back (see docs/windows-docker-desktop.md).

.EXAMPLE
  .\scripts\windows\start-docker-desktop.ps1 -WhatIf   # show what would happen
  .\scripts\windows\start-docker-desktop.ps1           # do it
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = 'Stop'

$exe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
$runDir = Join-Path $env:LOCALAPPDATA 'Docker\run'

if (-not (Test-Path -LiteralPath $exe)) {
    Write-Error "Docker Desktop not found at: $exe"
}

function Test-DockerResponds {
    docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

$running = Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -in 'Docker Desktop', 'com.docker.backend' }

if ($running) {
    if (Test-DockerResponds) {
        Write-Host 'Docker Desktop is already running and responding. Nothing changed.'
        exit 0
    }
    Write-Warning ('Docker Desktop processes exist but the engine does not respond. ' +
        'Not touching anything: finish starting, or quit it from its tray icon, then retry.')
    exit 1
}

if ((Test-Path -LiteralPath $runDir) -and (Get-ChildItem -LiteralPath $runDir -Force | Select-Object -First 1)) {
    $target = 'run.stale-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
    if ($PSCmdlet.ShouldProcess($runDir, "Rename to '$target' (no deletion)")) {
        Rename-Item -LiteralPath $runDir -NewName $target
        Write-Host "Moved stale '$runDir' to '$target'."
    }
}

if ($PSCmdlet.ShouldProcess($exe, 'Start Docker Desktop')) {
    Start-Process -FilePath $exe
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
        if (Test-DockerResponds) {
            Write-Host 'Docker is ready.'
            exit 0
        }
    }
    Write-Error "Docker did not respond within $TimeoutSeconds s. See %LOCALAPPDATA%\Docker\backend.error.json"
}
