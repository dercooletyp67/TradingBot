# Auto-start scripts

The bot is now set to launch automatically the next time you log into
Windows: `start_tradingbot.ps1` starts the paper trader (`sma_cross`,
auto-re-tuning every 6h across all strategies) and the dashboard, both
hidden with no console window, logging to `logs/`. A shortcut in your
Startup folder runs it at login:

```
C:\Users\mrfor\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup\TradingBotAutoStart.lnk
```

It'll be running the next time you sign in. To try it right now without
rebooting:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_tradingbot.ps1
```

Then open http://localhost:8000.

## Managing it

- **Stop it:** `powershell -ExecutionPolicy Bypass -File scripts\stop_tradingbot.ps1`
- **Turn off auto-start (keeps running if already started):**
  `powershell -ExecutionPolicy Bypass -File scripts\disable_autostart.ps1`
  — or just delete the `.lnk` file from the Startup folder above.
- **Change what it trades:** edit the `$traderArgs` block near the top of
  `start_tradingbot.ps1` (strategy, params, instrument, retune interval).
- **Logs:** `logs/paper_trader.log`, `logs/paper_trader.err.log`,
  `logs/dashboard.log`, `logs/dashboard.err.log`.

## Notes

- This uses a Startup-folder shortcut rather than a Task Scheduler entry.
  Practically the same result (runs once you log in), but if you'd rather
  have a proper scheduled task (e.g. so it can restart on crash, or run
  before login), you can register one yourself from an ordinary
  (non-sandboxed) PowerShell window:

  ```powershell
  schtasks /Create /TN "TradingBotAutoStart" /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"C:\Users\mrfor\Desktop\TradingBot\scripts\start_tradingbot.ps1`"" /SC ONLOGON /F
  ```

  then delete the Startup shortcut so it doesn't start twice.
- It still only trades against the local simulated broker / OANDA demo
  account, never real money, no matter when or how it starts.
