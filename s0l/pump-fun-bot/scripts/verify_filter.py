import sys
import os
from datetime import timedelta

# Add project root to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'trader'))

from trader.strategies.filters.market_structure_filter import MarketStructureFilter

def verify_filter():
    print("\nVerifying MarketStructureFilter...")
    f = MarketStructureFilter(
        min_vol_velocity=1.2,
        max_sell_ratio=0.6,
        min_unique_signers=5,
        max_bundled_buys=2,
        max_top10_concentration=50.0
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
    
    # Test Bundled Buys
    # Good: 2
    rej, msg = f.check_bundled_buys(2)
    assert not rej, f"Should pass bundled buys 2: {msg}"
    
    # Bad: 3
    rej, msg = f.check_bundled_buys(3)
    assert rej, "Should reject bundled buys 3"
    
    # Test Concentration
    # Good: 40%
    rej, msg = f.check_concentration(40.0)
    assert not rej, f"Should pass concentration 40%: {msg}"
    
    # Bad: 60%
    rej, msg = f.check_concentration(60.0)
    assert rej, "Should reject concentration 60%"
    
    print("Filter Verification PASSED")

    # 4. Lifespan Score Test
    print("\n--- Testing Lifespan Score ---")
    f_lifespan = MarketStructureFilter(min_lifespan_score=3.0)
    
    # Case 1: High Signers (Score should be high)
    # Base 1.0 + Signers(20) 4.0 + Velocity(1.2) 0.5 = 5.5 -> PASS
    rej, reason = f_lifespan.check_lifespan(unique_signers=25, vol_velocity=1.2, bundled_buys=0, top10_conc=40, min_score=3.0)
    print(f"High Signers (Exp Pass): Rejected={rej}, Reason={reason}")
    
    # Case 2: Low Signers, High Velocity (Score should be low)
    # Base 1.0 + Signers(5) 0.0 - Velocity(2.5) 0.5 = 0.5 -> REJECT
    rej, reason = f_lifespan.check_lifespan(unique_signers=5, vol_velocity=2.5, bundled_buys=0, top10_conc=40, min_score=3.0)
    print(f"Low Quality (Exp Reject): Rejected={rej}, Reason={reason}")

    # Case 3: Balanced (Score should be moderate)
    # Base 1.0 + Signers(10) 2.0 + Velocity(1.2) 0.5 = 3.5 -> PASS
    rej, reason = f_lifespan.check_lifespan(unique_signers=12, vol_velocity=1.2, bundled_buys=0, top10_conc=40, min_score=3.0)
    print(f"Balanced (Exp Pass): Rejected={rej}, Reason={reason}")

if __name__ == "__main__":
    verify_filter()
