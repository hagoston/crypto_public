import sys
import os
from datetime import datetime, timedelta
import sqlite3

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)
# Add trader to path (append so root takes precedence)
sys.path.append(os.path.join(project_root, 'trader'))

from trader.strategies.analyzers.market_structure_analyzer import MarketStructureAnalyzer
from trader.strategies.filters.market_structure_filter import MarketStructureFilter
from trader.inspector.db_manager import DBManager
from engine.pydantic_models import TickData, StrategyConfig, TokenState

class MockNode:
    def __init__(self):
        self.token_states = {}

def verify_analyzer():
    print("Verifying MarketStructureAnalyzer...")
    
    # Setup DB
    db = DBManager("test_inspector.db")
    db.connect()
    db.create_tables()
    db.clear_db() # Clear previous test data
    
    # Setup Analyzer
    config = StrategyConfig()
    analyzer = MarketStructureAnalyzer(config)
    analyzer.node = MockNode()
    analyzer.db_manager = db # Override with test db
    
    mint = "TEST_MINT"
    start_time = datetime.now()
    
    # Simulate Ticks
    # 1. T=0: First seen
    tick0 = TickData(
        ts_datetime=start_time,
        is_buy=True,
        token_price_sol=0.001,
        quantity_sol=1.0,
        quantity_token=1000,
        payer_address="user1",
        mint_address=mint
    )
    analyzer.on_tick(tick0)
    
    # 2. T=30s: Volume check
    tick30 = TickData(
        ts_datetime=start_time + timedelta(seconds=30),
        is_buy=True,
        token_price_sol=0.002,
        quantity_sol=2.0, # Total vol should be 3.0
        quantity_token=1000,
        payer_address="user2",
        mint_address=mint
    )
    analyzer.on_tick(tick30)
    
    # 3. T=1m: Features capture
    # Add some sells and more buys
    tick60 = TickData(
        ts_datetime=start_time + timedelta(minutes=1),
        is_buy=False, # Sell
        token_price_sol=0.0015,
        quantity_sol=0.5,
        quantity_token=500,
        payer_address="user1", # Repeat user
        mint_address=mint
    )
    analyzer.on_tick(tick60)
    
    # Mock TokenState for capture
    analyzer.node.token_states[mint] = TokenState(
        first_seen=start_time,
        last_tick=start_time + timedelta(minutes=1),
        token_metadata=None,
        holder_count=10,
        holder_distribution={"dev": 100, "others": 900},
        dev_wallet="dev"
    )
    
    # Trigger capture
    tick61 = TickData(
        ts_datetime=start_time + timedelta(minutes=1, seconds=1),
        is_buy=True,
        token_price_sol=0.002,
        quantity_sol=0.1,
        quantity_token=100,
        payer_address="user3",
        mint_address=mint
    )
    analyzer.on_tick(tick61)
    
    # Stop and Commit
    analyzer.on_stop()
    
    # Verify DB
    cursor = db.conn.cursor()
    cursor.execute("SELECT * FROM market_analysis WHERE mint_address=?", (mint,))
    row = cursor.fetchone()
    
    # Columns: mint, first_seen, vol_1m, vol_30s, buy_count, sell_count, unique_signers, ...
    # We need to check indices or dict
    # vol_1m should be 1.0 + 2.0 + 0.5 + 0.1 = 3.6
    # vol_30s should be 1.0 + 2.0 = 3.0 (captured at T=30s tick)
    # buy_count_1m: tick0(buy), tick30(buy), tick60(sell), tick61(buy) -> 3 buys, 1 sell
    # unique_signers: user1, user2, user3 -> 3
    
    print("DB Row:", dict(row))
    
    vol_1m = row['vol_1m_sol']
    vol_30s = row['vol_30s_sol']
    buy_count = row['buy_count_1m']
    sell_count = row['sell_count_1m']
    unique_signers = row['unique_signers_1m']
    
    assert vol_30s == 3.0, f"Expected vol_30s=3.0, got {vol_30s}"
    assert vol_1m == 3.6, f"Expected vol_1m=3.6, got {vol_1m}"
    assert buy_count == 3, f"Expected buy_count=3, got {buy_count}"
    assert sell_count == 1, f"Expected sell_count=1, got {sell_count}"
    assert unique_signers == 3, f"Expected unique_signers=3, got {unique_signers}"
    
    print("Analyzer Verification PASSED")
    db.close()
    os.remove("test_inspector.db")

def verify_filter():
    print("\nVerifying MarketStructureFilter...")
    f = MarketStructureFilter(
        min_vol_velocity=1.2,
        max_sell_ratio=0.6,
        min_unique_signers=5
    )
    
    # Test Volume Velocity
    # Good: 10 -> 15 (1.5x)
    rej, msg = f.check_volume_velocity(15.0, 10.0)
    assert not rej, f"Should pass velocity 1.5: {msg}"
    
    # Bad: 10 -> 11 (1.1x)
    rej, msg = f.check_volume_velocity(11.0, 10.0)
    assert rej, "Should reject velocity 1.1"
    
    # Test Buy/Sell Ratio
    # Good: 4 buys, 6 sells (0.6)
    rej, msg = f.check_buy_sell_ratio(4, 6)
    assert not rej, f"Should pass sell ratio 0.6: {msg}"
    
    # Bad: 3 buys, 7 sells (0.7)
    rej, msg = f.check_buy_sell_ratio(3, 7)
    assert rej, "Should reject sell ratio 0.7"
    
    # Test Unique Signers
    # Good: 5
    rej, msg = f.check_unique_signers(5)
    assert not rej, f"Should pass unique signers 5: {msg}"
    
    # Bad: 4
    rej, msg = f.check_unique_signers(4)
    assert rej, "Should reject unique signers 4"
    
    print("Filter Verification PASSED")

if __name__ == "__main__":
    verify_analyzer()
    verify_filter()
