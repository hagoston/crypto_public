# Momentum Sniper Hyperparameter Workflow

## Phase 1 – Fast Exploration
- Target a short, active window to keep trials quick:
  > If you already have an old `optuna_fast.db`, remove it first (`rm optuna_fast.db`) so SQLite can initialise cleanly.
  ```
  uv run python trader/optimize_momentum_sniper.py \
    --study-name ms_fast \
    --storage sqlite:///optuna_fast.db \
    --start-date "2025-10-02 00:00:00" \
    --end-date   "2025-10-02 04:00:00" \
    --chunk-seconds 900 \
    --slices-per-trial 2 \
    --aggregate mean \
    --trials 150 \
    --processes 8 \
    --jobs 1
  ```
- Enable pruning by editing `optimize_momentum_sniper.py` to pass `pruner=optuna.pruners.MedianPruner()` to `create_study` if desired.
- Inspect `optuna_fast.db` with the dashboard:
  ```
  uv run optuna-dashboard sqlite:///optuna_fast.db
  ```

## Phase 2 – Broader Sampling
- Start a new study, seeding it with the best Phase‑1 trials if needed (`study.enqueue_trial` via a small helper script):
  ```
  uv run python trader/optimize_momentum_sniper.py \
    --study-name ms_wide \
    --storage sqlite:///optuna_wide.db \
    --start-date "2025-09-20 00:00:00" \
    --end-date   "2025-09-22 00:00:00" \
    --chunk-seconds 1800 \
    --slices-per-trial 4 \
    --aggregate mean \
    --trials 250 \
    --processes 12 \
    --jobs 1
  ```
- Review progress in parallel with `uv run optuna-dashboard sqlite:///optuna_wide.db`.

## Phase 3 – Validation
- For the top configurations, run out-of-sample backtests (multiple windows):
  ```
  uv run python trader/run_backtest.py \
    --strategy momentum_sniper \
    --start-date "2025-09-27 00:00:00" \
    --end-date   "2025-09-28 00:00:00" \
    --ms-... <parameters from study.best_trial>
  ```
- Repeat on several date ranges (e.g., different weeks) to ensure stability.

## Parallel Windows
- To diversify data, launch independent studies on different weeks:
  ```
  uv run python trader/optimize_momentum_sniper.py \
    --study-name ms_week1 \
    --storage sqlite:///optuna_week1.db \
    --start-date "2025-09-13 00:00:00" \
    --end-date   "2025-09-15 00:00:00" \
    --chunk-seconds 1800 \
    --slices-per-trial 3 \
    --trials 150 \
    --processes 10 \
    --jobs 1
  ```
- Run multiple instances simultaneously (adjust `--processes` per machine capacity).
