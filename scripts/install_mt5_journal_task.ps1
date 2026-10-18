# Run in an ordinary PowerShell in TradingBot-Test; no admin privileges needed.
$ErrorActionPreference = 'Stop'
$taskName = 'TradingBot MT5 Journal Sync'
$runner = Join-Path $PSScriptRoot 'run_mt5_journal_sync.ps1'
if (-not (Test-Path $runner)) { throw 'Journal runner script not found' }
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    throw "Task already exists: $taskName. Not overwriting it."
}
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $runner + '"')
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -StartWhenAvailable
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Hourly read-only MT5 historical deals upsert to private Supabase journal; only while signed in.' | Out-Null
Write-Host "Created: $taskName (hourly while signed in)."
Write-Host "Check: Get-ScheduledTask -TaskName '$taskName' | Get-ScheduledTaskInfo"
Write-Host "Logs: $env:LOCALAPPDATA\TradingBot\journal-logs"
