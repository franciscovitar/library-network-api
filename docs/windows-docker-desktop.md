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

## Fix applied (non-destructive, reversible)

1. Confirmed no Docker process was running.
2. Renamed `%LOCALAPPDATA%\Docker\run` to `run.stale-20261118` (nothing deleted).
3. Started Docker Desktop; it recreated `run` and the engine came up.

Not modified: volumes, images, containers, WSL distributions, Docker settings.

To revert: quit Docker Desktop, delete/rename the freshly created `run` folder, rename
`run.stale-20261118` back to `run`. (Reverting restores the crashing state; it is only useful
for inspection.)

## Making it durable

[`scripts/windows/start-docker-desktop.ps1`](../scripts/windows/start-docker-desktop.ps1) does the
same safe sequence on demand: if Docker is running it changes nothing; if it is not running and
`run` is non-empty it renames `run` to `run.stale-<timestamp>`, then starts Docker Desktop and waits
for `docker info`. It never deletes. Use `-WhatIf` to preview.

```powershell
.\scripts\windows\start-docker-desktop.ps1
```

Prevention: quit Docker Desktop from its tray menu before shutting down or killing processes;
avoid force-killing `com.docker.backend`. Old `run.*` folders accumulate (a few bytes each);
remove them manually if you want, they are safe to delete only while Docker is stopped.

## Options NOT applied (need the owner's decision)

- Disable Docker AI (`EnableDockerAI` -> false in Docker Desktop settings): would stop creating
  `dockerInference`, but does not cover `userAnalyticsOtlpHttp.sock`, and changes a feature setting.
- Update Docker Desktop: a download/installation; might fix the defect, unverified.
