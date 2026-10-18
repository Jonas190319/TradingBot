# Read-only MT5 history sync. Requires an open MT5 terminal and logged-in Windows user.
$ErrorActionPreference = 'Stop'
$python = 'C:\Users\Jonas\TradingBot\.venv\Scripts\python.exe'
$importer = 'C:\Users\Jonas\TradingBot-Test\services\mt5-engine\import_mt5_history.py'
$envFile = 'C:\Users\Jonas\TradingBot\.env'
$logDir = Join-Path $env:LOCALAPPDATA 'TradingBot\journal-logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ('mt5-journal-' + (Get-Date -Format 'yyyy-MM-dd') + '.log')
$timestamp = (Get-Date).ToString('s')
try {
    if (-not (Test-Path $python) -or -not (Test-Path $importer) -or -not (Test-Path $envFile)) {
        throw 'Required local Python, importer, or .env file is missing'
    }
    # Use the existing read-only importer. No order_send or broker modifications.
    $output = & $python $importer --days 90 --env-file $envFile --commit 2>&1
    $code = $LASTEXITCODE
    Add-Content -Path $log -Value ("[$timestamp] ExitCode=$code")
    $output | ForEach-Object { Add-Content -Path $log -Value ([string]$_) }
    if ($code -ne 0) { exit $code }
} catch {
    Add-Content -Path $log -Value ("[$timestamp] Import failed: " + $_.Exception.Message)
    exit 1
}
# Keep logs for 30 days.
Get-ChildItem $logDir -Filter 'mt5-journal-*.log' -File |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -Force
