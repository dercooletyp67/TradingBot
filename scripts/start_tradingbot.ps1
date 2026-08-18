# Starts the paper trader + dashboard, hidden, with output redirected to logs/.
# Edit the strategy/params/instrument in $traderArgs below to change what
# it auto-starts with. Called by the "TradingBotAutoStart" scheduled task
# (see scripts/README.md), or run it directly any time to start manually.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$venvPython = Join-Path $root "venv\Scripts\python.exe"
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$pidFile = Join-Path $root "scripts\tradingbot.pids"
if (Test-Path $pidFile) { Remove-Item $pidFile }

# --- Paper trader: no broker account, real Yahoo Finance prices, fake money.
# Seed picked by running run_optimize.py --strategy all on 2026-08-17
# (rsi_reversion topped out-of-sample Sharpe 2.12 with a negative overfit
# gap -- rerun the optimizer yourself and update this if it's gone stale).
# Re-tunes itself every 6h across all strategies from here on. ---
$traderArgs = @(
    "run_paper_trader.py",
    "--strategy", "rsi_reversion",
    "--params", "period=21,oversold=20,overbought=80",
    "--instrument", "EUR_USD",
    "--granularity", "H1",
    "--poll-seconds", "60",
    "--auto-retune-hours", "6",
    "--position-sizing", "volatility",
    "--risk-pct", "0.01"
)
$traderProc = Start-Process -FilePath $venvPython -ArgumentList $traderArgs -WorkingDirectory $root `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logDir "paper_trader.log") `
    -RedirectStandardError (Join-Path $logDir "paper_trader.err.log")

# --- Dashboard, http://localhost:8000 ---
$dashArgs = @("-m", "uvicorn", "dashboard.server:app", "--port", "8000")
$dashProc = Start-Process -FilePath $venvPython -ArgumentList $dashArgs -WorkingDirectory $root `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logDir "dashboard.log") `
    -RedirectStandardError (Join-Path $logDir "dashboard.err.log")

"$($traderProc.Id)`n$($dashProc.Id)" | Set-Content $pidFile
