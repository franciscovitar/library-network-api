# Docker Desktop on Windows: "dockerInference" / "userAnalyticsOtlpHttp.sock" crash

Environment where this was diagnosed (2026-11-18): Windows 11 Home 26200, Docker Desktop
**4.51.0** (engine 28.5.2, Compose v2.40.3), WSL 2.6.1 with the `docker-desktop` distribution.

## Symptom

Docker Desktop shows "An unexpected error occurred" and closes. `docker info` fails with
`open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified`.
`%LOCALAPPDATA%\Docker\backend.error.json` says:

```
starting services: initializing Inference manager: listening on
unix://C:\Users\<user>\AppData\Local\Docker\run\dockerInference: remove
...\run\dockerInference: The file cannot be accessed by the system.
```

## Cause (what was observed)

- Docker Desktop creates AF_UNIX socket files (zero-byte reparse points) in
  `%LOCALAPPDATA%\Docker\run`: `dockerInference` (Docker AI / Model Runner, enabled by
  `"EnableDockerAI": true` in `%APPDATA%\Docker\settings-store.json`) and
  `userAnalyticsOtlpHttp.sock`.
- After an abrupt backend exit (the backend log shows `panic` traces on 2026-11-01/02) they stay
  on disk. On the next start Docker tries to `remove` the old socket, Windows returns
  error 1920 ("cannot be accessed by the system") and the backend aborts.
- Those files can not be deleted, renamed or inspected (`fsutil reparsepoint query` also fails)
  from PowerShell/Explorer. **Their parent folder can be renamed.** The folder
  `%LOCALAPPDATA%\Docker` contains `run.b6-backup-20260827-103847`, `run.tp6-backup-2` and
  `run.tp6-backup-20261101`: the same fix had been applied by hand at least three times.
- Root cause of *why* the backend exits abruptly was not established; the stale-socket handling
  on Windows is a Docker Desktop defect or limitation. Not verified whether a newer Docker
  Desktop release fixes it.

## Update 2026-11-18 (second recurrence): same defect, more sockets

The same session reproduced the crash **twice more**, which showed the problem is general:

- Docker Desktop had exited without a clean shutdown (backend log ends mid-traffic, no shutdown
  entry) and left sockets from 17:26 in **two** places: `%LOCALAPPDATA%\Docker\run`
  (`dockerInference`, `userAnalyticsOtlpHttp.sock`) **and** `%LOCALAPPDATA%\docker-secrets-engine`
  (`engine.sock`). A start with stale sockets failed on `dockerInference`; after renaming only `run`
  it failed again on `docker-secrets-engine\engine.sock`.
- `docker info` can **hang** (not fail) while Docker Desktop is half-dead, so scripts must put a
  timeout on it.
- A normal start does **not** always need repair: repair is only needed when the stale-socket
  error appears. Renaming on every start is therefore not done.

## Fix applied (non-destructive, reversible)

1. Confirmed no Docker engine was running (the crashed GUI/backend processes were closed).
2. Renamed `%LOCALAPPDATA%\Docker\run` and `%LOCALAPPDATA%\docker-secrets-engine` (each held only
   socket files) to `<name>.stale-<timestamp>`. Nothing was deleted.
3. Started Docker Desktop; it recreated both folders and the engine came up
   (`docker info` -> server 28.5.2, `docker compose version` -> v2.40.3).

Not modified: volumes, images, containers, WSL distributions, Docker settings.

To revert: quit Docker Desktop, rename the freshly created folder away, rename the `*.stale-*`
folder back. (That restores the crashing state; only useful for inspection.)

## The helper script

[`scripts/windows/start-docker-desktop.ps1`](../scripts/windows/start-docker-desktop.ps1)

| Situation | Default run (no switch) | With `-RepairStaleSockets` |
|---|---|---|
| Docker running and responding | does nothing, exit 0 | does nothing, exit 0 |
| Docker not running | **normal start**, waits for `docker info`, exit 0; no renaming | renames the socket folders first, then starts |
| Start fails with the stale-socket error | stops waiting, explains, changes nothing, **exit 2** | n/a (repair already done) |
| Docker open but crashed on stale sockets | detects it, changes nothing, **exit 2** | refuses while Docker processes exist: quit the error dialog first |
| Socket folder holds a non-socket file | n/a | leaves that folder untouched |

Only the two known folders can ever be renamed, only when they contain nothing but socket files, and
never deleted. `-WhatIf` previews.

```powershell
.\scripts\windows\start-docker-desktop.ps1                       # normal start
.\scripts\windows\start-docker-desktop.ps1 -RepairStaleSockets   # after exit code 2 (Docker closed)
```

Verified on this machine: detector against real and fabricated error files; "already running"
(exit 0); detection of the crashed state (exit 2, nothing changed, 9 s); repair of both folders
followed by a successful engine start. Bugs found and fixed while testing it: `docker info` hanging,
`ExitCode` being `$null` under Windows PowerShell 5.1 without touching `Process.Handle`, and stderr
becoming a terminating error under `$ErrorActionPreference = 'Stop'`. Not exercised: a normal start
of a *healthy* Docker from a cold state with no stale sockets.

Prevention: quit Docker Desktop from its tray menu before shutting down; avoid force-killing
`com.docker.backend`. Old `run.*` / `*.stale-*` folders are tiny; delete them manually only while
Docker is stopped, if at all.

## Options NOT applied (need the owner's decision)

- Disable Docker AI (`EnableDockerAI` -> false in Docker Desktop settings): would stop creating
  `dockerInference`, but not the other sockets, and changes a feature setting.
- Update Docker Desktop (4.51.0): a download/installation; might fix the defect, unverified.
