# What the bot has learned

This folder is a plain-file view into the same walk-forward parameter
search described in the main README -- there's no model here, just a
record of which strategy/params were live and why.

- **current_strategy.json** -- what's running right now, and the
  out-of-sample Sharpe / overfit gap that justified it (if it came from a
  re-tune; "seed" entries were just the starting point you passed on the
  command line, not yet validated).
- **history.jsonl** -- one line per re-tune cycle, oldest first. Every
  cycle is logged whether it switched strategies or not. Each line has:
  `timestamp`, `old_strategy`/`old_params`, `new_strategy`/`new_params`,
  `changed`, `mean_test_sharpe` (out-of-sample), `overfit_gap`
  (in-sample Sharpe minus out-of-sample Sharpe -- large values mean the
  pick looked good mostly because it was fit to the training window).

Read `mean_test_sharpe` and `overfit_gap` skeptically: this is a search
over historical data re-run periodically, not a model that accumulates
understanding. A high out-of-sample Sharpe in one cycle is not a promise
about the next one.
