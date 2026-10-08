$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
Write-Host 'TradingBot setup: installs dependencies only. No bot or orders are started.'
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is missing. Install Git for Windows, then rerun.' }
git --version
if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Python launcher is missing. Install Python 3.12 x64, then rerun.' }
py -3.12 -c "import sys,struct; assert sys.version_info[:2] == (3,12); assert struct.calcsize('P') == 8; print(sys.version)"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 x64 is required.' }
$terminals = @(Get-ChildItem "$env:ProgramFiles\*\terminal64.exe" -ErrorAction SilentlyContinue)
$pepperstone = @($terminals | Where-Object { $_.FullName -match 'Pepperstone' })
if ($pepperstone.Count -eq 0) { Write-Warning 'Pepperstone MT5 not detected in Program Files. Check the installation and MT5_TERMINAL_PATH.' }
else { $pepperstone | ForEach-Object { Write-Host "MT5 candidate: $($_.FullName)" } }
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
& .\.venv\Scripts\python.exe -m pip install -r services/mt5-engine/requirements-windows.lock pytest==9.1.1
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& .\.venv\Scripts\python.exe -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency conflict.' }
& .\.venv\Scripts\python.exe -c "import MetaTrader5,supabase,dotenv,pydantic; print('MT5 Python:',MetaTrader5.__version__); print('Dependency imports OK')"
if ($LASTEXITCODE -ne 0) { throw 'Dependency import failed.' }
& .\.venv\Scripts\python.exe -m pytest services/agent_team services/decision-engine services/mt5-engine -q
if ($LASTEXITCODE -ne 0) { throw 'Safety/core tests failed.' }
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
Write-Host 'Setup checks complete. Configure .env locally; never share passwords or service keys in chat.'
Write-Host 'No MT5 login, telemetry loop, task scheduler or order execution has been started.'
