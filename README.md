# TradingBot

A forex strategy backtester + walk-forward optimizer + paper-trading bot with
a live dashboard. **No broker account or signup required** by default — real
market prices come from Yahoo Finance, and "orders" are tracked as a fake
balance/position locally. An optional OANDA demo-account backend is also
available if you want real broker-side order matching later; `config.py`
hard-refuses to run against a live real-money account either way.

## Why "paper trading," not live

Grid-searching thousands of parameter combinations and picking whichever one
had the best backtest return is a great way to find a strategy that was
curve-fit to noise and falls apart on new data. This project bakes in
**walk-forward validation**: it splits history into chronological folds and
ranks strategies by out-of-sample performance, and reports the gap between
in-sample and out-of-sample results so you can see how much of the "edge" is
real. Even so, treat any backtest as a hypothesis, not a guarantee — run it
in paper mode for a while and see if it actually holds up before ever
considering real money.

## 1. Setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

That's it — no account, no API key, no ID verification. Skip to step 2.

<details>
<summary>Optional: use a real OANDA demo account instead</summary>

Only worth doing if you specifically want real broker-side execution instead
of the local simulator. Requires OANDA's signup, which may ask for identity
verification depending on your region — the local simulator above needs
none of that and is the recommended default.

1. https://www.oanda.com/forex-trading/demo-account/
2. In the account portal, generate a "Personal Access Token" for the
   **fxTrade Practice** environment.
3. Copy `.env.example` to `.env` and fill in `OANDA_API_KEY` and
   `OANDA_ACCOUNT_ID` (found under "My Account" in the portal, looks like
   `101-004-1234567-001`).
4. Pass `--source oanda` (backtest/optimize) or `--broker oanda`
   (paper trader) to use it.
</details>

## 2. Backtest a strategy

```bash
python run_backtest.py --strategy sma_cross --params fast=10,slow=50 --instrument EUR_USD --granularity H1
python run_backtest.py --strategy rsi_reversion --params period=14,oversold=30,overbought=70 \
    --instrument EUR_USD --granularity H1
```

Uses free Yahoo Finance data by default (`--source yfinance`). Pass
`--source synthetic` for a fake random-walk series, or `--source oanda` for
real OANDA history (needs the optional setup above).

Bundled strategies: `sma_cross`, `rsi_reversion`, `breakout`, `macd_momentum`,
`bollinger_reversion` (see `strategies/`). Adding a new one is a ~15-line
file — see any existing strategy for the pattern.

## 3. Search parameters (the "test thousands of strategies" part)

```bash
python run_optimize.py --strategy all --instrument EUR_USD --granularity H1 --folds 4 --top 10
```

This grid-searches every combination in each strategy's `param_grid`,
evaluates each on multiple walk-forward folds, and ranks by mean
**out-of-sample** Sharpe ratio — not in-sample. Pick a combo with a high OOS
Sharpe and a small overfit gap, not just the top in-sample number.

If a strategy's grid gets large, exhaustive search gets slow. Pass
`--search random --max-combos 500` to sample that many combinations instead
of walking the full grid — trades search coverage for wall-clock time.

## 4. Paper trade it live (no account, fake money)

```bash
python run_paper_trader.py --strategy sma_cross --params fast=10,slow=50 \
    --instrument EUR_USD --granularity H1 --units 1000 --poll-seconds 60
```

This polls Yahoo Finance for new candles, computes the strategy's desired
position, and simulates a market order to match it — no broker involved, the
fake balance and position live in `storage/tradingbot.db`. Every fill and
account balance snapshot is logged there too. Leave it running (e.g. in a
VPS, in a `tmux`/background session) to forward-test over time. Add
`--broker oanda` to route through a real OANDA demo account instead.

### Auto re-tuning ("making the bot learn")

By default the strategy and params you pass in stay fixed forever — the bot
does not learn anything on its own. `--auto-retune-hours N` makes it
periodically re-run the same walk-forward search from step 3 on the latest
data and **only** switch to a new strategy/params if a candidate clears two
guardrails: a minimum out-of-sample Sharpe (`--retune-min-oos-sharpe`,
default 0.0) and a maximum overfit gap (`--retune-max-overfit-gap`, default
1.5). If nothing clears the bar, it keeps running what it already had.

```bash
python run_paper_trader.py --strategy sma_cross --params fast=10,slow=50 \
    --instrument EUR_USD --granularity H1 --auto-retune-hours 6 \
    --retune-strategies all --retune-search random --retune-max-combos 200
```

This is genuine adaptation to shifting market conditions, not a model that
gets smarter with each cycle — a re-tune can just as easily rotate the bot
into a worse regime as a better one, since the search still only sees
historical data. Every cycle (whether it switched or not) is logged and
visible on the dashboard so you can watch what it's doing. The bot pauses
trading while a re-tune runs (searching takes seconds to a couple minutes
depending on how many combinations/strategies you include).

Every re-tune decision is also written to [learn/](learn/) as plain files
(`current_strategy.json`, `history.jsonl`) — open them in a text editor if
you want to see what it's picked over time without touching the database.

### Position sizing

`--units 1000` (the default) always trades the same size regardless of how
volatile the market currently is. `--position-sizing volatility` instead
sizes each trade so that a move of `--atr-multiplier` (default 1.5) times
the Average True Range against the position costs roughly `--risk-pct`
(default 1%) of the account balance — bigger positions in calm markets,
smaller ones in choppy markets, so *dollar risk per trade* stays roughly
constant instead of *unit count*.

```bash
python run_paper_trader.py --strategy sma_cross --params fast=10,slow=50 \
    --instrument EUR_USD --granularity H1 --position-sizing volatility --risk-pct 0.01
```

This only sizes the next trade — it doesn't place a real stop-loss order,
so an unusually large single move can still cost more than the risk
budget. See `live/position_sizing.py` for the full caveats (it also assumes
the account currency equals the pair's quote currency, which is exactly
true for EUR_USD/USD but an approximation for other pairs).

### Notifications

Set `DISCORD_WEBHOOK_URL` in `.env` (get one from a Discord channel's
Integrations settings) to get a message posted for every trade fill and
every re-tune decision. Leave it unset and notifications are silently
skipped — nothing else changes. Treat the URL as a secret: anyone who has
it can post to that channel, so it's never read from anywhere but env vars
(`live/notify.py`), and `.env` is gitignored.

## 5. Watch the dashboard

In a separate terminal, with the paper trader running:

```bash
uvicorn dashboard.server:app --reload --port 8000
```

Open http://localhost:8000 — shows current status, balance, return,
drawdown, win rate, an equity curve, the trade log, and (if auto re-tuning is
on) a history of every re-tune cycle and whether it switched strategies,
refreshing every 5s.

## 6. Run it automatically at login

See [scripts/README.md](scripts/README.md) — a Startup-folder shortcut
launches the paper trader + dashboard hidden in the background the next time
you log into Windows, no terminal window needed. This only runs while the
PC is on and you're logged in.

## 7. Run it 24/7 with GitHub Actions (no PC required)

For a bot that keeps running even when your computer is off, GitHub Actions
can run it on a schedule instead — no VPS, no always-on machine. This is a
**separate, independent instance** from the local one: its own state
(`storage/cloud_tradingbot.db`, `learn_cloud/`), its own starting balance,
so running both doesn't cause any conflict.

How it works: Actions runners are ephemeral (each run starts fresh and
disappears), so instead of one process staying alive and sleeping between
checks, `.github/workflows/paper_trade.yml` runs `run_paper_trader.py
--once` every 30 minutes — a single check-and-maybe-trade cycle — then
commits the updated state back to the repo so the next run can pick up
where the last one left off (see `run_paper_trader_once()` in
`live/paper_trader.py`).

**Setup (you'll need to run these yourself — account creation and pushing
code aren't things I can do on your behalf):**

1. Create a new **public** GitHub repo (public is required for the free
   dashboard hosting below — there's nothing sensitive in it, since the
   simulated broker uses no API keys).
2. From this project folder:
   ```bash
   git remote add origin https://github.com/<you>/<repo-name>.git
   git branch -M main
   git push -u origin main
   ```
3. On the repo's GitHub page: **Settings → Actions → General → Workflow
   permissions** → select "Read and write permissions" (needed so the
   workflow can commit its own state back).
4. **Settings → Pages** → Source: "Deploy from a branch" → Branch: `main`,
   folder: `/docs` → Save. GitHub gives you a URL like
   `https://<you>.github.io/<repo-name>/` — that's your dashboard, viewable
   from any device.
5. The workflow starts running automatically on its schedule. To trigger
   the first run immediately instead of waiting: repo page → **Actions**
   tab → "Paper Trade" → **Run workflow**.
6. Optional, for Discord notifications from this instance: **Settings →
   Secrets and variables → Actions → New repository secret**, name
   `DISCORD_WEBHOOK_URL`, value your webhook URL. It's encrypted at rest
   and never shown in logs. Skip this and notifications are just silently
   off for the cloud instance.

The seed strategy for this instance is set in
`.github/workflows/paper_trade.yml` (`--strategy` / `--params` on the "Run
one paper-trader tick" step) — edit and push to change it; like the local
instance, it only matters for the very first run, since every run after
that resumes from whatever's already active.

**Known limitations, so you're not surprised:**
- GitHub delays scheduled workflows under load, sometimes by 10+ minutes —
  fine for an hourly-granularity strategy, not for anything faster.
- GitHub auto-disables scheduled workflows after 60 days with no commits to
  the repo (not "no bot activity" — the bot's own commits count, so in
  practice this shouldn't trigger, but worth knowing about).
- Every commit is public: the code, the trade history, the numbers. Nothing
  sensitive given the simulated broker, but worth knowing.

## Running the tests

```bash
pytest tests/ -v
```

Covers the backtest engine's no-lookahead/cost logic, the simulated
broker's P&L bookkeeping (open/close/blend/flip-through-zero), the
walk-forward fold math, the resume-vs-seed and retune-timer logic that
`--once` mode depends on, position sizing, and dashboard stats. Not
covered: the actual OANDA/Yahoo Finance network calls, or the GitHub
Actions workflow itself (those need real runs to verify, per the smoke
tests done in this project's development).

## Project layout

```
config.py               env vars, OANDA host (practice-only guard)
data/fetch.py            historical candles: Yahoo Finance (no account), OANDA, or synthetic
strategies/               one file per strategy: generate_signals(df, **params) -> position series
backtest/engine.py        vectorized backtest (no lookahead, spread/slippage cost)
backtest/metrics.py       Sharpe, drawdown, win rate, profit factor
optimize/search.py        walk-forward grid/random search across a strategy's param_grid
live/simulated_broker.py  default paper backend: no account, local fake balance/position
live/oanda_client.py      optional real OANDA demo-account backend
live/paper_trader.py      polling loop: signal -> order -> log
live/auto_retune.py       periodic re-search + guardrails, called from paper_trader.py
live/learn_log.py         writes learn/ plain-file snapshots of re-tune decisions
live/position_sizing.py   fixed vs volatility(ATR)-based unit sizing
live/notify.py            optional Discord webhook notifications (trade fills, re-tunes)
storage/db.py             SQLite: trades, equity snapshots, bot status, retune history
learn/                    plain-file record of what the bot has picked and why (see learn/README.md)
dashboard/                FastAPI API + static dashboard page (local instance)
docs/                     static dashboard page for GitHub Pages (cloud instance)
export_dashboard_data.py  writes docs/data/*.json from the DB, for the static dashboard
.github/workflows/        scheduled "run one tick, commit state" workflow (see step 7 above)
scripts/                  Windows auto-start at login (see scripts/README.md)
tests/                    pytest suite -- see "Running the tests" below
run_backtest.py           CLI
run_optimize.py           CLI
run_paper_trader.py       CLI (--once for a single cron-driven tick)
```

## What this doesn't do

- It never places a live/real-money order — `config.py` raises if
  `OANDA_ENV=live` is set, and the default broker never talks to a real
  account at all.
- It isn't investment advice, and a good paper-trading track record still
  doesn't guarantee anything about real trading (different fills, slippage,
  psychology of real money, etc).
- The bundled strategies are simple, standard textbook ones (moving average
  crossover, RSI mean-reversion, Donchian breakout, MACD, Bollinger Bands)
  meant as a starting point, not a proven edge.
- Auto re-tuning is parameter search on a timer with guardrails, not machine
  learning — there's no model, and nothing carries knowledge forward between
  cycles beyond "did the last pick clear the bar."
- Volatility-based position sizing controls how big the next trade is, not
  how much a single bad move can cost — there's no real stop-loss order
  behind it.
