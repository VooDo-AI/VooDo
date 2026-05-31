# Windows-side one-shot launcher for voodo. Idempotent.
#
# The executor opens a WebSocket OUT to the backend's /executor endpoint.
# No inbound ports are required on this machine.
#
# Usage (run from the `client/` directory):
#   .\scripts\dev_all.ps1 -Backend ws://<backend-host>:7860 -Token "the-shared-token"
#
# Token defaults to EXECUTOR_TOKEN in a co-located .env if present.
# Backend defaults to BACKEND_WS_URL in .env, then ws://localhost:7860.

param(
    [string]$Backend = "",
    [string]$Token = "",
    [switch]$NoAssistant,  # skip auto-launching the floating robot on first message
    [switch]$NoBrowser     # skip auto-opening the chat UI in the default browser
)

$ErrorActionPreference = "Stop"
# cwd = client/. Repo root is one level up.
Set-Location (Join-Path $PSScriptRoot "..")
$RepoRoot = (Resolve-Path "..").Path

function Log($msg) { Write-Host "[dev_all] $msg" -ForegroundColor Cyan }
function Ok($msg)  { Write-Host "[dev_all] $msg" -ForegroundColor Green }

# --- 0. Defaults from repo-root .env ---
$EnvFile = Join-Path $RepoRoot ".env"
if ((-not $Token -or -not $Backend) -and (Test-Path $EnvFile)) {
    Get-Content $EnvFile | ForEach-Object {
        if (-not $Token -and $_ -match '^EXECUTOR_TOKEN=(.+)$') {
            $Token = $matches[1].Trim()
        }
        if (-not $Backend -and $_ -match '^BACKEND_WS_URL=(.+)$') {
            $Backend = $matches[1].Trim()
        }
    }
}
if (-not $Backend) { $Backend = "ws://localhost:7860" }

if ($Token) {
    Ok "using EXECUTOR_TOKEN ($($Token.Length) chars)"
} else {
    Log "no EXECUTOR_TOKEN set - backend will accept unauthenticated"
}
Ok "backend: $Backend"

# --- 1. venv ---
if (-not (Test-Path .venv)) {
    Log "creating venv at .venv (first run)"
    py -m venv .venv
    .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip wheel
}

# Re-install only if requirements file is newer than the stamp.
$stamp = ".venv\.deps-installed"
$reqs = "executor\requirements.txt"
$needsInstall = (-not (Test-Path $stamp)) -or `
                ((Get-Item $reqs).LastWriteTime -gt (Get-Item $stamp).LastWriteTime)
if ($needsInstall) {
    Log "installing executor deps"
    .\.venv\Scripts\pip.exe install --quiet -r $reqs
    New-Item -ItemType File -Path $stamp -Force | Out-Null
    Ok "deps installed"
} else {
    Ok "deps up to date"
}

# --- 2. Open the chat UI in the default browser ---
# ws://host:port -> http://host:port. The executor will spawn the floating
# assistant AFTER the user sends their first message (see client/executor/main.py).
if (-not $NoBrowser) {
    if     ($Backend -like 'wss://*') { $http = $Backend -replace '^wss://', 'https://' }
    elseif ($Backend -like 'ws://*')  { $http = $Backend -replace '^ws://',  'http://'  }
    else                              { $http = $Backend }
    # Launch the chat UI in the browser. It will restore the last active chat.
    $url = "$http/"
    Ok "opening chat UI: $url"
    Start-Process $url
}

# --- 3. Start the executor (long-lived, auto-reconnects) ---
# PYTHONPATH covers both client/ (so `executor.*` resolves) and the repo
# root (so `shared.*` resolves) — the executor imports both.
$env:PYTHONPATH = "$RepoRoot;$((Get-Location).Path)"
$env:EXECUTOR_TOKEN = $Token
$env:BACKEND_WS_URL = $Backend
# The executor reads this to decide whether to spawn the floating assistant
# on the first tool call it receives (i.e. after the user sends their first
# message). Pass -NoAssistant to disable.
if ($NoAssistant) { $env:VOODO_AUTOLAUNCH_ASSISTANT = "0" }
else              { $env:VOODO_AUTOLAUNCH_ASSISTANT = "1" }

Ok "starting voodo executor (Ctrl-C to stop)"
.\.venv\Scripts\python.exe -m executor.main --backend $Backend --token $Token
