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

The output ends with a **multiple-testing check**: how many combinations
you evaluated, the Sharpe ratio you'd expect the best of them to show by
pure chance with zero real skill, and whether your actual best result beat
that number. A result that doesn't clear it is statistically
indistinguishable from noise, however good the raw Sharpe looks — see
`optimize/deflated_sharpe.py`. The live auto-retuner (step 4) enforces this
automatically; here it's just reported so you can factor it in yourself
when picking a seed strategy.

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
data and **only** switch to a new strategy/params if a candidate clears
three guardrails: a minimum out-of-sample Sharpe (`--retune-min-oos-sharpe`,
default 0.0), a maximum overfit gap (`--retune-max-overfit-gap`, default
1.5), and — the one that actually matters most — the **multiple-testing
noise benchmark**. If nothing clears every bar, it keeps running what it
already had.

That third guardrail deserves an explanation, because it's the difference
between a number that means something and a number that doesn't. If you
evaluate 100 (strategy, params) combinations, the *best* one's Sharpe ratio
looks inflated just from having tried 100 things — pure noise, with zero
real skill, eventually produces a good-looking result by chance alone given
enough tries. `optimize/deflated_sharpe.py` computes the Sharpe you'd
*expect* the best of N trials to show even with no real edge at all
(Bailey & Lopez de Prado's expected-maximum-Sharpe-under-the-null
benchmark), and a re-tune candidate must beat that number, not just clear
an arbitrary flat threshold. Skip it with `--retune-ignore-noise-bar` if you
want the old, more permissive behavior — but running this bot for real, you
almost always want it on, since it's specifically designed to catch the
failure mode auto-retuning is most exposed to.

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

### Kill switch (max drawdown)

`--max-drawdown-pct 20` flattens the position and halts **all** trading the
moment equity falls that far below its all-time peak, until manually
cleared. There's no way to tell, in the moment, whether a losing stretch is
"the strategy is just having a bad week" (normal, no action needed) or
"something is badly wrong" (a bug, a data problem, a regime the strategy
has no business trading in) — so this doesn't try to guess. It stops the
bleeding at a pre-agreed line and waits for a human to look, which is the
right default when you genuinely don't know which situation you're in.

```bash
python run_paper_trader.py --strategy sma_cross --params fast=10,slow=50 \
    --instrument EUR_USD --granularity H1 --max-drawdown-pct 20
```

Once tripped, every subsequent tick just records equity/heartbeat (so the
dashboard still shows it's alive) and skips trading entirely — no candle
fetch, no signal, no orders — until you clear it:

```bash
python run_paper_trader.py --strategy sma_cross --instrument EUR_USD --granularity H1 --resume-trading --once
```

Off by default (no drawdown limit). See `live/kill_switch.py`.

### Position sizing

`--units 1000` (the default) always trades the same size regardless of how
volatile the market currently is. `--position-sizing volatility` instead
sizes each trade so that a move of `--atr-multiplier` (default 1.5) times
the Average True Range against the position costs roughly `--risk-pct`
(default 1%) of the account balance — bigger positions in calm markets,
smaller ones in choppy markets, so *dollar risk per trade* stays roughly
constant instead of *unit count*. It also caps every position between
`--min-notional` (default $50, skip positions too small to bother with) and
`--max-notional-pct` (default 0.5 = never more than half the account in one
position) — expressed as account-currency **value**, not raw unit count,
since "1 unit" means wildly different things across instruments (1 unit of
EUR_USD is ~$1, 1 unit of BTC-USD is ~$78,000+; an early version of this
bounded by raw unit count and could size a position at hundreds of times
the account's value on a high-priced asset before this was caught and
fixed).

```bash
python run_paper_trader.py --strategy sma_cross --params fast=10,slow=50 \
    --instrument EUR_USD --granularity H1 --position-sizing volatility --risk-pct 0.01
```

Position sizes are fractional (e.g. 0.06 BTC), not whole-unit-only — a
whole-unit floor is harmless for forex but would make any sane risk-sized
position on a high-priced asset impossible at retail account sizes. The
simulated broker supports fractional units; the real OANDA broker rounds to
whole units when actually placing the order, since OANDA doesn't accept
fractional units for forex/CFDs (not a practical issue there since OANDA
doesn't offer crypto anyway).

This only sizes the next trade — it doesn't place a real stop-loss order,
so an unusually large single move can still cost more than the risk
budget. See `live/position_sizing.py` for the full caveats (it also assumes
the account currency equals the pair's quote currency, which is exactly
true for EUR_USD/USD and BTC_USD but an approximation for other pairs).

### Cost model

The simulated broker's spread cost isn't flat — it's a constant floor
(`spread_bps`, 2.0 by default) plus a slippage term that scales with
recent volatility (ATR as a % of price, via `slippage_atr_multiplier`,
0.5 by default). Real bid/ask spreads and execution slippage widen in
choppy conditions and tighten in calm ones; assuming a flat cost is
optimistic exactly when it matters most, since a strategy's apparent edge
often shows up precisely during the volatile stretches where real costs
would have been highest. Not exposed as CLI flags (yet) — change the
defaults in `live/simulated_broker.py` if you want different values.

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

## 8. Trading multiple instruments in parallel

Nothing in this project is forex-specific — `data/fetch.py`'s Yahoo Finance
source already handles crypto tickers directly (`BTC-USD`, `ETH-USD`, ...)
with zero code changes, and every strategy is a generic technical
indicator that works on any OHLC data. The bundled BTC-USD instance is a
**fully separate, independent bot** from the EUR/USD one — own state, own
starting balance, own dashboard — following the same pattern as the
local/cloud split:

| | EUR/USD | BTC-USD |
|---|---|---|
| Local dashboard | :8000 | :8001 |
| Local start script | `scripts/start_tradingbot.ps1` | `scripts/start_tradingbot_btc.ps1` |
| Cloud workflow | `.github/workflows/paper_trade.yml` | `.github/workflows/paper_trade_btc.yml` |
| Cloud dashboard page | `docs/index.html` | `docs/btc.html` |
| Cloud state files | `storage/cloud_tradingbot.db`, `learn_cloud/`, `docs/data/` | `storage/cloud_tradingbot_btc.db`, `learn_cloud_btc/`, `docs/data-btc/` |

The two cloud workflows share the same GitHub repo/branch, so their
schedules are offset (`:00`/`:30` vs `:15`/`:45`) and their push steps
retry-with-rebase, to avoid one occasionally clobbering the other's push.

**Adding another instrument** (a different crypto pair, or a commodity —
Yahoo Finance also has futures like `GC=F` for gold, `CL=F` for crude oil):
copy the local start/stop scripts and the cloud workflow YAML for BTC,
rename their `TRADINGBOT_DB_PATH`/`TRADINGBOT_LEARN_DIR`/
`TRADINGBOT_DOCS_SUBDIR` values and dashboard port so they don't collide
with an existing instance, and run `run_optimize.py --instrument
<your-instrument>` first to pick a sane seed strategy rather than guessing.

Worth saying plainly: adding more instruments is a good way to see whether
an edge shows up **anywhere**, but it doesn't by itself make any of them
more likely to be profitable — it's the same experiment run in parallel,
not a different, better one.

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
optimize/deflated_sharpe.py  multiple-testing noise benchmark (Bailey & Lopez de Prado)
live/simulated_broker.py  default paper backend: no account, local fake balance/position, volatility-scaled costs
live/oanda_client.py      optional real OANDA demo-account backend
live/paper_trader.py      polling loop: signal -> order -> log
live/auto_retune.py       periodic re-search + guardrails (incl. the noise benchmark), called from paper_trader.py
live/kill_switch.py       max-drawdown decision logic, called from paper_trader.py
live/learn_log.py         writes learn/ plain-file snapshots of re-tune decisions
live/position_sizing.py   fixed vs volatility(ATR)-based unit sizing
live/notify.py            optional Discord webhook notifications (trade fills, re-tunes, kill switch)
storage/db.py             SQLite: trades, equity snapshots, bot status, retune history
learn/                    plain-file record of what the bot has picked and why (see learn/README.md)
dashboard/                FastAPI API + static dashboard page (local EUR/USD instance; BTC-USD reuses this on port 8001)
docs/                     static dashboard pages for GitHub Pages (index.html = EUR/USD, btc.html = BTC-USD)
export_dashboard_data.py  writes docs/<subdir>/*.json from the DB, for a static dashboard page
.github/workflows/        scheduled "run one tick, commit state" workflows, one per instrument (see steps 7-8 above)
scripts/                  Windows auto-start at login, one pair of scripts per instrument (see scripts/README.md)
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
- The multiple-testing noise benchmark tells you a result isn't
  *explainable by search volume alone* — it doesn't prove a strategy has a
  real edge. Overfitting to the specific backtest window, regime-dependence,
  and ordinary bad luck are all still live possibilities even for a result
  that clears the bar.
- The kill switch stops the bleeding at a drawdown line; it can't tell you
  *why* the drawdown happened, and it doesn't undo losses already taken.
