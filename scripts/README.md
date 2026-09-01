# Auto-start scripts

Two fully independent local instances run automatically at login:

| Instrument | Script | Dashboard | PID file |
|---|---|---|---|
| EUR/USD | `start_tradingbot.ps1` | http://localhost:8000 | `tradingbot.pids` |
| BTC-USD | `start_tradingbot_btc.ps1` | http://localhost:8001 | `tradingbot_btc.pids` |

Each seeds a strategy (whatever's currently set near the top of its script,
picked by running `run_optimize.py` for that instrument), then re-tunes
itself every 6h across all strategies. Both run hidden with no console
window, logging to `logs/`. A shortcut in your Startup folder runs each at
login:

```
C:\Users\mrfor\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\TradingBotAutoStart.lnk
C:\Users\mrfor\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\TradingBotBTCAutoStart.lnk
```

They'll be running the next time you sign in. To try either right now
without rebooting:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_tradingbot.ps1
powershell -ExecutionPolicy Bypass -File scripts\start_tradingbot_btc.ps1
```

## Managing them

- **Stop:** `stop_tradingbot.ps1` / `stop_tradingbot_btc.ps1`
- **Turn off auto-start (keeps running if already started):**
  `disable_autostart.ps1` handles the EUR/USD shortcut — for BTC (or to do
  it manually for either), just delete the `.lnk` file from the Startup
  folder above.
- **Change what it trades:** edit the `$traderArgs` block near the top of
  the relevant start script (strategy, params, instrument, retune interval,
  position sizing).
- **Logs:** `logs/paper_trader*.log`, `logs/paper_trader*.err.log`,
  `logs/dashboard*.log`, `logs/dashboard*.err.log` (BTC files have a `_btc`
  suffix).
- **Adding another instrument:** copy `start_tradingbot.ps1` /
  `stop_tradingbot.ps1`, give it its own `TRADINGBOT_DB_PATH` /
  `TRADINGBOT_LEARN_DIR` and dashboard port, and a new Startup shortcut --
  same pattern as the BTC instance.

## Notes

- This uses Startup-folder shortcuts rather than Task Scheduler entries.
  Practically the same result (runs once you log in), but if you'd rather
  have a proper scheduled task (e.g. so it can restart on crash, or run
  before login), you can register one yourself from an ordinary
  (non-sandboxed) PowerShell window:

  ```powershell
  schtasks /Create /TN "TradingBotAutoStart" /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"C:\Users\mrfor\Desktop\TradingBot\scripts\start_tradingbot.ps1`"" /SC ONLOGON /F
  ```

  then delete the Startup shortcut so it doesn't start twice.
- Both instances only trade against the local simulated broker / OANDA demo
  account, never real money, no matter when or how they start.
