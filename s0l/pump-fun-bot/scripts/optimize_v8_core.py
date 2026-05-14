import argparse
import optuna
import logging
import random
import sys
import os
from datetime import datetime, timedelta
from multiprocessing import Process
from typing import List, Optional, Tuple

# Add project root and trader directory to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(project_root, 'trader'))
sys.path.insert(0, project_root)

from trader.engine.node import BacktestNode
from trader.engine.trader_config import BacktestRunConfig
from trader.strategies.momentum_sniper_v8_core import MomentumSniperV8Core, MomentumSniperV8CoreConfig
from utils.logger_factory import get_logger

# Suppress excessive logging
logging.getLogger('node').setLevel(logging.WARNING)
logging.getLogger('data_loader').setLevel(logging.WARNING)
logging.getLogger('strat').setLevel(logging.WARNING)

DATETIME_FMT = "%Y-%m-%d %H:%M:%S"

def get_random_window(global_start: datetime, global_end: datetime, window_hours: float):
    total_duration = (global_end - global_start).total_seconds()
    window_duration = window_hours * 3600
    
    max_start_offset = max(0, total_duration - window_duration)
    random_offset = random.uniform(0, max_start_offset)
    
    start_time = global_start + timedelta(seconds=random_offset)
    end_time = start_time + timedelta(hours=window_hours)
    
    return start_time.strftime(DATETIME_FMT), end_time.strftime(DATETIME_FMT)

def objective(
    trial: optuna.trial.Trial,
    data_dir: str,
    global_start: datetime,
    global_end: datetime,
    window_hours: float,
    samples_per_trial: int
) -> float:
    # 1. Suggest Hyperparameters (Core Only)
    min_vol_1m_sol = trial.suggest_float('min_vol_1m_sol', 1.0, 20.0)
    hard_stop_pct = trial.suggest_float('hard_stop_pct', 0.05, 0.30)
    tp_pct = trial.suggest_float('tp_pct', 0.10, 1.00)
    
    # 2. Evaluate on Multiple Random Windows
    returns = []
    drawdowns = []
    
    for i in range(samples_per_trial):
        start_str, end_str = get_random_window(global_start, global_end, window_hours)
        
        config = MomentumSniperV8CoreConfig(
            min_vol_1m_sol=min_vol_1m_sol,
            hard_stop_pct=hard_stop_pct,
            tp_pct=tp_pct,
            max_concurrent_positions=5
        )
        
        strategy = MomentumSniperV8Core(config=config)
        
        bt_config = BacktestRunConfig(
            data_dir=data_dir,
            base_latency_ms=3000,
            data_filter={
                'start_date': start_str,
                'end_date': end_str
            },
            starting_balance_sol=5.0,
            token_inactivity_timeout_seconds=300,
            log_holder_distribution=False,
            track_holder_distribution=True
        )
        
        try:
            node = BacktestNode(bt_config, [strategy])
            node.run()
            
            summary = strategy._calculate_stats()
            if summary:
                returns.append(summary.total_return_pct)
                drawdowns.append(summary.max_drawdown_pct)
            else:
                returns.append(0.0)
                drawdowns.append(0.0)
                
        except Exception as e:
            print(f"Run failed: {e}")
            return -100.0

    # 3. Aggregate Scores
    avg_return = sum(returns) / len(returns)
    max_dd = max(drawdowns) if drawdowns else 0.0
    
    # Penalty for high drawdown in ANY window
    # User requested formula: (100 - max_dd) / 100 * avg_return
    # If max_dd is > 100 (unlikely but possible in crypto), score becomes negative, which is fine.
    score = (100.0 - max_dd) / 100.0 * avg_return
        
    return score

def _worker_entry(
    study_name: str,
    storage_target: str,
    n_trials: int,
    data_dir: str,
    start_dt: datetime,
    end_dt: datetime,
    window_hours: float,
    samples_per_trial: int
) -> None:
    study = optuna.create_study(
        study_name=study_name,
        storage=storage_target,
        direction='maximize',
        load_if_exists=True,
    )
    study.optimize(
        lambda t: objective(t, data_dir, start_dt, end_dt, window_hours, samples_per_trial),
        n_trials=n_trials
    )

def run_optimization(args):
    start_dt = datetime.strptime(args.start_date, DATETIME_FMT)
    end_dt = datetime.strptime(args.end_date, DATETIME_FMT)
    
    if args.processes > 1:
        if not args.storage:
            raise ValueError("--storage is required for parallel execution")
            
        # Initialize the study in the main process to ensure DB tables are created
        # This prevents race conditions where multiple workers try to create tables simultaneously
        optuna.create_study(
            study_name=args.study_name,
            storage=args.storage,
            direction='maximize',
            load_if_exists=True
        )
        
        workers = []
        trials_per_worker = args.trials // args.processes
        
        for _ in range(args.processes):
            p = Process(
                target=_worker_entry,
                args=(
                    args.study_name,
                    args.storage,
                    trials_per_worker,
                    args.data_dir,
                    start_dt,
                    end_dt,
                    args.window_hours,
                    args.samples_per_trial
                )
            )
            p.start()
            workers.append(p)
            
        for p in workers:
            p.join()
            
        study = optuna.load_study(study_name=args.study_name, storage=args.storage)
        
    else:
        study = optuna.create_study(direction='maximize')
        study.optimize(
            lambda t: objective(t, args.data_dir, start_dt, end_dt, args.window_hours, args.samples_per_trial),
            n_trials=args.trials
        )

    print('Best value:', study.best_value)
    print('Best params:')
    for k, v in study.best_params.items():
        print(f'  {k}: {v}')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', default='trader/historical_data')
    parser.add_argument('--start-date', default='2025-09-15 00:00:00')
    parser.add_argument('--end-date', default='2025-10-07 00:00:00')
    parser.add_argument('--trials', type=int, default=100)
    parser.add_argument('--processes', type=int, default=1)
    parser.add_argument('--storage', default='sqlite:///optuna_v8.db')
    parser.add_argument('--study-name', default='momentum_sniper_v8_core')
    parser.add_argument('--window-hours', type=float, default=2.0)
    parser.add_argument('--samples-per-trial', type=int, default=3)
    
    args = parser.parse_args()
    run_optimization(args)
