import sys, os
import polars as pl
import time
import asyncio
import pandas as pd
import numpy as np

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(THIS_DIR, '..')))

from utils.logger_factory import get_logger
from trader.data.data_loader import DataLoader
from data_proc.token_data_fetcher import TokenDataFetcher
from config import LAMPORTS_PER_SOL, DEFAULT_TOKEN_DECIMALS, TOTAL_SUPPLY


def set_ts_index(df):
    df['timestamp'] = pd.to_datetime(df['tsz'], unit='s', errors='coerce')
    df = df.drop(columns=['tsz'])
    df.set_index('timestamp', inplace=True)
    return df

async def main():
    data_loader = DataLoader('trader/historical_data')

    # --- Example usage for loading by a single date ---
    print("\n--- Loading trades for a single date ---")
    date_to_load = "2025-09-01"
    start_time = time.time()
    trades_lf_date = data_loader.load_trades_for_date(date_to_load)
    if trades_lf_date is None:
        print(f"No trade data found for date {date_to_load}.")
        return
        
    trades_df_date = trades_lf_date.collect(engine='streaming')
    print(f"\nLoaded {len(trades_df_date)} trades for date {date_to_load}.")

    # Define the patterns to search for
    patterns = ['bonk', 'pump', 'ray']

    selected_mints = []
    # find mints with highest trade counts
    for pattern in patterns:
        # Filter for mints ending with the current pattern
        pattern_mints_df = trades_df_date.filter(pl.col('mint').str.ends_with(pattern))

        if not pattern_mints_df.is_empty():
            # Group by mint and count the number of trades
            mint_counts = pattern_mints_df.group_by('mint').agg(pl.len().alias('trade_count'))

            # Find the mint with the highest trade count
            most_traded = mint_counts.sort('trade_count', descending=True)[1]

            if not most_traded.is_empty():
                mint_address = most_traded.select('mint').item()
                trade_count = most_traded.select('trade_count').item()
                print(f"\n--- Most Traded '{pattern}' Mint ---")
                print(f"Mint Address: {mint_address}")
                print(f"Number of Trades: {trade_count}")
                selected_mints.append(mint_address)
            else:
                print(f"\n--- No '{pattern}' mints found to determine the most traded one. ---")
        else:
            print(f"\n--- No trades found for mints ending with '{pattern}'. ---")

    data_fetcher = TokenDataFetcher(result_in_mcap=True, result_in_usd=False)
    cache_base_dir = "test/reserves"
    os.makedirs(cache_base_dir, exist_ok=True)

    try:
        for mint in selected_mints:

            if 'pump' not in mint :
                continue
            print(f"\n--- Processing data for mint: {mint} ---")
            mint_cache_dir = os.path.join(cache_base_dir, mint)
            os.makedirs(mint_cache_dir, exist_ok=True)

            # File paths for cached data
            loader_cache_path = os.path.join(mint_cache_dir, f"dataloader_trades.parquet")
            fetcher_cache_path = os.path.join(mint_cache_dir, f"tokenfetcher_trades.parquet")
            raw_bc_cache_path = os.path.join(mint_cache_dir, f"raw_bc_trades.parquet")
            raw_amm_cache_path = os.path.join(mint_cache_dir, f"raw_amm_trades.parquet")

            # 1. Get data from DataLoader (Parquet files)
            if os.path.exists(loader_cache_path):
                print("Loading from DataLoader cache...")
                trades_df_loader = pl.read_parquet(loader_cache_path)
                print(f"  Loaded {len(trades_df_loader)} trades from cache.")
            else:
                print("Fetching from DataLoader...")
                trades_lf_loader = data_loader.load_trades_for_mint(mint)
                if trades_lf_loader is not None:
                    trades_df_loader = trades_lf_loader.collect()
                    print(f"  DataLoader found {len(trades_df_loader)} trades.")
                    trades_df_loader.write_parquet(loader_cache_path)
                    print(f"  Saved to cache: {loader_cache_path}")
                else:
                    trades_df_loader = pl.DataFrame()
                    print("  DataLoader found no trades.")

            # 2. Get data from TokenDataFetcher (Database)
            if os.path.exists(fetcher_cache_path):
                print("Loading from TokenDataFetcher cache...")
                trades_df_fetcher = pd.read_parquet(fetcher_cache_path)
                print(f"  Loaded {len(trades_df_fetcher)} trades from cache.")
            else:
                print("Fetching from TokenDataFetcher...")
                try:
                    trades_df_fetcher = await data_fetcher.fetch_trades(mint)
                    if not trades_df_fetcher.empty:
                        print(f"  TokenDataFetcher found {len(trades_df_fetcher)} trades.")
                        trades_df_fetcher.to_parquet(fetcher_cache_path)
                        print(f"  Saved to cache: {fetcher_cache_path}")
                    else:
                        print("  TokenDataFetcher found no trades.")
                except Exception as e:
                    print(f"  An error occurred with TokenDataFetcher: {e}")
                    trades_df_fetcher = pd.DataFrame()

            # 3. Get raw data using the new function
            if os.path.exists(raw_bc_cache_path) and os.path.exists(raw_amm_cache_path):
                print("Loading raw data from cache...")
                df_bc = pd.read_parquet(raw_bc_cache_path)
                df_amm = pd.read_parquet(raw_amm_cache_path)
                print(f"  Loaded {len(df_bc)} raw bonding curve trades and {len(df_amm)} raw AMM trades from cache.")
            else:
                print("Fetching raw data for bonding curve and AMM trades...")
                try:
                    raw_trades_dfs = await data_fetcher.fetch_raw_data_for_mint(mint)
                    if raw_trades_dfs:
                        df_bc, df_amm = raw_trades_dfs
                        if not df_bc.empty:
                            print(f"  Found {len(df_bc)} raw bonding curve trades.")
                            df_bc.to_parquet(raw_bc_cache_path)
                            print(f"  Saved to cache: {raw_bc_cache_path}")
                        else:
                            print("  Found no raw bonding curve trades.")
                        if not df_amm.empty:
                            print(f"  Found {len(df_amm)} raw AMM trades.")
                            df_amm.to_parquet(raw_amm_cache_path)
                            print(f"  Saved to cache: {raw_amm_cache_path}")
                        else:
                            print("  Found no raw AMM trades.")
                except Exception as e:
                    print(f"  An error occurred with fetch_raw_data_for_mint: {e}")

            df_bc['price'] = df_bc['sol_amount'] / df_bc['token_amount']
            df_bc['price_res'] = df_bc['virtual_sol_reserves'] / df_bc['virtual_token_reserves']
            # check quantity db vs file
            df_bc = set_ts_index(df_bc)
            df_amm = set_ts_index(df_amm)

            # Convert trades_df_loader to pandas for easier processing
            trades_df_loader_pd = trades_df_loader.to_pandas()
            trades_df_loader_pd['timestamp'] = pd.to_datetime(trades_df_loader_pd['timestamp'])
            trades_df_loader_pd.set_index('timestamp', inplace=True)

            # Calculate expected token quantity
            trades_df_loader_pd['quantity_token'] = (
                LAMPORTS_PER_SOL * 10**DEFAULT_TOKEN_DECIMALS * trades_df_loader_pd['quantity'] / trades_df_loader_pd['price']
            ).fillna(0)

            # Separate trades based on bonding curve vs AMM
            last_bc_ts = df_bc.index.max()
            
            bc_trades = trades_df_loader_pd[trades_df_loader_pd.index <= last_bc_ts]
            amm_trades = trades_df_loader_pd[trades_df_loader_pd.index > last_bc_ts]

            # Merge with db data
            merged_bc = pd.merge(bc_trades, df_bc[['token_amount']], left_index=True, right_index=True, how='left')
            merged_amm = pd.merge(amm_trades, df_amm[['amount_out', 'amount_in']], left_index=True, right_index=True, how='left')

            # Check for missing data
            if merged_bc['token_amount'].isnull().any() or merged_amm.isnull().values.any():
                print('ERROR:: data not found for some trades')
                # Optionally, print the trades that couldn't be matched
                print("Unmatched BC trades:", merged_bc[merged_bc['token_amount'].isnull()])
                print("Unmatched AMM trades:", merged_amm[merged_amm.isnull().values.any()])
                exit(0)

            # Get db token quantity
            merged_bc['db_token_quantity'] = merged_bc['token_amount']
            merged_amm['db_token_quantity'] = np.where(merged_amm['is_buy'], merged_amm['amount_out'], merged_amm['amount_in'])

            # Combine results
            all_trades = pd.concat([merged_bc, merged_amm])

            # Check for mismatches
            # Handle cases where db_token_quantity might be a series/list due to duplicate timestamps
            def check_mismatch(row):
                quantity_token = row['quantity_token']
                db_quantities = row['db_token_quantity']
                if isinstance(db_quantities, (list, pd.Series)):
                    return not any(abs(int(dbq) - quantity_token) < 1 for dbq in db_quantities)
                else:
                    return abs(int(db_quantities) - quantity_token) > 1

            all_trades['mismatch'] = all_trades.apply(check_mismatch, axis=1)

            if all_trades['mismatch'].any():
                print('ERROR:: amount mismatch found in one or more trades')
                print("Mismatched trades:")
                print(all_trades[all_trades['mismatch']])
                exit(1)
            
            print("\n--- All quantities match between file and DB! ---")
                    
    finally:
        await data_fetcher.close()

if __name__ == "__main__":
    asyncio.run(main())

'''
2025.09.01. more buy in one transaction -> same ts
https://solscan.io/tx/Bai6uGkzm3nMNttBV8YmRUJtKHhka7dF3kbujGWHg1oKRPsPDiyWqPVfDkbaSrAKj3YDmQC2DAEFsJUJV9RiGa7

SELECT * FROM public.v00_pump_fun_trade_events
where slot in (363903676, 363917739) and mint = '14gZxhDphJyqGScsyvnyF7UvgpFF9LiM5etyibaWpump'
LIMIT 100

'''