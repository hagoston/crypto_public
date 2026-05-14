import sqlite3
import pandas as pd
import numpy as np
import json
from itertools import product

def load_data(db_path='inspector_data.db'):
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM market_analysis", conn)
    conn.close()
    return df

def prepare_features(df):
    # Avoid division by zero
    df['vol_30s_sol'] = df['vol_30s_sol'].replace(0, 0.0001)
    df['price_at_1m_sol'] = df['price_at_1m_sol'].replace(0, np.nan)
    
    # Derived Metrics
    df['vol_velocity'] = df['vol_1m_sol'] / df['vol_30s_sol']
    df['total_trades_1m'] = df['buy_count_1m'] + df['sell_count_1m']
    df['buy_ratio'] = df['buy_count_1m'] / df['total_trades_1m'].replace(0, 1)
    df['signer_concentration'] = df['unique_signers_1m'] / df['total_trades_1m'].replace(0, 1)
    df['bundle_ratio'] = df['bundled_buy_count_1m'] / df['buy_count_1m'].replace(0, 1)
    
    # ROI Metrics
    # If price_at_1m is NaN (token died before 1m), ROI is 0
    df['roi_after_1m'] = df['max_price_after_1m_sol'] / df['price_at_1m_sol']
    df['roi_after_1m'] = df['roi_after_1m'].fillna(0)
    
    # Survival Metrics (Did it stay active?)
    # We assume "active" means significant trading volume/count
    df['is_alive_15m'] = df['trade_count_15m'] > 50
    df['is_alive_1h'] = df['trade_count_1h'] > 50
    
    # Labels
    df['is_moonshot'] = df['roi_after_1m'] > 5.0
    df['is_profitable'] = df['roi_after_1m'] > 2.0
    df['is_fail'] = (df['is_rug'] == 1) | (df['roi_after_1m'] < 0.5)
    
    return df

def analyze_correlations(df):
    features = [
        'vol_1m_sol', 'vol_velocity', 'buy_ratio', 'unique_signers_1m', 
        'bundled_buy_count_1m', 'holder_count_1m', 'top10_concentration_1m', 
        'dev_holding_1m', 'sniper_count_10s'
    ]
    targets = ['roi_after_1m', 'is_rug', 'is_moonshot']
    
    print("\n=== Correlation Analysis ===")
    corr_matrix = df[features + targets].corr(method='pearson')
    print(corr_matrix[targets].loc[features].round(3))

def optimize_thresholds(df):
    print("\n=== Threshold Optimization (Grid Search) ===")
    
    # Define grid
    grid = {
        'min_unique_signers': [0, 5, 10, 15, 20, 30],
        'max_bundled_buys': [0, 1, 2, 5, 10],
        'min_vol_velocity': [0, 1.2, 1.5, 2.0],
        'max_dev_holding': [100, 20, 10, 5, 1]
    }
    
    results = []
    
    # Iterate (simplified grid search)
    # We test each filter individually first to find "Best Single Filters"
    print("\n--- Best Single Filters ---")
    for feature, thresholds in grid.items():
        for thresh in thresholds:
            mask = None
            if feature == 'min_unique_signers':
                mask = df['unique_signers_1m'] >= thresh
            elif feature == 'max_bundled_buys':
                mask = df['bundled_buy_count_1m'] <= thresh
            elif feature == 'min_vol_velocity':
                mask = df['vol_velocity'] >= thresh
            elif feature == 'max_dev_holding':
                mask = df['dev_holding_1m'] <= thresh
                
            passed = df[mask]
            if len(passed) < 10: continue
            
            win_rate = passed['is_profitable'].mean() * 100
            rug_rate = passed['is_rug'].mean() * 100
            ev = passed['roi_after_1m'].mean()
            pass_rate = len(passed) / len(df) * 100
            
            print(f"{feature} {thresh}: Win={win_rate:.1f}% Rug={rug_rate:.1f}% EV={ev:.2f}x (Pass {pass_rate:.1f}%)")

    # Combined Strategy (Optimized - Strict)
    print("\n--- Combined Strategy Test (Strict) ---")
    mask_strict = (
        (df['unique_signers_1m'] >= 20) &
        (df['bundled_buy_count_1m'] <= 2) &
        (df['sniper_count_10s'] <= 30) &
        (df['top10_concentration_1m'] <= 50) &
        (df['vol_velocity'] >= 1.2)
    )
    print_strategy_stats(df, mask_strict, "Strict")

    # Combined Strategy (Balanced)
    print("\n--- Combined Strategy Test (Balanced) ---")
    mask_balanced = (
        (df['unique_signers_1m'] >= 10) &
        (df['bundled_buy_count_1m'] <= 5) &
        (df['sniper_count_10s'] <= 50) &
        (df['top10_concentration_1m'] <= 70) &
        (df['vol_velocity'] >= 1.0)
    )
    print_strategy_stats(df, mask_balanced, "Balanced")

    # Combined Strategy (Loose)
    print("\n--- Combined Strategy Test (Loose) ---")
    mask_loose = (
        (df['unique_signers_1m'] >= 5) &
        (df['bundled_buy_count_1m'] <= 10) &
        (df['top10_concentration_1m'] <= 80)
    )
    print_strategy_stats(df, mask_loose, "Loose")

def print_strategy_stats(df, mask, name):
    passed = df[mask]
    if len(passed) > 0:
        win_rate = passed['is_profitable'].mean() * 100
        rug_rate = passed['is_rug'].mean() * 100
        survival_15m = passed['is_alive_15m'].mean() * 100
        survival_1h = passed['is_alive_1h'].mean() * 100
        ev = passed['roi_after_1m'].mean()
        pass_rate = len(passed) / len(df) * 100
        print(f"{name}: Win={win_rate:.1f}% Rug={rug_rate:.1f}% EV={ev:.2f}x (Pass {pass_rate:.1f}%)")
        print(f"    Survival: 15m={survival_15m:.1f}% 1h={survival_1h:.1f}%")
        print(f"    Total Signals: {len(passed)} / {len(df)}")
    else:
        print(f"{name}: No tokens passed.")

def analyze_rug_predictors(df):
    print("\n=== Rug Pull Predictors ===")
    
    # 1. Bundled Buys
    print("\n--- Bundled Buys vs Rug Rate ---")
    for thresh in [0, 1, 2, 3, 5, 10]:
        mask = df['bundled_buy_count_1m'] > thresh
        subset = df[mask]
        if len(subset) < 10: continue
        rug_rate = subset['is_rug'].mean() * 100
        fail_rate = subset['is_fail'].mean() * 100
        print(f"Bundled > {thresh}: Rug Rate={rug_rate:.1f}% Fail Rate={fail_rate:.1f}% (Count={len(subset)})")

    # 2. Sniper Count
    print("\n--- Sniper Count vs Rug Rate ---")
    for thresh in [0, 5, 10, 20, 50]:
        mask = df['sniper_count_10s'] > thresh
        subset = df[mask]
        if len(subset) < 10: continue
        rug_rate = subset['is_rug'].mean() * 100
        fail_rate = subset['is_fail'].mean() * 100
        print(f"Snipers > {thresh}: Rug Rate={rug_rate:.1f}% Fail Rate={fail_rate:.1f}% (Count={len(subset)})")

    # 3. Dev Activity (Selling early)
    print("\n--- Dev Early Sell vs Rug Rate ---")
    # Check if dev sold within first 5 mins
    # We need to parse timestamps first
    df['first_seen'] = pd.to_datetime(df['first_seen_ts'], format='mixed')
    df['dev_sell'] = pd.to_datetime(df['dev_first_sell_ts'], format='mixed')
    
    # Calculate time to sell in minutes
    df['dev_sell_min'] = (df['dev_sell'] - df['first_seen']).dt.total_seconds() / 60.0
    
    # Filter: Dev sold within X minutes
    for min_limit in [1, 5, 15, 60]:
        mask = (df['dev_sell_min'] <= min_limit)
        subset = df[mask]
        if len(subset) < 10: continue
        rug_rate = subset['is_rug'].mean() * 100
        fail_rate = subset['is_fail'].mean() * 100
        print(f"Dev Sold < {min_limit}m: Rug Rate={rug_rate:.1f}% Fail Rate={fail_rate:.1f}% (Count={len(subset)})")

    # 4. Concentration
    print("\n--- Top 10 Concentration vs Rug Rate ---")
    for thresh in [20, 30, 50, 70, 90]:
        mask = df['top10_concentration_1m'] > thresh
        subset = df[mask]
        if len(subset) < 10: continue
        rug_rate = subset['is_rug'].mean() * 100
        fail_rate = subset['is_fail'].mean() * 100
        print(f"Top10 > {thresh}%: Rug Rate={rug_rate:.1f}% Fail Rate={fail_rate:.1f}% (Count={len(subset)})")

def main():
    try:
        df = load_data()
        if df.empty:
            print("Database is empty.")
            return
            
        print(f"Loaded {len(df)} tokens.")
        df = prepare_features(df)
        
        analyze_correlations(df)
        analyze_rug_predictors(df)
        analyze_lifespan_predictors(df)
        optimize_thresholds(df)
        
    except Exception as e:
        print(f"Error: {e}")

def analyze_lifespan_predictors(df):
    print("\n=== Lifespan Predictors (Survival > 1h) ===")
    
    # Parse 5m Buckets (JSON)
    # We want to see if the *first* 5m bucket predicts the rest.
    # Actually, we are at T=1m usually. But let's see if T=5m stats help.
    
    # Define Target: Survived 1h
    # We already have 'is_alive_1h' from trade counts.
    
    # Features to test:
    # 1. T=1m stats (Velocity, Signers, Bundles)
    # 2. T=5m stats (Volume, Count) - Need to parse if we want to use them.
    
    # Let's focus on T=1m predictors first, as that's our decision point.
    
    features = [
        'unique_signers_1m', 'vol_velocity', 'bundled_buy_count_1m', 
        'top10_concentration_1m', 'sniper_count_10s'
    ]
    
    for feature in features:
        print(f"\n--- {feature} vs 1h Survival ---")
        
        # Determine bins/thresholds dynamically
        if 'concentration' in feature:
            thresholds = [20, 50, 70, 90]
            op = '<=' # Lower is better
        elif 'bundled' in feature or 'sniper' in feature:
            thresholds = [0, 2, 5, 10, 30]
            op = '<=' # Lower is better
        else:
            thresholds = [1.0, 1.5, 2.0, 5, 10, 20]
            op = '>=' # Higher is better
            
        for thresh in thresholds:
            if op == '>=':
                mask = df[feature] >= thresh
            else:
                mask = df[feature] <= thresh
                
            subset = df[mask]
            if len(subset) < 10: continue
            
            survival_rate = subset['is_alive_1h'].mean() * 100
            baseline_rate = df['is_alive_1h'].mean() * 100
            lift = survival_rate / baseline_rate if baseline_rate > 0 else 0
            
            print(f"{feature} {op} {thresh}: Survival={survival_rate:.1f}% (Baseline={baseline_rate:.1f}%) Lift={lift:.2f}x (Count={len(subset)})")

if __name__ == "__main__":
    main()
