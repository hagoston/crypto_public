import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__))))
import asyncpg
import logging
from data_store import db_store, pumpfun_event_types
from config import PG_CONNECTION

log = logging.getLogger('IndexManager')
logging.basicConfig(level=logging.INFO)

# Define the desired index structures more abstractly
# Format: (EventClass, columns_tuple, suffix_for_name)
INDEX_DEFINITIONS = [
    (pumpfun_event_types.PumpFunTradeEvent, ('mint', 'tsz'), '_mint_tsz_desc'),
    (pumpfun_event_types.RaydiumV4SwapEvent, ('pool_pc_token_account', 'tsz'), '_pool_tsz_desc'),
    (pumpfun_event_types.PumpFunAmmTradeEvent, ('pool', 'tsz'), '_pool_tsz_desc'),
    (pumpfun_event_types.PumpFunCreateEvent, ('mint', 'tsz'), '_mint_tsz_desc'),
    (pumpfun_event_types.RaydiumLaunchpadTradeEvent, ('mint', 'tsz'), '_mint_tsz_desc'),
    (pumpfun_event_types.RaydiumCPMMSwapEvent, ('mint', 'tsz'), '_mint_tsz_desc'),
    # Add other desired indexes here following the same pattern
]

async def ensure_indexes():
    conn = None
    all_tables_exist = True # Flag to track if all necessary tables exist

    try:
        conn = await asyncpg.connect(PG_CONNECTION)
        log.info("Connected to database to ensure indexes.")

        for event_class, columns, name_suffix in INDEX_DEFINITIONS:
            try:
                # Dynamically get the table name
                table_name = db_store.get_table_name_from_class(event_class)
            except Exception as e:
                 log.error(f"Could not determine table name for {event_class.__name__}: {e}")
                 all_tables_exist = False
                 continue # Skip this index if table name fails

            # Check if the base table exists before trying to create an index on it
            query_table_exists = """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = $1
                );
            """
            table_exists = await conn.fetchval(query_table_exists, table_name)

            if not table_exists:
                log.warning(f"Base table '{table_name}' does not exist. Skipping index creation.")
                all_tables_exist = False
                continue # Skip to the next index definition

            # Construct a consistent index name
            # Format: idx_tableName_col1_col2_suffix
            column_names = '_'.join(columns)
            # Limit length of generated index names if needed (PostgreSQL limit is typically 63 chars)
            base_index_name = f"{table_name}_idx_{column_names}{name_suffix}"
            index_name = base_index_name[:63] # Truncate if necessary

            # Construct the columns string for SQL (handling DESC)
            sql_columns = []
            for col in columns:
                # Simple check for 'tsz' to add DESC, adjust if other columns need DESC
                if col == 'tsz':
                    sql_columns.append(f"{col} DESC")
                else:
                    sql_columns.append(col)
            sql_columns_str = ", ".join(sql_columns)


            # Construct the full SQL command
            index_sql = f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {table_name} ({sql_columns_str});
            """

            log.info(f"Ensuring index '{index_name}' on table '{table_name}'.")
            # Use conn.execute() for DDL commands that don't return rows
            status = await conn.execute(index_sql)
            log.info(f"Command executed for '{index_name}', status: {status}")

        if all_tables_exist:
            log.info("Finished ensuring all defined indexes on existing tables.")
        else:
            log.warning("Finished ensuring indexes, but some base tables were missing.")


    except Exception as e:
        log.exception("Error while ensuring indexes:") # Log full traceback
    finally:
        if conn:
            await conn.close()
            log.info("Database connection closed.")

async def main():
    await ensure_indexes()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())