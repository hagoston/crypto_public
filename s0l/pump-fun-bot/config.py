import os

from solders.pubkey import Pubkey


def _env(name: str, default: str = "") -> str:
    """Read runtime secrets from the environment instead of committing them."""
    return os.getenv(name, default)

RAYDIUM_LIQUIDITY_POOL_V4 = Pubkey.from_string("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8")
# System & pump.fun addresses
PUMP_PROGRAM = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
PUMP_AMM_PROGRAM = Pubkey.from_string("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")
PUMP_AMM_EVENT_AUTHORITY = Pubkey.from_string("GS4CU59F31iL7aR2Q8zVS8DRrcRnXX1yjQ66TqNVQnaR")
PUMP_MINT_PROGRAM = Pubkey.from_string("39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg")
PUMP_GLOBAL = Pubkey.from_string("4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf")
PUMP_EVENT_AUTHORITY = Pubkey.from_string("Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1")
PUMP_FEE = Pubkey.from_string("CebN5WGQ4jvEPvsVU4EoHEpgzq1VV7AbicfhtW4xC9iM")
PUMP_LIQUIDITY_MIGRATOR = Pubkey.from_string("39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg")

# raydium lanchpad tokens
RAYDIUM_LAUNCHPAD = Pubkey.from_string("LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj")
RAYDIUM_LAUNCHPAD_EVENT_AUTHORITY = Pubkey.from_string("2DPAtwB8L12vrMRExbLuyGnC7n2J5LNoZQSejeQGpwkr")
# raydium launchpad tokens migrates to migrate_to_amm or migrate_to_cpswap
RAYDIUM_CPMM_PROGRAM = Pubkey.from_string("CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C")

SYSTEM_PROGRAM = Pubkey.from_string("11111111111111111111111111111111")
SYSTEM_TOKEN_PROGRAM = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
SYSTEM_ASSOCIATED_TOKEN_ACCOUNT_PROGRAM = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
SYSTEM_RENT = Pubkey.from_string("SysvarRent111111111111111111111111111111111")

SOL = Pubkey.from_string("So11111111111111111111111111111111111111112")
USD1: Pubkey = Pubkey.from_string("USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB")

LAMPORTS_PER_SOL = 1_000_000_000  # Lamports to SOL conversion
DEFAULT_TOKEN_DECIMALS = 6
TOTAL_SUPPLY = 1_000_000_000

# Trading parameters
BUY_AMOUNT = 0.0001  # Amount of SOL to spend when buying
BUY_SLIPPAGE = 0.2  # 20% slippage tolerance for buying
SELL_SLIPPAGE = 0.2  # 20% slippage tolerance for selling

# RPC and stream endpoints. Public defaults are usable for read-only RPC calls;
# low-latency gRPC/WebSocket providers should be supplied through environment variables.
SOLANA_RPC_URL = _env("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
RPC_ENDPOINT = _env("RPC_ENDPOINT", SOLANA_RPC_URL)
WSS_ENDPOINT = _env("WSS_ENDPOINT", "ws://127.0.0.1:8900")

# Shyft API configuration
SHYFT_X_TOKEN = _env("SHYFT_X_TOKEN")
SHYFT_RPC_FQDN = _env("SHYFT_RPC_FQDN", "grpc.ny.shyft.to")

# https://erpc.global/en/
ERPC_X_TOKEN = _env("ERPC_X_TOKEN")
ERPC_RPC_FQDN = _env("ERPC_RPC_FQDN", "grpc-ams1.validators.solutions")

# SolanaVibeStation
SOLANAVIBESTATION_X_TOKEN = _env("SOLANAVIBESTATION_X_TOKEN")
SOLANAVIBESTATION_RPC_FQDN = _env("SOLANAVIBESTATION_RPC_FQDN", "grpc.solanavibestation.com:10000")

# Optional base58 private key used by manual sandbox trading scripts.
PRIVATE_KEY = _env("SOLANA_PRIVATE_KEY")

# storage
PG_CONNECTION = _env("PG_CONNECTION", "postgres://postgres:postgres@localhost:5432/postgres")

PG_UPLOAD_BATCH_SIZE = 50  # Number of items to accumulate before uploading
PG_UPLOAD_BATCH_TIMEOUT = 5  # Time (in seconds) to wait before uploading an incomplete batch

# docker run -d --name pumpfundata -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e PGDATA=/var/lib/postgresql/data -v pumpfundata:/var/lib/postgresql/data timescale/timescaledb-ha:pg17
