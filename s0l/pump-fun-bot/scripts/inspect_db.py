import sqlite3
import pandas as pd

def inspect_db():
    try:
        conn = sqlite3.connect('inspector_data.db')
    
        # Read market_analysis table
        df = pd.read_sql_query("SELECT * FROM market_analysis", conn)
        
        print("Columns:", df.columns)
        print("\nSample Data (New Metrics):")
        # Show new columns if they exist
        new_cols = ['bundled_buy_count_1m', 'is_flash_rug', 'price_at_1m_sol', 'max_price_after_1m_sol']
        existing_cols = [c for c in new_cols if c in df.columns]
        if existing_cols:
            print(df[['mint_address'] + existing_cols].head())
        else:
            print("New columns not found!")
            
        # Check if any rows have bundled buys > 0
        if 'bundled_buy_count_1m' in df.columns:
            print(f"\nRows with bundled_buy_count_1m > 0: {len(df[df['bundled_buy_count_1m'] > 0])}")
            
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_db()
