# trust-open.ps1 — prepend localhost-only trust lines for user postgres.
# Used ONCE for the Phase D/E live-DB verification window (2026-11-12).
# The backup (pg_hba.conf.bak-verify) is made BEFORE this runs; the restore
# is a plain file copy back + reload. Trust lines are localhost-only,
# postgres user only — never wider.
$ErrorActionPreference = 'Stop'
$Path = 'C:\Users\ayc\pgsql-data\pg_hba.conf'
$Lines = @(
    'host all postgres 127.0.0.1/32 trust',
    'host all postgres ::1/128 trust'
)
$Content = Get-Content -Path $Path -Encoding Ascii
if ($Content -contains $Lines[0]) {
    Write-Output 'trust lines already present — not duplicating'
} else {
    Set-Content -Path $Path -Value ($Lines + $Content) -Encoding Ascii
    Write-Output 'trust lines prepended'
}
Get-Content -Path $Path -TotalCount 5
