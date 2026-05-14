import os, sys
from typing import List, Dict, Any
import pandas as pd
import mplfinance as mpf
import pickle
import numpy as np

THIS_PATH = os.path.dirname(os.path.abspath(__file__))
sys.path.append(THIS_PATH + '/..')

from data_store import db_store
from data_store.db_store import DB_VERSION
from data_store.pumpfun_event_types import *
import asyncio
import matplotlib
matplotlib.use('Qt5Agg')  # sudo apt install python3-pyqt5 qtbase5-dev qt5-qmake libxcb-xinerama0
import matplotlib.pyplot as plt


class DataProc:
    def __init__(self):
        self.total_supply = 1_000_000_000  # 1 billion tokens
    
    def process(self, data: dict):
        # merge data from pumpfun and raydium trades
        #  - calculate market cap data
        df_out = pd.DataFrame()
        
        ## pumpfun trades
        df = data[db_store.get_table_name_from_class(PumpFunTradeEvent)]
        # current_price = df['virtual_sol_reserves'] / df['virtual_token_reserves']
        # market_cap_before = current_price * self.total_supply
        new_virtual_sol_reserves = df['virtual_sol_reserves'] + df['sol_amount'] * df['is_buy'].astype(int) - df['sol_amount'] * (~df['is_buy']).astype(int)
        new_virtual_token_reserves = df['virtual_token_reserves'] - df['token_amount'] * df['is_buy'].astype(int) + df['token_amount'] * (~df['is_buy']).astype(int)
        # Calculate new price and market cap
        df_out['tsz'] = pd.to_datetime(df['tsz'])
        #df_out['market_cap'] = new_virtual_sol_reserves / new_virtual_token_reserves * self.total_supply
        df_out['price'] = df['sol_amount'] / df['token_amount']
        df_out['volume'] = df['sol_amount']
        
        ## raydium trades if any
        raydium_swap_table_name = db_store.get_table_name_from_class(RaydiumV4SwapEvent)
        if raydium_swap_table_name in data:
            df = data[raydium_swap_table_name]
            df_swap = pd.DataFrame()
            df_swap['tsz'] = pd.to_datetime(df['tsz'])
            df_swap['price'] = np.where(df['is_buy'], df['amount_in'] / df['amount_out'], df['amount_out'] / df['amount_in'])
            df_swap['volume'] = np.where(df['is_buy'], df['amount_in'], df['amount_out'])
            df_out = pd.concat([df_out, df_swap[df_out.columns]], ignore_index=True)


        df_out.set_index('tsz', inplace=True)
        data['trades'] = df_out
    
    def calculate_bonding_status(self, data: dict) -> pd.DataFrame:
        """Calculate bonding status for the mint"""
        df = data[db_store.get_table_name_from_class(PumpFunTradeEvent)]
        
        token_amount_signed = df['token_amount'] * (~df['is_buy']).astype(int) - df['token_amount'] * df['is_buy'].astype(int)
        df['token_amount_cumsum'] = token_amount_signed.cumsum()
        
        print(df.iloc[-1].token_amount_cumsum/1000000)
        return df

    def plot_ohlc(self, data):
        df = data['trades']
        
        # Resample to get OHLC data
        ival = '1min'   # 1s / 1min
        ohlc = df['price'].resample(ival).ohlc()
        # Resample the 'sol_amount' column to get the sum for volume
        volume = df['volume'].resample(ival).sum()
        # Combine the OHLC and volume into a single DataFrame
        ohlc['volume'] = volume
        mpf.plot(ohlc, type='candle', volume=True, savefig='testsave.png')
    
    def plot_trades(self, data_dict: Dict[str, pd.DataFrame]):
        """
        Plots trade prices for the given mint using pre-fetched trade data.
        The trade price is computed as virtual_sol_reserves / virtual_token_reserves
        from the PumpFunTrade events DataFrame.
        """
        trade_table = db_store.get_table_name_from_class(PumpFunTradeEvent)
        if trade_table not in data_dict:
            print("No trade data available")
            return
        df = data_dict[trade_table]
        if df.empty:
            print("Trade data is empty")
            return
        df["tsz"] = pd.to_datetime(df["tsz"])
        if "virtual_sol_reserves" in df.columns and "virtual_token_reserves" in df.columns:
            df["price"] = df["virtual_sol_reserves"] / df["virtual_token_reserves"]
        else:
            print("Required columns for computing trade price not found.")
            return
        
        plt.figure(figsize=(10,6))
        plt.scatter(df["tsz"], df["price"], color="blue", label="Trade Price")
        plt.xlabel("Time")
        plt.ylabel("Trade Price")
        plt.title(f"Trade Prices")
        plt.legend()
        plt.grid(True)
        plt.show()

    async def download_and_export_data(self, mint: str):
        """
        Downloads data from all tables with names starting with DB_VERSION.
        For events with a 'mint' column (PumpFunTrade, PumpFunCreate, PumpFunComplete, PumpFunRemoveLiquidity),
        the query filters by mint = provided mint.
        For events without a 'mint' column (RaydiumV4AddLiquidity, RaydiumV4RemoveLiquidity, RaydiumV4WithdrawPnl, RaydiumV4Swap),
        if a single RaydiumV4Initialize2 row exists with pc_mint = mint, its pool_pc_token_account is used for filtering.
        The output is a dictionary mapping table names to their corresponding DataFrames,
        and is exported using pickle into an export folder with the filename as the mint address.
        """
        export_folder = os.path.join(THIS_PATH, "export")
        os.makedirs(export_folder, exist_ok=True)
        export_filename = os.path.join(export_folder, f"{mint}.pkl")
        if os.path.exists(export_filename):
            print(f"Data already exported to {export_filename}, loading data.")
            with open(export_filename, 'rb') as f:
                result_dict = pickle.load(f)
            return result_dict
        await db_store.connect_to_db()
        
        result_dict: Dict[str, pd.DataFrame] = {}
        pool_token_account = None  # To be obtained from RaydiumV4Initialize2 table
        
        try:
            # Get all tables starting with DB_VERSION
            tables = await db_store.db_conn.fetch("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name LIKE $1
            """, f"{DB_VERSION}_%")
            #print("Available tables:", [t['table_name'] for t in tables])
            
            # First, attempt to retrieve the single RaydiumV4Initialize2Event row with pc_mint = mint
            init_table_name = db_store.get_table_name_from_class(RaydiumV4Initialize2Event)
            init_query = f"""
                SELECT *
                FROM {init_table_name}
                WHERE pc_mint = $1
            """
            init_records = await db_store.db_conn.fetch(init_query, mint)
            if init_records:
                # Only one row should exist; if more, take the first.
                if len(init_records) != 1:
                    print('ERROR: no ray init')
                    return
                init_row = init_records[0]
                pool_token_account = init_row.get("pool_pc_token_account")
                columns = init_row.keys()
                df_init = pd.DataFrame(init_records, columns=columns)
                result_dict[init_table_name] = df_init
            
            # Process the remaining events using known event types
            from data_store import pumpfun_event_types
            available_tables = {t['table_name'] for t in tables}
            for event in pumpfun_event_types.KNOWN_EVENT_TYPES:
                # Skip RaydiumV4Initialize2 as it's already processed
                if event._event_name == "RaydiumV4Initialize2":
                    continue
                expected_table = db_store.get_table_name(event._event_name)
                if expected_table not in available_tables:
                    continue
                # Determine filter field based on whether the event has a 'mint' column
                if 'mint' in event.__annotations__:
                    query = f"""
                        SELECT *
                        FROM {expected_table}
                        WHERE mint = $1
                    """
                    records = await db_store.db_conn.fetch(query, mint)
                else:
                    if pool_token_account is None:
                        continue
                    query = f"""
                        SELECT *
                        FROM {expected_table}
                        WHERE pool_pc_token_account = $1
                        ORDER BY slot, tsz;
                    """
                    records = await db_store.db_conn.fetch(query, pool_token_account)
                if records:
                    df = pd.DataFrame(records, columns=records[0].keys())
                    result_dict[expected_table] = df
                        
            # Export the result dictionary using pickle
            with open(export_filename, 'wb') as f:
                pickle.dump(result_dict, f)
            print(f"Data exported to {export_filename}")
            
        except Exception as e:
            print(f"Error: {e}")
            
        finally:
            await db_store.disconnect_db()
        return result_dict

if __name__ == "__main__":
    async def main():
        mint_address = "GK72tG5CFR2nVa5DSzx1J2x7Pa6wkVnpw1wBfvvNpump"
        dp = DataProc()
        data_dict = await dp.download_and_export_data(mint_address)
        dp.process(data_dict)
        dp.plot_ohlc(data_dict)

    asyncio.run(main())