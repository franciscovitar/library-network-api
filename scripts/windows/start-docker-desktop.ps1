<#
.SYNOPSIS
  Starts Docker Desktop on Windows; can optionally move aside stale socket files that crash it.

.DESCRIPTION
  Docker Desktop (verified on 4.51.0) creates AF_UNIX socket files in
  %LOCALAPPDATA%\Docker\run (`dockerInference`, `userAnalyticsOtlpHttp.sock`) and in
  %LOCALAPPDATA%\docker-secrets-engine (`engine.sock`). If the backend dies abruptly they are
  left behind, and a later start can abort with:
    "listening on unix://...\dockerInference: remove ...: The file cannot be accessed
     by the system."
  Individual stale socket files cannot be removed or renamed, but their parent folder can
  be renamed.

  Default behaviour (no switches) is a NORMAL start and changes nothing on disk:
    * Docker already running and responding -> does nothing, exit 0.
    * Docker not running -> starts it and waits for `docker info`, exit 0 when ready.
    * If startup fails with the stale-socket signature in backend.error.json, it stops
      waiting immediately, explains what to do, and exits 2. It does NOT rename anything.

  Only with -RepairStaleSockets (explicit opt-in) and only while Docker is NOT running does it
  RENAME the known socket folders (`Docker\run`, `docker-secrets-engine`) to
  `<name>.stale-<timestamp>` before starting, and only if a folder holds nothing but socket
  files. It never deletes anything; Docker recreates the folders itself. Nothing else is
  touched: no volumes, images, containers, WSL distributions or settings.

  To revert a repair: quit Docker Desktop and rename the folder back (docs/windows-docker-desktop.md).

.EXAMPLE
  .\scripts\windows\start-docker-desktop.ps1                          # normal start
  .\scripts\windows\start-docker-desktop.ps1 -RepairStaleSockets      # after exit code 2
  .\scripts\windows\start-docker-desktop.ps1 -RepairStaleSockets -WhatIf
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [int]$TimeoutSeconds = 180,
    [switch]$RepairStaleSockets
)

$ErrorActionPreference = 'Stop'

$exe = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
$dockerDir = Join-Path $env:LOCALAPPDATA 'Docker'
$runDir = Join-Path $dockerDir 'run'
$errorFile = Join-Path $dockerDir 'backend.error.json'
# The ONLY folders the repair may rename (each is recreated by Docker Desktop).
$socketDirs = @($runDir, (Join-Path $env:LOCALAPPDATA 'docker-secrets-engine'))

function Test-DockerResponds {
    # `docker info` can HANG (not fail) while Docker Desktop is half-dead, so run it as a child
    # process with a hard timeout instead of calling it inline. Start-Process needs files to
    # redirect into; they are created in a private temp folder that is ALWAYS removed again
    # (success, failure or timeout), so repeated polling leaves nothing behind in %TEMP%.
    param([int]$TimeoutMs = 8000)
    $scratch = Join-Path ([IO.Path]::GetTempPath()) ('docker-probe-' + [Guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $scratch
    $p = $null
    try {
        $p = Start-Process -FilePath 'docker' -ArgumentList 'info', '--format', '{{.ServerVersion}}' `
            -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $scratch 'out.txt') `
            -RedirectStandardError (Join-Path $scratch 'err.txt')
        $null = $p.Handle  # PS 5.1: without touching Handle, ExitCode can come back $null
        if (-not $p.WaitForExit($TimeoutMs)) {
            try { $p.Kill(); $null = $p.WaitForExit(2000) } catch { }
            return $false
        }
        return ($p.ExitCode -eq 0)
    }
    finally {
        if ($p) { $p.Dispose() }
        # Only ever removes the folder created above (unique GUID name inside the temp path).
        Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Test-StaleSocketFailure {
    # True when backend.error.json was written at/after $Since and shows the stale-socket error.
    param([string]$Path, [datetime]$Since)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    if ((Get-Item -LiteralPath $Path).LastWriteTime -lt $Since) { return $false }
    $raw = Get-Content -LiteralPath $Path -Raw
    return ($raw -match 'cannot be accessed by the system') -and ($raw -match 'listening on unix://')
}

function Test-OnlySocketFiles {
    # True when the folder holds only AF_UNIX socket files (reparse points): leftovers, no data.
    param([string]$Path)
    $items = @(Get-ChildItem -LiteralPath $Path -Force -Recurse -ErrorAction SilentlyContinue)
    if ($items.Count -eq 0) { return $true }
    foreach ($i in $items) {
        if ($i.PSIsContainer -or -not ($i.Attributes -band [IO.FileAttributes]::ReparsePoint)) { return $false }
    }
    return $true
}

# Allow dot-sourcing the functions (used by the checks in docs) without executing the script.
if ($MyInvocation.InvocationName -eq '.') { return }

if (-not (Test-Path -LiteralPath $exe)) {
    Write-Error "Docker Desktop not found at: $exe"
}

$running = Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -in 'Docker Desktop', 'com.docker.backend' }

if ($running) {
    if (Test-DockerResponds) {
        Write-Host 'Docker Desktop is already running and responding. Nothing changed.'
        exit 0
    }
    $since = ($running | Sort-Object StartTime | Select-Object -First 1).StartTime.AddSeconds(-5)
    if (Test-StaleSocketFailure -Path $errorFile -Since $since) {
        Write-Warning ('Docker Desktop is open but failed on stale socket files (see ' + $errorFile + '). ' +
            'Nothing was changed. Click Quit on its error dialog, then run: ' +
            '.\scripts\windows\start-docker-desktop.ps1 -RepairStaleSockets  ' +
            '(renames the folder, never deletes).')
        exit 2
    }
    Write-Warning ('Docker Desktop processes exist but the engine does not respond. ' +
        'Not touching anything: wait for it to finish starting, or quit it (close any error ' +
        'dialog / tray icon > Quit), then run this script again.')
    exit 1
}

if ($RepairStaleSockets) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    foreach ($dir in $socketDirs) {
        if (-not ((Test-Path -LiteralPath $dir) -and (Get-ChildItem -LiteralPath $dir -Force | Select-Object -First 1))) {
            Write-Host "'$dir' is missing or empty: nothing to repair."
            continue
        }
        if (-not (Test-OnlySocketFiles -Path $dir)) {
            Write-Warning "'$dir' contains files other than sockets; leaving it untouched."
            continue
        }
        $target = (Split-Path -Leaf $dir) + '.stale-' + $stamp
        if ($PSCmdlet.ShouldProcess($dir, "Rename to '$target' (no deletion)")) {
            Rename-Item -LiteralPath $dir -NewName $target
            Write-Host "Moved stale '$dir' to '$target'."
        }
    }
}

if ($PSCmdlet.ShouldProcess($exe, 'Start Docker Desktop')) {
    $startedAt = Get-Date
    Start-Process -FilePath $exe
    $deadline = $startedAt.AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
        if (Test-StaleSocketFailure -Path $errorFile -Since $startedAt.AddSeconds(-2)) {
            Write-Warning ('Docker Desktop failed on stale socket files (see ' + $errorFile + '). ' +
                'Nothing was changed. Close the Docker error dialog (Quit), then run: ' +
                '.\scripts\windows\start-docker-desktop.ps1 -RepairStaleSockets  ' +
                '(renames the folder, never deletes).')
            exit 2
        }
        if (Test-DockerResponds) {
            Write-Host 'Docker is ready.'
            exit 0
        }
    }
    Write-Error "Docker did not respond within $TimeoutSeconds s. See $errorFile"
}
