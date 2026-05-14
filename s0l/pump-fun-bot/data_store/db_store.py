import os
import sys
import asyncio
import asyncpg
from typing import NamedTuple, Type, get_type_hints

import pandas as pd
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))
from utils.logger_factory import get_logger
from config import PG_CONNECTION
from pumpfun_event_types import *
from pyheck import snake

log = get_logger('db')
db_conn = None  # Persistent database connection
DB_VERSION = 'v02'
##
# v07 - works, failed with lagged to send an update
# v08 - works, failed with lagged to send an update
# v09 - all good, couple days of data, ip whitelist failed
# v10 - all good, 1+ month data, stopped because of pumpfun amm switch
# v00 - -20250910
# v01 - 20250910 - 20250912 missing total supply / raydium launchpad USD1 quote_mint support added 
# v02 - 20250912

# Type mapping from Python to PostgreSQL
TYPE_MAPPING = {
    int: 'NUMERIC',
    str: 'TEXT',
    bool: 'BOOLEAN',
    float: 'DOUBLE PRECISION'
}

def get_table_name(name) -> str:
    return f"{DB_VERSION}_{snake(name)}_events"

def get_table_name_from_class(event_class) -> str:
   return get_table_name(event_class._event_name)

def get_table_schema(event_type: Type[NamedTuple]) -> str:
    """Generate SQL schema from event type definition"""
    type_hints = get_type_hints(event_type)
    columns = []
    
    for field_name, field_type in type_hints.items():
        # Default to TEXT if type not in mapping
        sql_type = TYPE_MAPPING.get(field_type, 'TEXT')
        columns.append(f"{field_name} {sql_type}")
        
    return ",\n".join(columns)

async def connect_to_db():
    global db_conn
    try:
        db_conn = await asyncpg.connect(PG_CONNECTION)
        log.info("Database connection established.")
    except Exception as e:
        log.error(f"Error connecting to the database: {e}")

async def disconnect_db():
    global db_conn
    if db_conn:
        await db_conn.close()
        db_conn = None
        log.info("Database connection closed.")

async def create_tables():
    global db_conn
    try:
        # Create event tables based on type if they don't exist
        for e in KNOWN_EVENTS.values():
            schema = get_table_schema(e)
            await db_conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {get_table_name(e._event_name)} (
                    tsz TIMESTAMPTZ,
                    slot BIGINT,
                    {schema}
                );
            """)

        log.info(f"Tables created")
    except Exception as e:
        log.error(f"Error creating tables: {e}")

async def drop_tables():
    global db_conn
    try:
        # Get all tables starting with the current DB_VERSION
        tables = await db_conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name LIKE $1
        """, f"{DB_VERSION}_%")
        
        # Drop each matching table
        for table in tables:
            await db_conn.execute(f"DROP TABLE IF EXISTS {table['table_name']};")
            
        log.info(f"Dropped {len(tables)} tables starting with {DB_VERSION}_")
    except Exception as e:
        log.error(f"Error dropping tables: {e}")

async def insert_events(conn: asyncpg.Connection, ename, edata):
    try:
        # Get field names from event type
        fields = list(get_type_hints(KNOWN_EVENTS[ename]).keys())
        columns = ["tsz", "slot"] + fields
        placeholders = ", ".join(f"${i+1}" for i in range(len(columns)))
        
        query = f"""
            INSERT INTO {get_table_name(ename)} (
                {", ".join(columns)}
            )
            VALUES ({placeholders});
        """
        await conn.executemany(query, edata)
        log.info(f"insert:: {get_table_name(ename)} <-- {len(edata)} rows")
    except Exception as e:
        log.error(f"Error inserting {get_table_name(ename)} data: {e}")

# Function to upload data to TimescaleDB
async def upload_data(batch):
    global db_conn
    if not db_conn:
        log.error("Database connection not initialized.")
        return
    try:
        # Upload all items in the batch
        for k in batch:
            if not len(batch[k]):
                continue

            if k in KNOWN_EVENTS:
                await insert_events(db_conn, k, batch[k])
            else:
                log.error(f'ERROR: unknown event!!!!!!!!! {k}')

            #print(f"data uploaded to db..")
    except Exception as e:
        log.error(f"Error uploading batch: {e}")

async def upload_batch(pg_upload_batch, wait=False):
    if pg_upload_batch:  # If there's data in the batch
        current_batch = pg_upload_batch.copy()  # Copy the batch
        # Keep the stream reader responsive; callers can force a synchronous flush
        # during shutdown/tests by passing wait=True.
        if wait:
            await upload_data(current_batch)
        else:
            asyncio.create_task(upload_data(current_batch))

# -------------------- GETTER
async def get_trade_events(mint: str, db_prefix=DB_VERSION) -> pd.DataFrame:
    """Fetch all trade events for a specific mint as a pandas DataFrame"""
    if not db_conn:
        raise Exception("Database connection not initialized")
        
    query = f"""
        SELECT *
        FROM {get_table_name(PumpFunTradeEvent._event_name)}
        WHERE mint = $1
        ORDER BY tsz ASC
    """
    records = await db_conn.fetch(query, mint)

    if not records:
        # If no records are found, return an empty DataFrame
        return pd.DataFrame()
    
    # Extract column names from the first record
    columns = records[0].keys()

    df = pd.DataFrame(records, columns=columns)
    # convert objects to string
    df['mint'] = df['mint'].astype(str)
    df['owner'] = df['owner'].astype(str)
    return df
