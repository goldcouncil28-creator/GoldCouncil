# Gold Council — create Scheduled Tasks on Narmer (PREP ONLY, DO NOT RUN UNTIL CUTOVER)
#
# Creates the three live tasks + the n8n task, ALL DISABLED. Enabling any of
# them starts live Telegram polling / cycles from Narmer — that must happen
# ONLY at cutover, on Mohamed's separate explicit «نفذ», after the 1-week
# uptime observation, and after the VM crons are switched off. Enabling the
# Poll task while the VM bot is live would duplicate Telegram polling.
#
# LAYOUT NOTE (2026-11-12): the actual Narmer build uses D:\Project\Trade\system\
# (code) and D:\Project\Trade\system\venv — NOT the app\/ + root venv layout in
# design/D-Project-Trade-structure.md. The commands below use the ACTUAL paths.
#
# Run from an elevated PowerShell on Narmer:
#   powershell -ExecutionPolicy Bypass -File D:\Project\Trade\scripts\create-tasks.ps1
# Then verify: Get-ScheduledTask GoldCouncil-* | Select TaskName, State
# Expected: all four show State = Disabled.

# Repetition duration is 10 years (New-TimeSpan -Days 3650), NOT
# [TimeSpan]::MaxValue — Task Scheduler rejects MaxValue's
# P99999999DT23H59M59S as out of range (seen 2026-11-12). Re-run this
# script in 2036 if the tasks are still wanted.
$ErrorActionPreference = 'Stop'

$Python = 'D:\Project\Trade\system\venv\Scripts\python.exe'
$System = 'D:\Project\Trade\system'

function New-DisabledTask {
    param([string]$Name, [string]$Description, [Microsoft.Management.Infrastructure.CimInstance]$Action, [Microsoft.Management.Infrastructure.CimInstance[]]$Triggers)
    $existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($null -ne $existing) {
        # Idempotent re-run: never fail on an existing task; keep it Disabled.
        Disable-ScheduledTask -TaskName $Name | Out-Null
        Write-Output "exists, left Disabled: $Name"
        return
    }
    $settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable
    Register-ScheduledTask -TaskName $Name -Description $Description -Action $Action -Trigger $Triggers -Settings $settings | Out-Null
    Disable-ScheduledTask -TaskName $Name | Out-Null
    Write-Output "created (Disabled): $Name"
}

# 1. Poll — every 2 minutes (replaces VM cron trading-bot-poll)
$pollAction = New-ScheduledTaskAction -Execute $Python -Argument "$System\telegram_bot\poll.py" -WorkingDirectory $System
$pollTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 2) -RepetitionDuration (New-TimeSpan -Days 3650)
New-DisabledTask -Name 'GoldCouncil-Poll' -Description 'Gold Council Telegram poll (2 min). DISABLED until cutover.' -Action $pollAction -Triggers @($pollTrigger)

# 2. Cycle — hourly on the hour (replaces VM cron trading-bot-cycle)
# NOTE: -Daily cannot take -RepetitionInterval (ambiguous parameter set);
# -Once at the next hour boundary + hourly repetition is equivalent.
$nextHour = (Get-Date).Date.AddHours((Get-Date).Hour + 1)
$cycleAction = New-ScheduledTaskAction -Execute $Python -Argument "$System\telegram_bot\cycle.py" -WorkingDirectory $System
$cycleTrigger = New-ScheduledTaskTrigger -Once -At $nextHour -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
New-DisabledTask -Name 'GoldCouncil-Cycle' -Description 'Gold Council signal cycle (hourly). DISABLED until cutover.' -Action $cycleAction -Triggers @($cycleTrigger)

# 3. n8n — at logon (fixes the fragile session-0 launch; replaces manual start)
$n8nAction = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c "C:\Users\ayc\AppData\Roaming\npm\n8n.cmd" start' -WorkingDirectory 'C:\Users\ayc'
$n8nTrigger = New-ScheduledTaskTrigger -AtLogOn
New-DisabledTask -Name 'GoldCouncil-N8N' -Description 'n8n 2.47.3 for Gold Council. DISABLED until cutover.' -Action $n8nAction -Triggers @($n8nTrigger)

# 4. Watchdog — every 15 minutes (replaces VM cron trading-dashboard-watchdog)
$watchAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -ExecutionPolicy Bypass -File D:\Project\Trade\scripts\check-health.ps1' -WorkingDirectory 'D:\Project\Trade'
$watchTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(15) -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 3650)
New-DisabledTask -Name 'GoldCouncil-Watchdog' -Description 'Gold Council health check (15 min). DISABLED until cutover.' -Action $watchAction -Triggers @($watchTrigger)

Write-Output 'Done. All tasks are Disabled. Do NOT enable them before cutover.'
