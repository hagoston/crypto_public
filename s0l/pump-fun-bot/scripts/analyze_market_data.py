import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

def analyze_market_data(db_path='inspector_data.db'):
    print(f"Connecting to {db_path}...")
    conn = sqlite3.connect(db_path)
    
    query = "SELECT * FROM market_analysis"
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    print(f"Loaded {len(df)} rows.")
    
    # Basic Cleanup
    df['is_rug'] = df['is_rug'].astype(bool)
    
    # Define Analysis Functions
    def analyze_feature(feature_name, bins=10, q=None):
        print(f"\n--- Analysis: {feature_name} ---")
        
        # Create bins
        if q:
            try:
                df['bin'] = pd.qcut(df[feature_name], q=q, duplicates='drop')
            except ValueError:
                df['bin'] = pd.cut(df[feature_name], bins=bins)
        else:
            df['bin'] = pd.cut(df[feature_name], bins=bins)
            
        stats = df.groupby('bin', observed=True).agg({
            'is_rug': ['count', 'mean'],
            'max_drawdown_pct': 'mean'
        })
        
        stats.columns = ['count', 'rug_prob', 'avg_drawdown']
        stats['rug_prob'] = stats['rug_prob'] * 100
        
        print(stats)
        return stats

    # 1. Top 10 Concentration Analysis
    # We expect high concentration -> High Rug Probability
    analyze_feature('top10_concentration_1m', bins=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100])

    # 2. Sniper Count Analysis (T=10s)
    # High sniper count -> ?
    # Let's use quantiles as this might be skewed
    analyze_feature('sniper_count_10s', q=10)

    # 3. Volume 1m Analysis
    # Very low volume -> Dust/Fail? High volume -> ?
    analyze_feature('vol_1m_sol', q=10)
    
    # 4. Holder Count 1m Analysis
    analyze_feature('holder_count_1m', q=10)
    
    # 5. Dev Holding 1m
    analyze_feature('dev_holding_1m', bins=[0, 1, 5, 10, 20, 50, 100])

    # --- Derived Features ---
    print("\n--- Derived Features Analysis ---")
    
    # 6. Volume per Holder
    # High volume per holder might indicate wash trading or few whales
    df['vol_per_holder'] = df['vol_1m_sol'] / df['holder_count_1m'].replace(0, 1)
    analyze_feature('vol_per_holder', q=10)
    
    # 7. Sniper Ratio
    # Portion of early holders that were snipers
    df['sniper_ratio'] = df['sniper_count_10s'] / df['holder_count_1m'].replace(0, 1)
    # Clip to 1.0 just in case
    df['sniper_ratio'] = df['sniper_ratio'].clip(upper=1.0)
    analyze_feature('sniper_ratio', bins=[0, 0.1, 0.2, 0.3, 0.5, 0.8, 1.0])

    print("\n--- Summary of Recommendations ---")
    print("Based on the tables above, look for 'elbows' where Rug Probability jumps significantly.")

if __name__ == "__main__":
    try:
        analyze_market_data()
    except ImportError:
        print("Pandas/Matplotlib/Seaborn not found. Please install them: pip install pandas matplotlib seaborn")
    except Exception as e:
        print(f"An error occurred: {e}")
