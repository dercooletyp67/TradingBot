# BTC-USD instance -- a fully separate bot from start_tradingbot.ps1
# (EUR/USD): own state files, own dashboard port (8001), own PID/log files.
# See scripts/README.md.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$venvPython = Join-Path $root "venv\Scripts\python.exe"
$logDir = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$pidFile = Join-Path $root "scripts\tradingbot_btc.pids"
if (Test-Path $pidFile) { Remove-Item $pidFile }

# Keeps this instance's DB/learn files separate from the EUR/USD local
# instance's -- inherited by both child processes started below.
$env:TRADINGBOT_DB_PATH = "storage/btc_tradingbot.db"
$env:TRADINGBOT_LEARN_DIR = "learn_btc"

# --- Paper trader: no broker account, real Yahoo Finance prices, fake money.
# Seed picked by running run_optimize.py --instrument BTC-USD on 2026-08-24
# (rsi_reversion, period=7/oversold=25/overbought=80 topped out-of-sample
# Sharpe 1.89 with a small overfit gap -- rerun the optimizer yourself and
# update this if it's gone stale). Re-tunes itself every 6h from here on. ---
$traderArgs = @(
    "run_paper_trader.py",
    "--strategy", "rsi_reversion",
    "--params", "period=7,oversold=25,overbought=80",
    "--instrument", "BTC-USD",
    "--granularity", "H1",
    "--poll-seconds", "60",
    "--auto-retune-hours", "6",
    "--position-sizing", "volatility",
    "--risk-pct", "0.01",
    "--max-drawdown-pct", "25"
)
$traderProc = Start-Process -FilePath $venvPython -ArgumentList $traderArgs -WorkingDirectory $root `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logDir "paper_trader_btc.log") `
    -RedirectStandardError (Join-Path $logDir "paper_trader_btc.err.log")

# --- Dashboard, http://localhost:8001 ---
$dashArgs = @("-m", "uvicorn", "dashboard.server:app", "--port", "8001")
$dashProc = Start-Process -FilePath $venvPython -ArgumentList $dashArgs -WorkingDirectory $root `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logDir "dashboard_btc.log") `
    -RedirectStandardError (Join-Path $logDir "dashboard_btc.err.log")

"$($traderProc.Id)`n$($dashProc.Id)" | Set-Content $pidFile
