import sys
import os

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)
# Add trader to path (append so root takes precedence for 'utils')
trader_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../trader'))
sys.path.append(trader_dir)

print("Sys Path:", sys.path)

try:
    import utils.logger_factory
    print("Successfully imported utils.logger_factory")
except ImportError as e:
    print(f"Failed to import utils.logger_factory: {e}")

try:
    from trader.strategies.momentum_sniper_v9_filtered import MomentumSniperV9Filtered, MomentumSniperV9FilteredConfig
    print("Successfully imported strategy class")
    
    config = MomentumSniperV9FilteredConfig()
    strat = MomentumSniperV9Filtered(config)
    print("Successfully instantiated strategy")
except TypeError as e:
    print(f"Failed to instantiate: {e}")
except Exception as e:
    print(f"Other error: {e}")
