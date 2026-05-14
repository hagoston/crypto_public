import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

import asyncpg
import pandas as pd
import numpy as np
import time
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import mplfinance as mpf
import asyncio
from typing import Optional, Dict, Union, List
from sol_price import BinancePriceFetcher
from datetime import datetime, timezone
from data_store import db_store, pumpfun_event_types
from config import (
    PG_CONNECTION, SOLANA_RPC_URL, # Assuming RPC URL is in config
    LAMPORTS_PER_SOL, DEFAULT_TOKEN_DECIMALS, TOTAL_SUPPLY,
    SOL, USD1
)
from utils.logger_factory import get_logger

log = get_logger('TokenDataFetcher')
# Configure logging properly if not already done elsewhere
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Determine table names based on DB_VERSION (These might not exist in older schemas)
PUMP_TRADE_TABLE = db_store.get_table_name_from_class(pumpfun_event_types.PumpFunTradeEvent)
# Potential tables that might be missing in older DBs
PUMP_AMM_TRADE_TABLE = db_store.get_table_name_from_class(pumpfun_event_types.PumpFunAmmTradeEvent)
PUMP_AMM_CREATE_TABLE = db_store.get_table_name_from_class(pumpfun_event_types.PumpFunAmmCreatePoolEvent)
RAYDIUM_SWAP_TABLE = db_store.get_table_name_from_class(pumpfun_event_types.RaydiumV4SwapEvent)
RAYDIUM_INIT_TABLE = db_store.get_table_name_from_class(pumpfun_event_types.RaydiumV4Initialize2Event)
PUMP_CREATE_TABLE = db_store.get_table_name_from_class(pumpfun_event_types.PumpFunCreateEvent)
RAYDIUM_LAUNCHPAD_POOL_CREATE_TABLE = db_store.get_table_name_from_class(pumpfun_event_types.RaydiumLaunchpadPoolCreateEvent)
RAYDIUM_LAUNCHPAD_TRADE_TABLE = db_store.get_table_name_from_class(pumpfun_event_types.RaydiumLaunchpadTradeEvent)
RAYDIUM_CPMM_SWAP_TABLE = db_store.get_table_name_from_class(pumpfun_event_types.RaydiumCPMMSwapEvent)


class TokenDataFetcher:
    
    def __init__(self, 
                 pg_conn_str: str = PG_CONNECTION,
                 result_in_mcap = True,
                 result_in_usd = False):
        """
        Initializes the fetcher with database connection string and Solana RPC endpoint.

        Args:
            pg_conn_str: PostgreSQL connection string.
            rpc_endpoint: Solana RPC endpoint URL for SlotTimeMapper.
        """
        self.sol_price_cache = None
        self.pg_conn_str = pg_conn_str
        self._pool: Optional[asyncpg.Pool] = None # Connection pool
        self._table_cache: Dict[str, bool] = {} # Cache for table existence checks
        self.sol_price_fetcher = BinancePriceFetcher()  # default is 1d SOLUSDT
        self.result_in_mcap = result_in_mcap
        self.result_in_usd = result_in_usd
        log.info("TokenDataFetcher initialized.")


    async def _connect(self):
        """Establishes the database connection pool."""
        if not self._pool:
            try:
                self._pool = await asyncpg.create_pool(self.pg_conn_str, min_size=1, max_size=10)
                log.info("Database connection pool established.")
                # Reset table cache on new pool creation
                self._table_cache = {}
            except Exception as e:
                log.error(f"Error connecting to database: {e}")
                self._pool = None # Ensure pool is None on error
                raise # Re-raise the exception

    async def close(self, save_slot_cache: bool = True):
        """Closes the database pool and the SlotTimeMapper client."""
        if self._pool:
            try:
                await self._pool.close()
                log.info("Database connection pool closed.")
            except Exception as e:
                log.error(f"Error closing database pool: {e}")
            finally:
                self._pool = None

    async def _table_exists(self, conn: asyncpg.Connection, table_name: str) -> bool:
        """Checks if a table exists in the database, using a cache."""
        if table_name in self._table_cache:
            return self._table_cache[table_name]

        query = """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = $1
            );
        """
        try:
            exists = await conn.fetchval(query, table_name)
            self._table_cache[table_name] = exists
            if not exists:
                log.warning(f"Table '{table_name}' does not exist in the current database.")
            return exists
        except Exception as e:
            log.error(f"Error checking existence for table {table_name}: {e}")
            self._table_cache[table_name] = False # Assume doesn't exist on error
            return False


    async def _find_amm_pool(self, conn: asyncpg.Connection, mint_addresses: List[str]) -> Dict[str, tuple[str, str]]:
        """
        Finds AMM pool addresses and types ('pump' or 'raydium') for a list of mint addresses.
        Returns a dictionary mapping mint_address to (pool_address, pool_type).
        """
        found_pools: Dict[str, tuple[str, str]] = {}
        if not mint_addresses:
            return found_pools

        # Check PumpSwap AMM (if table exists)
        if await self._table_exists(conn, PUMP_AMM_CREATE_TABLE):
            query_pump = f"SELECT base_mint, pool FROM {PUMP_AMM_CREATE_TABLE} WHERE base_mint = ANY($1)"
            try:
                records = await conn.fetch(query_pump, mint_addresses)
                for record in records:
                    mint, pool = record['base_mint'], record['pool']
                    if mint and pool and mint not in found_pools:
                        # log.info(f"Found PumpSwap AMM pool {pool} for mint {mint}")
                        found_pools[mint] = (pool, 'pump')
            except Exception as e:
                log.error(f"Error querying {PUMP_AMM_CREATE_TABLE} for {mint_addresses}: {e}")

        # Find mints that are still not found
        remaining_mints = [m for m in mint_addresses if m not in found_pools]

        # Fallback to Raydium (if table exists)
        if remaining_mints and await self._table_exists(conn, RAYDIUM_INIT_TABLE):
            # Assuming pc_mint is the token mint for Raydium pools
            query_raydium = f"SELECT pc_mint, pool_pc_token_account FROM {RAYDIUM_INIT_TABLE} WHERE pc_mint = ANY($1)"
            try:
                records = await conn.fetch(query_raydium, remaining_mints)
                for record in records:
                    mint, pool = record['pc_mint'], record['pool_pc_token_account']
                    if mint and pool and mint not in found_pools:
                        # log.info(f"Found Raydium AMM pool {pool} for mint {mint}")
                        found_pools[mint] = (pool, 'raydium')
            except Exception as e:
                log.error(f"Error querying {RAYDIUM_INIT_TABLE} for {remaining_mints}: {e}")

        mints_not_found = [m for m in mint_addresses if m not in found_pools]
        log.debug(f"bounding found for {len(found_pools)}, no bounding pool for {len(mints_not_found)} mints")

        return found_pools

    async def _classify_mints(self, conn: asyncpg.Connection, mint_addresses: List[str]) -> Dict[str, str]:
        """
        Classifies mints as 'pumpfun' or 'raydium_launchpad' based on their creation event.
        Returns a dictionary mapping mint_address to its type.
        """
        classification: Dict[str, str] = {}
        if not mint_addresses:
            return classification

        # Check pump.fun create events
        if await self._table_exists(conn, PUMP_CREATE_TABLE):
            query_pump = f"SELECT mint FROM {PUMP_CREATE_TABLE} WHERE mint = ANY($1)"
            try:
                records = await conn.fetch(query_pump, mint_addresses)
                for record in records:
                    mint = record['mint']
                    if mint not in classification:
                        classification[mint] = 'pumpfun'
            except Exception as e:
                log.error(f"Error querying {PUMP_CREATE_TABLE} for mint classification: {e}")

        remaining_mints = [m for m in mint_addresses if m not in classification]

        # Check Raydium launchpad create events
        if remaining_mints and await self._table_exists(conn, RAYDIUM_LAUNCHPAD_POOL_CREATE_TABLE):
            query_raydium = f"SELECT mint FROM {RAYDIUM_LAUNCHPAD_POOL_CREATE_TABLE} WHERE mint = ANY($1)"
            try:
                records = await conn.fetch(query_raydium, remaining_mints)
                for record in records:
                    mint = record['mint']
                    if mint not in classification:
                        classification[mint] = 'raydium_launchpad'
            except Exception as e:
                log.error(f"Error querying {RAYDIUM_LAUNCHPAD_POOL_CREATE_TABLE} for mint classification: {e}")
        
        unclassified_mints = [m for m in mint_addresses if m not in classification]
        if unclassified_mints:
            # It's possible a token is on a standard AMM without a create event in our DB, so this is a warning not an error.
            log.warning(f"Could not classify {len(unclassified_mints)} mints via create events: {unclassified_mints}")

        return classification

    async def fetch_pumpfun_amm_raw_data(self, mint_address: str) -> pd.DataFrame:
        """
        Fetches and combines raw db data from PumpFunTradeEvent and PumpFunAmmTradeEvent.
        Returns DataFrame with columns: tsz, slot, is_buy, amount_in, amount_out, base_reserves, token_reserves
        
        Args:
            mint_address: Token mint address to query
            
        Returns:
            pd.DataFrame: Combined trade data with required columns
        """
        default_df = pd.DataFrame(columns=['tsz', 'slot', 'is_buy', 'amount_in', 'amount_out', 'base_reserves', 'token_reserves'])
        if not self._pool:
            await self._connect()

            if not self._pool:
                log.error("Database pool not initialized")
                return default_df
            
        async with self._pool.acquire() as conn:
            # Check if required tables exist
            if not await self._table_exists(conn, PUMP_TRADE_TABLE):
                log.warning(f"Table {PUMP_TRADE_TABLE} does not exist")
                return default_df
                
            # Query PumpFunTradeEvent data
            query_pump = f"""
                SELECT
                    tsz,
                    slot,
                    is_buy,
                    CASE WHEN is_buy THEN sol_amount ELSE token_amount END as amount_in,
                    CASE WHEN is_buy THEN token_amount ELSE sol_amount END as amount_out,
                    virtual_sol_reserves as base_reserves,
                    virtual_token_reserves as token_reserves
                FROM {PUMP_TRADE_TABLE}
                WHERE mint = $1
                ORDER BY tsz, slot, ctid
            """
            
            # Query PumpFunAmmTradeEvent data
            query_amm = f"""
                SELECT
                    tsz,
                    slot,
                    is_buy,
                    amount_in,
                    amount_out,
                    pool_quote_token_reserves as base_reserves,
                    pool_base_token_reserves as token_reserves
                FROM {PUMP_AMM_TRADE_TABLE}
                WHERE pool = $1
                ORDER BY tsz, slot, ctid
            """
            
            try:
                # Execute both queries
                pump_records = await conn.fetch(query_pump, mint_address)

                # Check if mint is in AMM pool
                pools = await self._find_amm_pool(conn, [mint_address])
                if mint_address not in pools or pools[mint_address][1] != 'pump':
                    log.info(f"Mint {mint_address} not in Pump AMM, returning empty DataFrame")
                    amm_records = None
                else:
                    pool, _ = pools[mint_address]
                    amm_records = await conn.fetch(query_amm, pool)
                
                # Combine results
                combined = []
                if pump_records:
                    combined.extend(pump_records)
                if amm_records:
                    combined.extend(amm_records)
                    
                if not combined:
                    log.info(f"No trade data found for mint {mint_address}")
                    return pd.DataFrame(columns=['tsz', 'slot', 'is_buy', 'amount_in', 'amount_out', 'base_reserves', 'token_reserves'])
                    
                # Convert to DataFrame
                df = pd.DataFrame(combined, columns=['tsz', 'slot', 'is_buy', 'amount_in', 'amount_out', 'base_reserves', 'token_reserves'])
                log.info(f"Fetched {len(df)} trade records for mint {mint_address}")
                return df
                
            except Exception as e:
                log.error(f"Error fetching trade data for mint {mint_address}: {e}")
                return pd.DataFrame(columns=['tsz', 'slot', 'is_buy', 'amount_in', 'amount_out', 'base_reserves', 'token_reserves'])

    async def fetch_raw_data_for_mint(self, mint_address: str) -> List[pd.DataFrame]:
        """
        Fetches raw, unmodified trade data for a specific mint from both bonding curve
        and AMM trade tables.

        Args:
            mint_address: The token mint address to query.

        Returns:
            A list of pandas DataFrames: [bonding_curve_trades, amm_trades].
            DataFrames will be empty if no data is found or tables don't exist.
        """
        await self._connect()
        if not self._pool:
            log.error("Database pool connection failed or not established.")
            raise ConnectionError("Database pool not initialized or connection failed.")

        results_dfs = []
        async with self._pool.acquire() as conn:
            # 1. Fetch Bonding Curve Trades
            if await self._table_exists(conn, PUMP_TRADE_TABLE):
                query_bc = f"SELECT * FROM {PUMP_TRADE_TABLE} WHERE mint = $1 ORDER BY tsz, slot, ctid"
                try:
                    records_bc = await conn.fetch(query_bc, mint_address)
                    if records_bc:
                        df_bc = pd.DataFrame(records_bc, columns=list(records_bc[0].keys()))
                        log.info(f"Fetched {len(df_bc)} raw bonding curve trades for mint {mint_address}.")
                        results_dfs.append(df_bc)
                    else:
                        log.info(f"No raw bonding curve trades found for mint {mint_address}.")
                        results_dfs.append(pd.DataFrame())
                except Exception as e:
                    log.error(f"Error fetching raw bonding curve trades for mint {mint_address}: {e}")
                    results_dfs.append(pd.DataFrame())
            else:
                log.warning(f"Table {PUMP_TRADE_TABLE} does not exist.")
                results_dfs.append(pd.DataFrame())

            # 2. Fetch AMM Trades
            amm_df = pd.DataFrame()
            if await self._table_exists(conn, PUMP_AMM_TRADE_TABLE):
                pools = await self._find_amm_pool(conn, [mint_address])
                if mint_address in pools and pools[mint_address][1] == 'pump':
                    pool_address, _ = pools[mint_address]
                    query_amm = f"SELECT * FROM {PUMP_AMM_TRADE_TABLE} WHERE pool = $1 ORDER BY tsz, slot, ctid"
                    try:
                        records_amm = await conn.fetch(query_amm, pool_address)
                        if records_amm:
                            amm_df = pd.DataFrame(records_amm, columns=list(records_amm[0].keys()))
                            log.info(f"Fetched {len(amm_df)} raw AMM trades for mint {mint_address} (pool {pool_address}).")
                        else:
                            log.info(f"No raw AMM trades found for mint {mint_address} (pool {pool_address}).")
                    except Exception as e:
                        log.error(f"Error fetching raw AMM trades for mint {mint_address}: {e}")
                else:
                    log.info(f"Mint {mint_address} not found in a Pump AMM pool.")
            else:
                log.warning(f"Table {PUMP_AMM_TRADE_TABLE} does not exist.")
            results_dfs.append(amm_df)

        return results_dfs

    async def fetch_trades(self,
                           mint_addresses: Union[str, List[str]],
                           start_date: datetime | None = None,
                           end_date: datetime | None = None) -> pd.DataFrame:
        await self._connect()
        if not self._pool:
            # Ensure pool is connected before proceeding
            log.error("Database pool connection failed or not established.")
            raise ConnectionError("Database pool not initialized or connection failed.")

        async with self._pool.acquire() as conn:
            tick_data = await self._fetch_raw_trades(mint_addresses, conn, start_date, end_date)
            tick_data = tick_data.set_index('timestamp')
            return tick_data
    
    async def _fetch_raw_trades(self,
                           mint_addresses: Union[str, List[str]],
                           conn: asyncpg.Connection,
                           start_date: datetime | None = None,
                           end_date: datetime | None = None) -> pd.DataFrame:
        trades_dfs = []
        min_amount = 1000   # for avoiding spikes

        if isinstance(mint_addresses, str):
            mint_addresses_list = [mint_addresses]
        else:
            mint_addresses_list = mint_addresses
        t0 = time.time()

        # Classify mints to determine their origin
        mint_classification = await self._classify_mints(conn, mint_addresses_list)
        pump_mints = [m for m, type in mint_classification.items() if type == 'pumpfun']
        raydium_mints = [m for m, type in mint_classification.items() if type == 'raydium_launchpad']
        # log.info(f"Classified mints: {len(pump_mints)} pump.fun, {len(raydium_mints)} Raydium Launchpad.")

        # Prepare date filter SQL parts
        date_filter_clauses = []
        date_params = []
        if start_date:
            date_filter_clauses.append("tsz >= ${param_idx}")
            date_params.append(start_date)
        if end_date:
            date_filter_clauses.append("tsz <= ${param_idx}")
            date_params.append(end_date)

        def build_query_components(mints: List[str]):
            mint_placeholders = ", ".join([f"${i+1}" for i in range(len(mints))])
            param_idx_start = len(mints) + 1
            date_filter_sql = " AND ".join(clause.format(param_idx=i + param_idx_start) for i, clause in enumerate(date_filter_clauses))
            if date_filter_sql:
                date_filter_sql = "AND " + date_filter_sql
            sql_params = mints + date_params
            return mint_placeholders, date_filter_sql, sql_params

        # --- 1. Fetch Pump.fun bonding curve trades ---
        if pump_mints and await self._table_exists(conn, PUMP_TRADE_TABLE):
            mint_placeholders, date_filter_sql, sql_params = build_query_components(pump_mints)
            query_pump = f"""
                SELECT tsz, slot, is_buy, sol_amount, token_amount, owner, mint
                FROM {PUMP_TRADE_TABLE}
                WHERE mint IN ({mint_placeholders}) {date_filter_sql}
                AND token_amount > {min_amount} AND sol_amount > {min_amount}
                ORDER BY tsz, slot, ctid
            """
            try:
                records = await conn.fetch(query_pump, *sql_params)
                if records:
                    df = pd.DataFrame(records, columns=['tsz', 'slot', 'is_buy', 'sol_amount', 'token_amount', 'owner', 'mint'])
                    df['sol_amount'] = pd.to_numeric(df['sol_amount'], errors='coerce')
                    df['token_amount'] = pd.to_numeric(df['token_amount'], errors='coerce')
                    df['price'] = df['sol_amount'] / df['token_amount']
                    df['volume'] = df['sol_amount']
                    df['payer'] = df['owner']
                    df['source'] = 'pump_bc'
                    trades_dfs.append(df[['tsz', 'slot', 'is_buy', 'price', 'volume', 'source', 'payer', 'mint']])
                    log.debug(f"Fetched {len(df)} bonding curve trades for {len(pump_mints)} pump.fun mint(s).")
            except Exception as e:
                log.error(f"Error fetching pump.fun bonding curve trades for {pump_mints}: {e}")

        # --- 2. Fetch Raydium Launchpad trades ---
        if raydium_mints and await self._table_exists(conn, RAYDIUM_LAUNCHPAD_TRADE_TABLE):
            mint_placeholders, date_filter_sql, sql_params = build_query_components(raydium_mints)
            query_ray_launch = f"""
                SELECT tsz, slot, is_buy, amount_in, amount_out, owner, mint
                FROM {RAYDIUM_LAUNCHPAD_TRADE_TABLE}
                WHERE mint IN ({mint_placeholders}) {date_filter_sql}
                AND amount_in > {min_amount} AND amount_out > {min_amount}
                ORDER BY tsz, slot, ctid
            """
            try:
                records = await conn.fetch(query_ray_launch, *sql_params)
                if records:
                    df = pd.DataFrame(records, columns=['tsz', 'slot', 'is_buy', 'amount_in', 'amount_out', 'owner', 'mint'])
                    df['amount_in'] = pd.to_numeric(df['amount_in'], errors='coerce')
                    df['amount_out'] = pd.to_numeric(df['amount_out'], errors='coerce')
                    # Assuming quote is SOL. is_buy means SOL is amount_in.
                    df['price'] = np.where(df['is_buy'], df['amount_in'] / df['amount_out'], df['amount_out'] / df['amount_in'])
                    df['volume'] = np.where(df['is_buy'], df['amount_in'], df['amount_out'])
                    df['payer'] = df['owner']
                    df['source'] = 'raydium_launchpad'
                    trades_dfs.append(df[['tsz', 'slot', 'is_buy', 'price', 'volume', 'source', 'payer', 'mint']])
                    log.debug(f"Fetched {len(df)} Raydium Launchpad trades for {len(raydium_mints)} mint(s).")
            except Exception as e:
                log.error(f"Error fetching Raydium Launchpad trades for {raydium_mints}: {e}")

        # --- 3. Fetch Raydium CPMM trades (for launchpad tokens that migrated) ---
        if raydium_mints and await self._table_exists(conn, RAYDIUM_CPMM_SWAP_TABLE):
            mint_placeholders, date_filter_sql, sql_params = build_query_components(raydium_mints)
            query_cpmm = f"""
                SELECT tsz, slot, is_buy, amount_in, amount_out, owner, mint
                FROM {RAYDIUM_CPMM_SWAP_TABLE}
                WHERE mint IN ({mint_placeholders}) {date_filter_sql}
                AND amount_in > {min_amount} AND amount_out > {min_amount}
                ORDER BY tsz, slot, ctid
            """
            try:
                records = await conn.fetch(query_cpmm, *sql_params)
                if records:
                    df = pd.DataFrame(records, columns=['tsz', 'slot', 'is_buy', 'amount_in', 'amount_out', 'owner', 'mint'])
                    df['amount_in'] = pd.to_numeric(df['amount_in'], errors='coerce')
                    df['amount_out'] = pd.to_numeric(df['amount_out'], errors='coerce')
                    df['price'] = np.where(df['is_buy'], df['amount_in'] / df['amount_out'], df['amount_out'] / df['amount_in'])
                    df['volume'] = np.where(df['is_buy'], df['amount_in'], df['amount_out'])
                    df['payer'] = df['owner']
                    df['source'] = 'raydium_cpmm'
                    trades_dfs.append(df[['tsz', 'slot', 'is_buy', 'price', 'volume', 'source', 'payer', 'mint']])
                    log.debug(f"Fetched {len(df)} Raydium CPMM trades for {len(raydium_mints)} mint(s).")
            except Exception as e:
                log.error(f"Error fetching Raydium CPMM trades for {raydium_mints}: {e}")

        # --- 4. Find and Fetch Standard AMM trades (for all tokens) ---
        amm_pools_map = await self._find_amm_pool(conn, mint_addresses_list)
        pools_by_type: Dict[str, Dict[str, str]] = {'pump': {}, 'raydium': {}}
        for mint_addr, (pool_addr, pool_type) in amm_pools_map.items():
            pools_by_type[pool_type][pool_addr] = mint_addr
        
        amount_condition = f"amount_in > {min_amount} AND amount_out > {min_amount}"

        for amm_type, pools_map in pools_by_type.items():
            if not pools_map:
                continue

            amm_table, pool_column = None, None
            if amm_type == 'pump' and await self._table_exists(conn, PUMP_AMM_TRADE_TABLE):
                amm_table, pool_column = PUMP_AMM_TRADE_TABLE, 'pool'
            elif amm_type == 'raydium' and await self._table_exists(conn, RAYDIUM_SWAP_TABLE):
                amm_table, pool_column = RAYDIUM_SWAP_TABLE, 'pool_pc_token_account'

            if amm_table and pool_column:
                pool_addresses = list(pools_map.keys())
                _, date_filter_sql, sql_params = build_query_components(pool_addresses)
                
                query_amm = f"""
                    SELECT tsz, slot, is_buy, amount_in, amount_out, owner, {pool_column} as pool_addr
                    FROM {amm_table}
                    WHERE {pool_column} IN ({", ".join([f'${i+1}' for i in range(len(pool_addresses))])}) {date_filter_sql}
                    AND {amount_condition}
                    ORDER BY tsz, slot, ctid
                """
                try:
                    records = await conn.fetch(query_amm, *sql_params)
                    if records:
                        df_amm = pd.DataFrame(records, columns=['tsz', 'slot', 'is_buy', 'amount_in', 'amount_out', 'owner', 'pool_addr'])
                        df_amm['amount_in'] = pd.to_numeric(df_amm['amount_in'], errors='coerce')
                        df_amm['amount_out'] = pd.to_numeric(df_amm['amount_out'], errors='coerce')
                        df_amm['price'] = np.where(df_amm['is_buy'], df_amm['amount_in'] / df_amm['amount_out'], df_amm['amount_out'] / df_amm['amount_in'])
                        df_amm['volume'] = np.where(df_amm['is_buy'], df_amm['amount_in'], df_amm['amount_out'])
                        df_amm['source'] = amm_type + '_amm'
                        df_amm['payer'] = df_amm['owner']
                        df_amm['mint'] = df_amm['pool_addr'].map(pools_map)
                        trades_dfs.append(df_amm[['tsz', 'slot', 'is_buy', 'price', 'volume', 'source', 'payer', 'mint']])
                        log.debug(f"Fetched {len(df_amm)} {amm_type} AMM trades for {len(pool_addresses)} pools.")
                except Exception as e:
                    log.error(f"Error fetching {amm_type} AMM trades for pools {pool_addresses}: {e}")

        # --- Combine, Interpolate Timestamp, and Finalize ---
        if not trades_dfs:
            log.warning(f"No trade data found for mint(s) {mint_addresses_list} across available tables.")
            return pd.DataFrame(columns=['timestamp', 'price', 'volume', 'source', 'mint'])

        all_trades_df = pd.concat(trades_dfs, ignore_index=True)
        all_trades_df['timestamp'] = pd.to_datetime(all_trades_df['tsz'], unit='s', errors='coerce')

        original_rows = len(all_trades_df)
        all_trades_df.dropna(subset=['timestamp'], inplace=True)
        if (removed_rows := original_rows - len(all_trades_df)) > 0:
            log.warning(f"Removed {removed_rows} rows due to missing timestamps for mint(s) {mint_addresses_list}.")

        if all_trades_df.empty:
             log.warning(f"No valid trade data remaining after timestamp conversion for mint(s) {mint_addresses_list}.")
             return pd.DataFrame(columns=['timestamp', 'price', 'volume', 'source', 'mint'])

        all_trades_df = all_trades_df.drop(columns=['slot', 'tsz'])
        all_trades_df.sort_values(by='timestamp', inplace=True)
        all_trades_df.reset_index(drop=True, inplace=True)

        all_trades_df['volume'] /= LAMPORTS_PER_SOL
        all_trades_df['price'] *= 10**DEFAULT_TOKEN_DECIMALS / LAMPORTS_PER_SOL
        if self.result_in_mcap:
            all_trades_df['price'] *= TOTAL_SUPPLY
        if self.result_in_usd:
            if not all_trades_df.empty:
                sol_2_usd = self.sol_price_fetcher.get_price(all_trades_df['timestamp'].iloc[0])
                all_trades_df['volume'] *= sol_2_usd
                all_trades_df['price'] *= sol_2_usd
        
        log.debug(f"Finished processing {len(all_trades_df)} trades for {len(mint_addresses_list)} mint(s). elapsed time = {(time.time()-t0):.2f}")
        return all_trades_df

    async def get_data(self,
                       mint_address: str,
                       data_type: str = 'tick', # 'tick' or 'ohlcv'
                       granularity: str = '1min', # e.g., '1min', '5T', '1H', '1D'
                       start_date: datetime | None = None, # Note: Still filters by tsz in fetch_trades
                       end_date: datetime | None = None) -> pd.DataFrame:
        """
        Fetches tick or OHLCV data for a given mint address.
        Uses interpolated slot-based timestamps for tick data.
        Handles bonding curve and AMM trades, checks for missing tables.
        Optionally uses Continuous Aggregates if available and matching granularity.
        """
        await self._connect()
        if not self._pool:
            # Ensure pool is connected before proceeding
            log.error("Database pool connection failed or not established.")
            raise ConnectionError("Database pool not initialized or connection failed.")

        async with self._pool.acquire() as conn:
            # --- Optimization Check: Query Continuous Aggregate for OHLCV ---
            # (Keep CAGG logic as is, assuming 'bucket' is the reliable timestamp)
            cagg_name = None
            if data_type == 'ohlcv':
                bucket_size_map = {'1s': '1 sec', '1min': '1 minute', '5T': '5 minutes', '1H': '1 hour', '1D': '1 day'}
                sql_bucket_size = bucket_size_map.get(granularity)
                if sql_bucket_size:
                    # !! Adjust this table name if your CAGG naming is different !!
                    cagg_name = f"token_ohlcv_{granularity.lower().replace('t', 'min')}" # Example name

            if cagg_name and await self._table_exists(conn, cagg_name):
                log.info(f"Attempting to query Continuous Aggregate: {cagg_name}")
                try:
                    param_count = 1
                    params = [mint_address]
                    cagg_filter_sql = ""
                    # Filter CAGG by bucket timestamp
                    if start_date:
                        cagg_filter_sql += f" AND bucket >= ${param_count + 1}"
                        params.append(start_date)
                        param_count += 1
                    if end_date:
                         cagg_filter_sql += f" AND bucket < ${param_count + 1}" # Use < for end date with buckets
                         params.append(end_date)
                         param_count += 1

                    query_cagg = f"""
                        SELECT bucket as timestamp, open, high, low, close, volume
                        FROM {cagg_name}
                        WHERE mint = $1 {cagg_filter_sql}
                        ORDER BY bucket ASC
                    """
                    cagg_records = await conn.fetch(query_cagg, *params)
                    if cagg_records:
                        log.info(f"Successfully fetched {len(cagg_records)} rows from Continuous Aggregate {cagg_name}")
                        df_ohlcv = pd.DataFrame(cagg_records, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                        df_ohlcv['timestamp'] = pd.to_datetime(df_ohlcv['timestamp'])
                        # Optional: Convert volume from lamports to SOL here if CAGG stores lamports
                        return df_ohlcv.set_index('timestamp')
                    else:
                         log.info(f"No data found in Continuous Aggregate {cagg_name} for the specified range.")
                         # Fall through to raw trade fetching if CAGG is empty for range
                except Exception as e:
                    log.warning(f"Could not query Continuous Aggregate {cagg_name}: {e}. Falling back to raw trades.")
            elif cagg_name:
                log.info(f"Continuous Aggregate '{cagg_name}' does not exist. Falling back to raw trades.")

            # --- Fallback or Tick Data: Fetch Raw Trades with Interpolated Timestamps ---
            log.info("Fetching raw trades and interpolating timestamps...")
            tick_data = await self._fetch_raw_trades(mint_address, 
                                                conn=conn, 
                                                start_date=start_date, 
                                                end_date=end_date)

            if tick_data.empty:
                 log.warning(f"No raw trade data found or processed for mint {mint_address}. Returning empty DataFrame.")
                 if data_type == 'tick':
                      # Return empty df with correct columns for tick data
                      return pd.DataFrame(columns=['price', 'volume', 'source']).set_index(pd.to_datetime([]))
                 elif data_type == 'ohlcv':
                      # Return empty df with correct columns for ohlcv data
                      return pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume']).set_index(pd.to_datetime([]))
                 else:
                      raise ValueError("data_type must be 'tick' or 'ohlcv'")


            if data_type == 'tick':
                log.info(f"Returning {len(tick_data)} rows of tick data.")
                return tick_data.set_index('timestamp')

            elif data_type == 'ohlcv':
                log.info(f"Generating {granularity} OHLCV data from {len(tick_data)} raw trades...")
                tick_data = tick_data.set_index('timestamp')

                # Resample to OHLCV
                ohlc = tick_data['price'].resample(granularity, closed='left', label='left').ohlc()
                volume = tick_data['volume'].resample(granularity, closed='left', label='left').sum()

                df_ohlcv = pd.concat([ohlc, volume], axis=1)
                # Ensure column name is 'volume' after concat (sometimes gets numbered if volume column name was different)
                # Find the volume column index (should be the last one)
                volume_col_index = len(df_ohlcv.columns) - 1
                df_ohlcv.rename(columns={df_ohlcv.columns[volume_col_index]: 'volume'}, inplace=True)


                # Fill NaNs created by resampling empty intervals
                # Forward fill close price from previous valid interval
                df_ohlcv['close'] = df_ohlcv['close'].ffill()
                # Where ohlc values are NaN, fill with the forward-filled close
                df_ohlcv['open'] = df_ohlcv['open'].fillna(df_ohlcv['close'])
                df_ohlcv['high'] = df_ohlcv['high'].fillna(df_ohlcv['close'])
                df_ohlcv['low'] = df_ohlcv['low'].fillna(df_ohlcv['close'])
                # Fill volume NaNs with 0
                df_ohlcv['volume'] = df_ohlcv['volume'].fillna(0)

                # Drop any rows where close is still NaN (e.g., at the very beginning if no trades)
                df_ohlcv.dropna(subset=['close'], inplace=True)


                log.info(f"Generated {len(df_ohlcv)} OHLCV rows.")
                return df_ohlcv

            else:
                raise ValueError("data_type must be 'tick' or 'ohlcv'")

    async def fetch_pumpfun_create_events(self,
                                          start_date: Optional[Union[datetime, str]] = None,
                                          end_date: Optional[Union[datetime, str]] = None,
                                          mint_address: Optional[str] = None) -> pd.DataFrame:
        """
        Fetches PumpFunCreateEvent data from the database.
        Accepts start_date and end_date as datetime objects or strings (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
        If mint_address is provided, date filters are ignored.

        Args:
            start_date: Optional start datetime/string to filter events. Ignored if mint_address is provided.
            end_date: Optional end datetime/string to filter events. Ignored if mint_address is provided.
            mint_address: Optional mint address string to filter events.

        Returns:
            A pandas DataFrame containing the PumpFunCreateEvent data.
        """
        
        parsed_start_date: Optional[datetime] = None
        parsed_end_date: Optional[datetime] = None
        # Define expected columns for empty DataFrames consistently
        expected_cols = list(pumpfun_event_types.PumpFunCreateEvent._fields) + ['tsz', 'slot']

        date_formats_to_try = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]

        # Date parsing is only relevant if mint_address is not provided
        if not mint_address:
            if start_date:
                if isinstance(start_date, str):
                    dt_naive = None
                    for fmt in date_formats_to_try:
                        try:
                            dt_naive = datetime.strptime(start_date, fmt)
                            break
                        except ValueError:
                            continue
                    if dt_naive:
                        parsed_start_date = dt_naive.replace(tzinfo=timezone.utc)
                    elif isinstance(start_date, str): # Ensure it was a string that failed all formats
                        log.error(f"Invalid start_date string format: {start_date}. Expected YYYY-MM-DD or YYYY-MM-DD HH:MM:SS. Proceeding without start_date filter.")
                elif isinstance(start_date, datetime):
                    if start_date.tzinfo is None: # Naive datetime, assume UTC
                        parsed_start_date = start_date.replace(tzinfo=timezone.utc)
                    else: # Already timezone-aware
                        parsed_start_date = start_date
                else:
                    log.error(f"Invalid type for start_date: {type(start_date)}. Expected datetime or str. Proceeding without start_date filter.")

            if end_date:
                if isinstance(end_date, str):
                    dt_naive = None
                    for fmt in date_formats_to_try:
                        try:
                            dt_naive = datetime.strptime(end_date, fmt)
                            break
                        except ValueError:
                            continue
                    if dt_naive:
                        parsed_end_date = dt_naive.replace(tzinfo=timezone.utc)
                    elif isinstance(end_date, str): # Ensure it was a string that failed all formats
                        log.error(f"Invalid end_date string format: {end_date}. Expected YYYY-MM-DD or YYYY-MM-DD HH:MM:SS. Proceeding without end_date filter.")
                elif isinstance(end_date, datetime):
                    if end_date.tzinfo is None: # Naive datetime, assume UTC
                        parsed_end_date = end_date.replace(tzinfo=timezone.utc)
                    else: # Already timezone-aware
                        parsed_end_date = end_date
                else:
                    log.error(f"Invalid type for end_date: {type(end_date)}. Expected datetime or str. Proceeding without end_date filter.")

        await self._connect()
        if not self._pool:
            log.error("Database pool not initialized for fetch_pumpfun_create_events")
            return pd.DataFrame(columns=expected_cols)

        async with self._pool.acquire() as conn:
            if not await self._table_exists(conn, PUMP_CREATE_TABLE):
                log.warning(f"Table {PUMP_CREATE_TABLE} does not exist.")
                return pd.DataFrame(columns=expected_cols)

            query_params = []
            filter_conditions = []
            
            if mint_address:
                filter_conditions.append("mint = $1")
                query_params.append(mint_address)
            else:
                # Date filters are only applied if mint_address is not provided
                param_idx = 1
                if parsed_start_date:
                    filter_conditions.append(f"tsz >= ${param_idx}")
                    query_params.append(parsed_start_date)
                    param_idx += 1
                if parsed_end_date:
                    filter_conditions.append(f"tsz <= ${param_idx}")
                    query_params.append(parsed_end_date)
                    param_idx += 1
                # Handling BETWEEN for dates if both are present and no mint_address
                if parsed_start_date and parsed_end_date:
                    # Reset conditions and params for BETWEEN for clarity, though above logic also works
                    filter_conditions = ["tsz BETWEEN $1 AND $2"]
                    query_params = [parsed_start_date, parsed_end_date]


            where_clause = ""
            if filter_conditions:
                where_clause = "WHERE " + " AND ".join(filter_conditions)
            
            query = f"SELECT * FROM {PUMP_CREATE_TABLE} {where_clause} ORDER BY tsz, slot, ctid"
            
            try:
                records = await conn.fetch(query, *query_params)
                if not records:
                    log.info(f"No PumpFunCreateEvent data found for the given criteria in {PUMP_CREATE_TABLE}.")
                    return pd.DataFrame(columns=expected_cols)
                
                df = pd.DataFrame(records, columns=list(records[0].keys()))
                df.set_index('tsz', inplace=True)
                log.info(f"Fetched {len(df)} PumpFunCreateEvent records from {PUMP_CREATE_TABLE}.")
                # Add default metadata fields for backtest usage
                df['decimals'] = DEFAULT_TOKEN_DECIMALS
                df['total_supply'] = int(10**DEFAULT_TOKEN_DECIMALS * TOTAL_SUPPLY)
                df['quote_mint'] = str(SOL)
                return df
            except Exception as e:
                log.error(f"Error fetching PumpFunCreateEvent data from {PUMP_CREATE_TABLE}: {e}")
                return pd.DataFrame(columns=expected_cols)
 
    async def fetch_raydium_launchpad_create_events(self,
                                                  start_date: Optional[Union[datetime, str]] = None,
                                                  end_date: Optional[Union[datetime, str]] = None,
                                                  mint_address: Optional[str] = None) -> pd.DataFrame:
        """
        Fetches RaydiumLaunchpadPoolCreateEvent data from the database.
        Accepts start_date and end_date as datetime objects or strings (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
        If mint_address is provided, date filters are ignored.

        Args:
            start_date: Optional start datetime/string to filter events. Ignored if mint_address is provided.
            end_date: Optional end datetime/string to filter events. Ignored if mint_address is provided.
            mint_address: Optional mint address string to filter for a specific token.

        Returns:
            A pandas DataFrame containing the RaydiumLaunchpadPoolCreateEvent data.
        """
        parsed_start_date: Optional[datetime] = None
        parsed_end_date: Optional[datetime] = None
        expected_cols = list(pumpfun_event_types.RaydiumLaunchpadPoolCreateEvent._fields) + ['tsz', 'slot']

        date_formats_to_try = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]

        if not mint_address:
            if start_date:
                if isinstance(start_date, str):
                    dt_naive = None
                    for fmt in date_formats_to_try:
                        try:
                            dt_naive = datetime.strptime(start_date, fmt)
                            break
                        except ValueError:
                            continue
                    if dt_naive:
                        parsed_start_date = dt_naive.replace(tzinfo=timezone.utc)
                    elif isinstance(start_date, str):
                        log.error(f"Invalid start_date string format: {start_date}. Proceeding without filter.")
                elif isinstance(start_date, datetime):
                    parsed_start_date = start_date if start_date.tzinfo else start_date.replace(tzinfo=timezone.utc)
                else:
                    log.error(f"Invalid type for start_date: {type(start_date)}. Proceeding without filter.")

            if end_date:
                if isinstance(end_date, str):
                    dt_naive = None
                    for fmt in date_formats_to_try:
                        try:
                            dt_naive = datetime.strptime(end_date, fmt)
                            break
                        except ValueError:
                            continue
                    if dt_naive:
                        parsed_end_date = dt_naive.replace(tzinfo=timezone.utc)
                    elif isinstance(end_date, str):
                        log.error(f"Invalid end_date string format: {end_date}. Proceeding without filter.")
                elif isinstance(end_date, datetime):
                    parsed_end_date = end_date if end_date.tzinfo else end_date.replace(tzinfo=timezone.utc)
                else:
                    log.error(f"Invalid type for end_date: {type(end_date)}. Proceeding without filter.")

        await self._connect()
        if not self._pool:
            log.error("Database pool not initialized for fetch_raydium_launchpad_create_events")
            return pd.DataFrame(columns=expected_cols)

        async with self._pool.acquire() as conn:
            if not await self._table_exists(conn, RAYDIUM_LAUNCHPAD_POOL_CREATE_TABLE):
                log.warning(f"Table {RAYDIUM_LAUNCHPAD_POOL_CREATE_TABLE} does not exist.")
                return pd.DataFrame(columns=expected_cols)

            query_params = []
            filter_conditions = []

            if mint_address:
                filter_conditions.append("mint = $1")
                query_params.append(mint_address)
            else:
                param_idx = 1
                if parsed_start_date:
                    filter_conditions.append(f"tsz >= ${param_idx}")
                    query_params.append(parsed_start_date)
                    param_idx += 1
                if parsed_end_date:
                    filter_conditions.append(f"tsz <= ${param_idx}")
                    query_params.append(parsed_end_date)
                    param_idx += 1
                if parsed_start_date and parsed_end_date:
                    filter_conditions = ["tsz BETWEEN $1 AND $2"]
                    query_params = [parsed_start_date, parsed_end_date]

            where_clause = ""
            if filter_conditions:
                where_clause = "WHERE " + " AND ".join(filter_conditions)

            query = f"SELECT * FROM {RAYDIUM_LAUNCHPAD_POOL_CREATE_TABLE} {where_clause} ORDER BY tsz, slot, ctid"

            try:
                records = await conn.fetch(query, *query_params)
                if not records:
                    log.info(f"No RaydiumLaunchpadPoolCreateEvent data found for the given criteria in {RAYDIUM_LAUNCHPAD_POOL_CREATE_TABLE}.")
                    return pd.DataFrame(columns=expected_cols)

                df = pd.DataFrame(records, columns=list(records[0].keys()))
                df.set_index('tsz', inplace=True)
                log.info(f"Fetched {len(df)} RaydiumLaunchpadPoolCreateEvent records from {RAYDIUM_LAUNCHPAD_POOL_CREATE_TABLE}.")
                # Normalize field names
                df['name'] = df['base_mint_name']
                df['symbol'] = df['base_mint_symbol']
                df['uri'] = df['base_mint_uri']
                df['decimals'] = df['base_mint_decimals']
                if 'supply' in df:
                    df['total_supply'] = df['supply']
                else:
                    df['total_supply'] = df['vesting_total_locked_amount']
                df.loc[df['total_supply'] == 0, 'total_supply'] = int(10**DEFAULT_TOKEN_DECIMALS * TOTAL_SUPPLY)
                if 'quote_mint' not in df:
                    df['quote_mint'] = str(SOL)
                return df
            except Exception as e:
                log.error(f"Error fetching RaydiumLaunchpadPoolCreateEvent data from {RAYDIUM_LAUNCHPAD_POOL_CREATE_TABLE}: {e}")
                return pd.DataFrame(columns=expected_cols)

 
# --- Modified Example Usage with Plotting ---
async def main():
    # Setup basic logging for the example
    
    # Ensure RPC URL is available
    if not SOLANA_RPC_URL:
        print("Error: SOLANA_RPC_URL is not defined in config.py")
        # You might want to load it from environment variables or a .env file as well
        # Example: SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
        print("Please define SOLANA_RPC_URL in config.py or environment variables.")
        return

    fetcher = None # Initialize fetcher to None for finally block
    try:
        fetcher = TokenDataFetcher()
        # Use the mint address from your error log or another test mint
        mint = "Fx4TPTTWiwGKuKXDzgPjmJQMZsLuiwLEMPkufYaipump" # this is a raydium launchpad token
        plot_output_dir = "plots" # Directory to save plots
        granularity = '1m'
        os.makedirs(plot_output_dir, exist_ok=True)

        fetch_tick = True
        fetch_ohlcv = False

        # --- Get OHLCV data ---
        if fetch_ohlcv:
            print(f"\nFetching OHLCV for {mint}...")
            start_time = time.monotonic()
            ohlcv = await fetcher.get_data(mint, data_type='ohlcv', granularity=granularity)
            duration = time.monotonic() - start_time
            print(f"Fetched OHLCV data in {duration:.2f} seconds.")

            if not ohlcv.empty:
                # --- Plot OHLCV Data ---
                try:
                    plot_filename_ohlcv = os.path.join(plot_output_dir, f"{mint}_ohlcv_{granularity}_slot_ts.png") # New filename
                    print(f"Plotting OHLCV data to {plot_filename_ohlcv}...")
                    mpf.plot(ohlcv,
                            type='candle',
                            style='yahoo',
                            title=f'{mint} {granularity} OHLCV (Slot Timestamp)',
                            ylabel='Price',
                            volume=True,
                            ylabel_lower='Volume',
                            figratio=(16, 9))
                            #, savefig=plot_filename_ohlcv)
                    print("OHLCV plot saved.")
                except Exception as plot_err:
                    log.error(f"Failed to generate OHLCV plot: {plot_err}", exc_info=True)

            else:
                print("No OHLCV data found.")


        # --- Optional: Get Tick data ---
        if fetch_tick:
            print(f"\nFetching Tick data for {mint}...")
            start_time = time.monotonic()
            tick_data = await fetcher.get_data(mint, data_type='tick')
            duration = time.monotonic() - start_time
            print(f"Fetched tick data in {duration:.2f} seconds.")

            if not tick_data.empty:
                # --- Plot Tick Data ---
                try:
                    plot_filename_tick = os.path.join(plot_output_dir, f"{mint}_tick_data_slot_ts.png") # New filename
                    print(f"Plotting Tick data to {plot_filename_tick}...")
                    fig, ax1 = plt.subplots(figsize=(16, 9))

                    colors = {'pump_bc': 'blue', 'raydium_amm': 'red', 'pump_amm': 'green', 'raydium_launchpad': 'purple', 'raydium_cpmm': 'orange'}
                    ax1.set_xlabel('Timestamp (Interpolated Slot Time)')
                    ax1.set_ylabel('Price', color='tab:blue')
                    for source, color in colors.items():
                        subset = tick_data[tick_data['source'] == source]
                        if not subset.empty:
                            ax1.scatter(subset.index, subset['price'], label=f'Price ({source})', color=color, s=5)

                    ax1.tick_params(axis='y', labelcolor='tab:blue')
                    ax1.legend(loc='upper left')
                    ax1.grid(True)

                    ax2 = ax1.twinx()
                    ax2.set_ylabel('Volume (SOL)', color='tab:gray')
                    # Adjust width based on typical time delta if needed
                    # Example: estimate width based on median time diff
                    time_diffs = tick_data.index.to_series().diff().median()
                    bar_width = time_diffs.total_seconds() / (24 * 60 * 60) * 0.5 if pd.notna(time_diffs) else 0.0001
                    ax2.bar(tick_data.index, tick_data['volume'], width=bar_width, alpha=0.3, color='gray', label='Volume')
                    ax2.tick_params(axis='y', labelcolor='tab:gray')
                    ax2.legend(loc='upper right')

                    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S.%f')) # Show milliseconds
                    plt.gca().xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=15)) # More ticks
                    fig.autofmt_xdate()

                    plt.title(f'{mint} Tick Data (Price & Volume - Slot Timestamp)')
                    fig.tight_layout()
                    #plt.savefig(plot_filename_tick)
                    plt.show() # Optional: display interactively
                    plt.close(fig) # Close figure
                    print("Tick data plot saved.")
                except Exception as plot_err:
                    log.error(f"Failed to generate Tick plot: {plot_err}", exc_info=True)
            else:
                print("No tick data found.")

    except Exception as e:
        log.exception(f"An error occurred in main execution:") # Use log.exception for traceback
    finally:
        # Ensure fetcher resources are closed
        if fetcher:
            log.info("Closing TokenDataFetcher resources...")
            await fetcher.close(save_slot_cache=True) # Save cache on exit
            log.info("TokenDataFetcher resources closed.")
        else:
            log.info("Fetcher not initialized, nothing to close.")

async def test_mint_list():
        fetcher = TokenDataFetcher()
        mints = ["84R7DJLRtmCLbMxes5NYDhFHfPkPQAdjTG6bmetQpump", # pumpfun
                 "BwLhkMH1YXiuZhfh1LzZadsJ2G3C4BUEq3bio6v9bonk"] # raydium
        result_df = await fetcher.fetch_trades(mints)
        # result_df.columns == ['is_buy', 'price', 'volume', 'source', 'payer', 'mint']
        stop = 0

if __name__ == "__main__":
    # Make sure config.py has SOLANA_RPC_URL defined
    # Check if SOLANA_RPC_URL exists and is not empty
    if 'SOLANA_RPC_URL' not in globals() or not SOLANA_RPC_URL:
         print("Error: SOLANA_RPC_URL is not defined or empty in config.py")
         # Example: SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
         # Or load from environment: SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL")
         print("Please define SOLANA_RPC_URL = 'YOUR_RPC_ENDPOINT' in config.py or set the environment variable.")
         sys.exit(1)

    asyncio.run(main())
    #asyncio.run(test_mint_list())