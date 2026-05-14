import argparse
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from trader.engine.node import BacktestNode
from trader.engine.trader_config import BacktestRunConfig
from trader.strategies.analyzers.market_structure_analyzer import MarketStructureAnalyzer
from utils.logger_factory import get_logger

def main():
    parser = argparse.ArgumentParser(description="Run Market Structure Analysis")
    parser.add_argument('--data-dir', default='trader/historical_data')
    parser.add_argument('--start-date', default='2025-09-15 00:00:00')
    parser.add_argument('--end-date', default='2025-10-07 00:00:00')
    
    args = parser.parse_args()
    log = get_logger('run_market_analysis')
    
    log.info("Starting Market Structure Analysis...")
    
    # Config
    bt_config = BacktestRunConfig(
        data_dir=args.data_dir,
        base_latency_ms=0, # Zero latency for analysis
        data_filter={
            'start_date': args.start_date,
            'end_date': args.end_date
        },
        starting_balance_sol=100.0,
        token_inactivity_timeout_seconds=None, # Don't timeout tokens, we want full history
        log_holder_distribution=False,
        track_holder_distribution=True # Required for features
    )
    
    # Strategy
    strategy = MarketStructureAnalyzer()
    
    # Node
    node = BacktestNode(bt_config, [strategy])
    
    try:
        node.run()
    except KeyboardInterrupt:
        log.info("Interrupted by user.")
    except Exception as e:
        log.exception(f"Analysis failed: {e}")
        
    log.info("Analysis complete.")

if __name__ == "__main__":
    main()
