import optuna
import multiprocessing
import sys
import os
import time
import random
from datetime import datetime, timedelta

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)
# Add trader to path (append so root takes precedence)
sys.path.append(os.path.join(project_root, 'trader'))

from trader.engine.node import BacktestNode
from trader.engine.trader_config import BacktestRunConfig
from trader.strategies.pullback_sniper_v10 import PullbackSniperV10, PullbackSniperV10Config
from utils.logger_factory import get_logger

DATETIME_FMT = "%Y-%m-%d %H:%M:%S"

def get_random_window(global_start: datetime, global_end: datetime, window_hours: float):
    total_duration = (global_end - global_start).total_seconds()
    window_duration = window_hours * 3600
    
    max_start_offset = max(0, total_duration - window_duration)
    random_offset = random.uniform(0, max_start_offset)
    
    start_time = global_start + timedelta(seconds=random_offset)
    end_time = start_time + timedelta(hours=window_hours)
    
    return start_time.strftime(DATETIME_FMT), end_time.strftime(DATETIME_FMT)

def objective(trial, data_dir, global_start, global_end, window_hours, samples_per_trial):
    # Define Search Space
    pullback_pct = trial.suggest_float('pullback_percentage', 30.0, 60.0) # Relaxed lower bound to 5%
    stop_loss = trial.suggest_float('stop_loss_percentage', 5.0, 30.0)
    tp_multiplier = trial.suggest_float('take_profit_multiplier', 1.2, 5.0)
    min_volume = trial.suggest_float('min_volume_sol', 0.5, 10.0) # Relaxed lower bound to 0.5 SOL
    
    returns = []
    drawdowns = []
    trades = []
    
    for i in range(samples_per_trial):
        start_str, end_str = get_random_window(global_start, global_end, window_hours)
        
        # Config
        config = PullbackSniperV10Config(
            pullback_percentage=pullback_pct,
            stop_loss_percentage=stop_loss,
            take_profit_multiplier=tp_multiplier,
            
            # Fixed Params
            min_volume_sol=min_volume,
            max_wait_time_minutes=30.0, # Increased wait time
            abort_percentage=50.0,
            
            # Relaxed Filter Set (Looser than Balanced)
            max_sniper_count=100, # Relaxed
            max_vol_1m=50.0, # Relaxed
            max_holder_count_1m=1000,
            min_dev_holding_pct=0.0,
            max_dev_holding_pct=100.0,
            min_unique_signers=5, # Relaxed from 10
            max_bundled_buys=10, # Relaxed from 5
            max_top10_concentration=80.0, # Relaxed from 70
            min_volume_velocity=0.5, # Relaxed from 1.0
            min_lifespan_score=2.0 # Relaxed from 3.0
        )
        
        bt_config = BacktestRunConfig(
            data_dir=data_dir,
            base_latency_ms=0,
            data_filter={
                'start_date': start_str,
                'end_date': end_str
            },
            starting_balance_sol=10.0,
            token_inactivity_timeout_seconds=None,
            log_holder_distribution=False,
            track_holder_distribution=True # Required for filters
        )
        
        strategy = PullbackSniperV10(config)
        node = BacktestNode(bt_config, [strategy])
        
        try:
            node.run()
            
            # Calculate Score for this sample
            summary = strategy._calculate_stats()
            
            if summary:
                ret = summary.total_return_pct
                dd = summary.max_drawdown_pct
                num_trades = summary.total_trades
            else:
                ret = 0.0
                dd = 0.0
                num_trades = 0
            
            returns.append(ret)
            drawdowns.append(dd)
            trades.append(num_trades)
            
        except Exception as e:
            print(f"Trial sample failed: {e}")
            return -1000.0
        
    # Aggregate Scores
    avg_return = sum(returns) / len(returns)
    max_dd = max(drawdowns) if drawdowns else 0.0
    avg_trades = sum(trades) / len(trades)
    
    if max_dd > 100: max_dd = 100
    
    # Objective Function (Same as V9)
    # 1. Drawdown Penalty: Non-linear (x^1.5)
    dd_penalty = (max_dd / 100.0) ** 1.5
    
    # 2. Trade Frequency Bonus
    import math
    trade_bonus = 1.0 + (math.log10(avg_trades + 1) * 0.5) if avg_trades > 0 else 1.0
    
    # 3. Base Score
    if avg_return > 0:
        score = avg_return * (1.0 - dd_penalty) * trade_bonus
    else:
        score = avg_return * (1.0 + dd_penalty)

    return score

def _worker_entry(study_name, storage_url, data_dir, start_dt, end_dt, window_hours, samples_per_trial, n_trials):
    # Connect to existing study
    study = optuna.load_study(study_name=study_name, storage=storage_url)
    study.optimize(lambda t: objective(t, data_dir, start_dt, end_dt, window_hours, samples_per_trial), n_trials=n_trials)

def run_optimization(args):
    log = get_logger('optimize_v10')
    
    storage_url = args.storage
    study_name = args.study_name
    
    start_dt = datetime.strptime(args.start_date, DATETIME_FMT)
    end_dt = datetime.strptime(args.end_date, DATETIME_FMT)
    
    # Create study in main process to init DB
    study = optuna.create_study(
        study_name=study_name, 
        storage=storage_url, 
        direction='maximize', 
        load_if_exists=True
    )
    
    log.info(f"Starting optimization with {args.processes} processes, {args.trials} trials total.")
    log.info(f"Window: {args.window_hours}h, Samples per trial: {args.samples_per_trial}")
    
    processes = []
    trials_per_process = args.trials // args.processes
    
    for i in range(args.processes):
        p = multiprocessing.Process(
            target=_worker_entry,
            args=(study_name, storage_url, args.data_dir, start_dt, end_dt, args.window_hours, args.samples_per_trial, trials_per_process)
        )
        p.start()
        processes.append(p)
        
    for p in processes:
        p.join()
        
    log.info("Optimization complete.")
    
    if len(study.trials) == 0:
        log.error("No trials were completed.")
        return
        
    completed_trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    if not completed_trials:
        log.error("No trials completed successfully.")
        return

    log.info(f"Best params: {study.best_params}")
    log.info(f"Best value: {study.best_value}")
    
    # Save results to CSV for trend analysis
    try:
        df = study.trials_dataframe()
        csv_filename = f"{study_name}_results.csv"
        df.to_csv(csv_filename)
        log.info(f"Saved optimization results to {csv_filename}")
    except Exception as e:
        log.error(f"Failed to save results CSV: {e}")
    
    # Run Validation on full period
    log.info("Running validation with best parameters...")
    run_validation(args, study.best_params)

def run_validation(args, best_params):
    log = get_logger('optimize_v10_validation')
    
    # Merge best params with fixed filter params
    config = PullbackSniperV10Config(
        pullback_percentage=best_params['pullback_percentage'],
        stop_loss_percentage=best_params['stop_loss_percentage'],
        take_profit_multiplier=best_params['take_profit_multiplier'],
        
        # Fixed Params
        min_volume_sol=best_params['min_volume_sol'],
        max_wait_time_minutes=30.0,
        abort_percentage=50.0,
        
        # Relaxed Filter Set
        max_sniper_count=100,
        max_vol_1m=50.0,
        max_holder_count_1m=1000,
        min_dev_holding_pct=0.0,
        max_dev_holding_pct=100.0,
        min_unique_signers=5,
        max_bundled_buys=10,
        max_top10_concentration=80.0,
        min_volume_velocity=0.5,
        min_lifespan_score=2.0
    )
    
    bt_config = BacktestRunConfig(
        data_dir=args.data_dir,
        base_latency_ms=0,
        data_filter={
            'start_date': args.start_date,
            'end_date': args.end_date
        },
        starting_balance_sol=10.0,
        token_inactivity_timeout_seconds=None,
        log_holder_distribution=False,
        track_holder_distribution=True
    )
    
    strategy = PullbackSniperV10(config)
    node = BacktestNode(bt_config, [strategy])
    
    try:
        node.run()
        stats = strategy._calculate_stats()
        
    except Exception as e:
        log.error(f"Validation run failed: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--processes', type=int, default=20)
    parser.add_argument('--trials', type=int, default=300)
    parser.add_argument('--data-dir', default='trader/historical_data')
    parser.add_argument('--start-date', default='2025-09-15 00:00:00')
    parser.add_argument('--end-date', default='2025-10-07 00:00:00')
    parser.add_argument('--window-hours', type=float, default=2.0)
    parser.add_argument('--samples-per-trial', type=int, default=5)
    parser.add_argument('--study-name', default='v10_pullback_opt')
    parser.add_argument('--storage', default='sqlite:///v10_optuna.db')
    
    args = parser.parse_args()
    run_optimization(args)
