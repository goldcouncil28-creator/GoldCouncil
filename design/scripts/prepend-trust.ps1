# One-time trust-window prepend (Gold Council Phase B, 2026-11-12).
# Used ONCE for the approved temporary localhost trust window; do NOT re-run
# without Mohamed's explicit approval. The restore (copy back the
# pg_hba.conf.bak-20261112-* backup) is done by the operator, not this script.
$ErrorActionPreference = 'Stop'
$p = 'C:\Users\ayc\pgsql-data\pg_hba.conf'
$c = Get-Content $p -Raw -Encoding ascii
$nl = [char]13 + [char]10
$trust = 'host all postgres 127.0.0.1/32 trust' + $nl + 'host all postgres ::1/128 trust' + $nl
if ($c.StartsWith('host all postgres 127.0.0.1/32 trust')) {
    Write-Output 'already-prepended'
    exit 0
}
Set-Content $p -Value ($trust + $c) -Encoding ascii -NoNewline
Write-Output 'prepended'
Get-Content $p -TotalCount 3
