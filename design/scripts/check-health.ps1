# Gold Council — health check for Narmer (PREP ONLY, DO NOT SCHEDULE UNTIL CUTOVER)
#
# Checks Postgres, n8n, and the dashboard; restarts the dashboard ONLY if it
# is down AND already configured (dashboard\.admin-password exists). It never
# starts Telegram polling or signal cycles, never touches the VM, and never
# prints secrets. Intended to be run by the GoldCouncil-Watchdog Scheduled
# Task (every 15 min) after cutover — see scripts\create-tasks.ps1.
#
# Paths use the ACTUAL Narmer layout: D:\Project\Trade\system\ (+ system\venv),
# NOT the app\ + root venv layout in design/D-Project-Trade-structure.md.
#
# Logs to D:\Project\Trade\logs\watchdog.log (created on first run).

$ErrorActionPreference = 'Continue'

$TradeRoot = 'D:\Project\Trade'
$SystemDir = "$TradeRoot\system"
$LogDir = "$TradeRoot\logs"
$LogFile = "$LogDir\watchdog.log"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

function Write-CheckLog {
    param([string]$Message)
    $ts = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Add-Content -Path $LogFile -Value "[$ts] $Message"
}

# 1. Postgres (local, port 5432)
$pgReady = Join-Path 'C:\Program Files\PostgreSQL\17\bin' 'pg_isready.exe'
if (Test-Path $pgReady) {
    & $pgReady -h 127.0.0.1 -p 5432 -q
    if ($LASTEXITCODE -eq 0) { Write-CheckLog 'postgres: accepting connections' }
    else { Write-CheckLog 'postgres: NOT accepting connections (service may be stopped)' }
} else {
    Write-CheckLog 'postgres: pg_isready.exe not found, check skipped'
}

# 2. n8n (http://127.0.0.1:5678/healthz)
try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5678/healthz' -UseBasicParsing -TimeoutSec 10
    Write-CheckLog "n8n: healthz HTTP $($r.StatusCode)"
} catch {
    Write-CheckLog 'n8n: healthz unreachable (process may be down or hung — see GoldCouncil-N8N task)'
}

# 3. Dashboard (http://127.0.0.1:8100/ — expect 307 to /login when healthy)
$dashUp = $false
try {
    $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8100/' -UseBasicParsing -TimeoutSec 10 -MaximumRedirection 0 -ErrorAction Stop
    Write-CheckLog "dashboard: HTTP $($r.StatusCode)"
    $dashUp = $true
} catch {
    $code = $_.Exception.Response.StatusCode.Value__
    if ($code -eq 307) {
        Write-CheckLog 'dashboard: HTTP 307 (healthy, redirects to /login)'
        $dashUp = $true
    } else {
        Write-CheckLog 'dashboard: down or not responding'
    }
}

if (-not $dashUp) {
    $pwFile = Join-Path $SystemDir 'dashboard\.admin-password'
    if (-not (Test-Path $pwFile)) {
        # Dashboard was never configured on Narmer (no admin password yet).
        # Starting it without a password file is pointless — log and stop.
        Write-CheckLog 'dashboard: not configured yet (.admin-password missing) — not starting'
    } else {
        $py = Join-Path $SystemDir 'venv\Scripts\python.exe'
        # NOTE (2026-11-12): uvicorn must run with cwd = $SystemDir, NOT the
        # dashboard dir — `dashboard.app` is only importable from system\
        # (launching from dashboard\ fails with ModuleNotFoundError).
        try {
            Start-Process -FilePath $py -ArgumentList '-m','uvicorn','dashboard.app:app','--host','127.0.0.1','--port','8100' -WorkingDirectory $SystemDir -WindowStyle Hidden
            Write-CheckLog 'dashboard: restart attempted (uvicorn starting)'
        } catch {
            Write-CheckLog "dashboard: restart FAILED: $($_.Exception.Message)"
        }
    }
}

# 4. Scheduled Tasks — last-run info, only if the tasks exist yet
foreach ($name in @('GoldCouncil-Poll', 'GoldCouncil-Cycle', 'GoldCouncil-N8N')) {
    $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($null -eq $t) {
        Write-CheckLog "task ${name}: not created yet"
    } else {
        $info = Get-ScheduledTaskInfo -TaskName $name
        Write-CheckLog "task ${name}: state=$($t.State) lastRun=$($info.LastRunTime) lastResult=$($info.LastTaskResult)"
    }
}

Write-CheckLog 'check complete'
