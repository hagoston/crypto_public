from typing import NamedTuple
from anchorpy import Event
from config import (
    PUMP_PROGRAM, 
    RAYDIUM_LAUNCHPAD, 
    PUMP_AMM_PROGRAM,
    USD1
)
from spl.token.constants import WRAPPED_SOL_MINT


# https://solscan.io/tx/2R43Eq7hRvi7BqKsGiiFYMEoxQsPsrhfhEos3WWUQBeP6PtfmrnzB2Dqn1cV5ximj64c8FhPp9GXKTQXcyM4nodt
class PumpFunAmmTradeEvent(NamedTuple):
    timestamp: int
    is_buy: bool
    amount_in: int
    amount_out: int
    pool_base_token_reserves: int
    pool_quote_token_reserves: int
    protocol_fee: int
    owner: str
    pool: str
    _event_name = "PumpFunAmmTrade"

# https://solscan.io/tx/37nfLC11wAAvHU1uNegHYkiGVNYUUBRg1KzBWWZun1jAwuAzrGMmvKERtPezDKFYacMk7Ua86Hr87ktqyHaLYYcL
class PumpFunAmmDepositEvent(NamedTuple):
    timestamp: int
    lp_token_amount_out: int
    max_base_amount_in: int
    max_quote_amount_in: int
    user_base_token_reserves: int
    user_quote_token_reserves: int
    pool_base_token_reserves: int
    pool_quote_token_reserves: int
    base_amount_in: int
    quote_amount_in: int
    lp_mint_supply: int
    pool: str
    user_: str
    user_base_token_account: str
    user_quote_token_account: str
    user_pool_token_account: str
    _event_name = "PumpFunAmmDeposit"

## PumpFun AMM create pool
# https://solscan.io/tx/2gwL4eCyFH9eEtGxFV7orp46QQKmY8JxRh4j59SCgUut3SSt3vrA5QGhJAzeATr2ZveDNxP5K6UZztkHJv8AsJPi
class PumpFunAmmCreatePoolEvent(NamedTuple):
    timestamp: int  
    index: int  
    creator: str  
    base_mint: str  
    quote_mint: str  
    base_mint_decimals: int  
    quote_mint_decimals: int  
    base_amount_in: int  
    quote_amount_in: int  
    pool_base_amount: int  
    pool_quote_amount: int  
    minimum_liquidity: int  
    initial_liquidity: int  
    lp_token_amount_out: int  
    pool_bump: int  
    pool: str  
    lp_mint: str  
    user_base_token_account: str  
    user_quote_token_account: str
    _event_name = "PumpFunAmmCreatePool"

## PumpFun AMM CompletePumpAmmMigrationEvent
# https://solscan.io/tx/3itWVfXHZYBAvdKs7L4SuXkfaMFsqz47bv5nqzpQYujBkgg31tMdyZuiPbej3vrx1YaeBLDqmCxFwftyLR6z7jTW #3.41
class PumpFunAmmCompleteMigrationEvent(NamedTuple):
    user_: str
    mint: str
    mint_amount: int
    sol_amount: int
    pool_migration_fee: int
    bonding_curve: str
    timestamp: int
    pool: str
    _event_name = "PumpFunAmmCompleteMigration"

## PumpFun AMM widthraw
# https://solscan.io/tx/rjexmREaWbFdEP7HvNG98kyiWLnrkasJjPtcdc1DpeyrMdft8FfdtXrEvBkoMbsyXSx7WzGsYEVnY6Z2Zih4E1U
class PumpFunAmmWithdrawEvent(NamedTuple):
    timestamp: int  
    lp_token_amount_in: int  
    min_base_amount_out: int  
    min_quote_amount_out: int  
    user_base_token_reserves: int  
    user_quote_token_reserves: int  
    pool_base_token_reserves: int  
    pool_quote_token_reserves: int  
    base_amount_out: int  
    quote_amount_out: int  
    lp_mint_supply: int  
    pool: str  
    user_: str  
    user_base_token_account: str  
    user_quote_token_account: str  
    user_pool_token_account: str  
    _event_name = "PumpFunAmmWithdraw"

## RaydiumV4 creation of a new liquidity pool
# https://solscan.io/tx/2QvPu378tn4Wwa2JjJkSk7AjSqi92npNB66CFRBeMWRz2cp31quxNWH5MsK56rYBqhSvX9w68TFLP8S6xNQAe5Xn
class RaydiumV4Initialize2Event(NamedTuple):
    nonce: int
    init_pc_amount: int
    init_coin_amount: int
    coin_mint: str
    pc_mint: str
    pool_coin_token_account: str
    pool_pc_token_account: str
    _event_name = "RaydiumV4Initialize2"

## RaydiumV4 deposit token pairs into the pool, increasing its liquidity
# https://solscan.io/tx/4ER5yWTrXCZanbyGz8QyoYq8J2QugLMzVxWppH91Nf1VAhpdZ4Hyvy6wbcB1N7Cwc9ph7Y3hQb5YrMWKuNHQu5ai
class RaydiumV4AddLiquidityEvent(NamedTuple):
    coin_amount: int
    pc_amount: int
    mint_lp_token_amount: int
    pool_pc_token_account: str
    _event_name = "RaydiumV4AddLiquidity"

## RaydiumV4 remove liquidity
# https://solscan.io/tx/aJZWHa5PKKL74r7ECrwTeD5w22ifVeP6ATT4PNuu6dxBD8bmRv7USPSGrPpzpdqwCSXi5ERo2kVCLqg9ZGRW3nc
class RaydiumV4RemoveLiquidityEvent(NamedTuple):
    coin_amount: int
    pc_amount: int
    burn_lp_token_amount: int
    pool_pc_token_account: str
    _event_name = "RaydiumV4RemoveLiquidity"

## RaydiumV4 withdrawPnl
# https://solscan.io/tx/672T8fe7pKj6cyJwmuz2X1qtF4pnHuUGUCkNaEjU5Vxvx1DcM8azKHcEFo8BD2x1f7Hso1EFYrXWZhrBkTAwfBSD
class RaydiumV4WithdrawPnlEvent(NamedTuple):
    coin_amount: int
    pc_amount: int
    pool_pc_token_account: str
    _event_name = "RaydiumV4WithdrawPnl"

## RaydiumV4 swap
# https://solscan.io/tx/5YPQqdnoRSviyZM8motpLhRck7BvuR3MoDedviywMGyNn1CcVvQ9Pv5nTqjD5qvMyV23xKrCe1SkbL2Mq65a9FP2
class RaydiumV4SwapEvent(NamedTuple):
    is_buy: bool
    amount_in: int
    amount_out: int
    owner: str
    pool_pc_token_account: str
    _event_name = 'RaydiumV4Swap'

## PumpFun remove liquidity
# https://solscan.io/tx/5PLQ8mdSpQf4qcq7XTSSch3d1vR76vWXtTaX5yyCb84DDJEKLcCTZA8MdEqmx6QpLxBEvC3S9EWpwPqydBeu5RhJ
class PumpFunRemoveLiquidityEvent(NamedTuple):
    mint: str
    amount: int
    _event_name = 'PumpFunRemoveLiquidity'

## PumpFun trade
# https://solscan.io/tx/5HvP6g8gZZspThJUvGyoqDaTchyEobqFHpqy7o9BoQrbsSLLRZY1GZtZnvQvgVTvdWo8jGvMjf7nRexfw1uC14LQ
class PumpFunTradeEvent(NamedTuple):
    is_buy: bool
    sol_amount: int
    token_amount: int
    virtual_sol_reserves: int
    virtual_token_reserves: int
    owner: str
    mint: str
    _event_name = 'PumpFunTrade'

## PumpFun create event
# https://solscan.io/tx/5SLfxkDsDKnCCdN12L3BVCjC5QqVJq2aSHm3exbBCZMGFHHvU1FBpY44sUNk74t6XgxmP7XanviaFHpv5g41oYuJ
class PumpFunCreateEvent(NamedTuple):
    name: str
    symbol: str
    uri: str
    mint: str
    bonding_curve: str
    owner: str
    _event_name = 'PumpFunCreate'

## PumpFun complete event
# https://solscan.io/tx/3J98pLbj4PERTGqbZYs4YDsPCQAXRG1izZmEyFf3qjUUKwjFUzCrrxYr1ByWWNGDuu1oyCpeqbAjWGBH86oBddKf
class PumpFunCompleteEvent(NamedTuple):
    mint: str
    bonding_curve: str
    owner: str
    _event_name = 'PumpFunComplete'

## PumpFun SetMetaplexCreatorEvent
# https://solscan.io/tx/NMAufeDGVgZzxi8jX1FUUZ4bzUAsZu4BWqAY9RKUrjKZeDuQyMpb9XzMMsCsi6qsKWpqdfaXzkBKSKVKSEDVjtF
class PumpFunSetMetaplexCreatorEvent(NamedTuple):
    timestamp: int
    mint: str
    bonding_curve: str
    metadata: str
    creator: str
    _event_name = "PumpFunSetMetaplexCreator"

## Raydium launchpad trade
# https://solscan.io/tx/2z8RsV5Jor7ysair39DGZB4BVGVjGG8s8ThNmSYfNbkEDXKjVLqdXME7j7HcAMcTLdFaTHXZgoFWfJgJPNcLk1Ji
class RaydiumLaunchpadTradeEvent(NamedTuple):
    is_buy: bool
    amount_in: int
    amount_out: int
    virtual_base_reserves: int
    virtual_quote_reserves: int
    real_base_reserves_after: int
    real_quote_reserves_after: int
    owner: str  # The user/payer initiating the swap
    mint: str
    _event_name = 'RaydiumLaunchpadTrade'

## Raydium launchpad pool create
# Based on CPI log and IDL
class RaydiumLaunchpadPoolCreateEvent(NamedTuple):
    pool_state: str
    creator: str
    mint: str
    quote_mint: str     # could be SOL or USD1
    config: str
    base_mint_decimals: int
    base_mint_name: str
    base_mint_symbol: str
    base_mint_uri: str
    curve_type: str
    vesting_total_locked_amount: int
    vesting_cliff_period: int
    vesting_unlock_period: int
    supply: int
    _event_name = 'RaydiumLaunchpadPoolCreate'


## Raydium launchpad migrate to amm
class RaydiumLaunchpadMigrateToAmmEvent(NamedTuple):
    base_mint: str
    quote_mint: str
    _event_name = 'RaydiumLaunchpadMigrateToAmm'

## Raydium CPMM swap event
# https://solscan.io/tx/31cxSSYiam3EbKVqCBtY77kUtz45Ym8zw8rosTDEUZ9nZLKbUTGGPwpJ5zL5YPp62jFUsoLgyB3aM79moKgaseYE
class RaydiumCPMMSwapEvent(NamedTuple):
    is_buy: bool
    amount_in: int
    amount_out: int
    owner: str
    mint: str
    _event_name = 'RaydiumCPMMSwap'

## Raydium CPMM initialize
# https://solscan.io/tx/12oaxGcDQew5hjQ3vEGEBgvwSL1ov5NSsoezxZ2NzjxvhWgsRWAKXwTQXzkDU3NqJNyo4ibHop7wM3cP6pQzwZz
class RaydiumCPMMInitializeEvent(NamedTuple):
    amm_config: str
    pool_state: str
    token0_mint: str
    token1_mint: str
    lp_mint: str
    token0_vault: str
    token1_vault: str
    observation_state: str
    init_amount0: int
    init_amount1: int
    open_time: int
    _event_name = 'RaydiumCPMMInitialize'

## -------------------------------------------------------------------------------------------------------------
def event_converter(ein: Event, program_id, additional_data=None):
    if program_id == str(PUMP_PROGRAM) or program_id == str(PUMP_AMM_PROGRAM): # TODO split
        if ein.name == 'TradeEvent':
            return PumpFunTradeEvent(
                is_buy=ein.data.is_buy,
                sol_amount=ein.data.sol_amount,
                token_amount=ein.data.token_amount,
                virtual_sol_reserves=ein.data.virtual_sol_reserves,
                virtual_token_reserves=ein.data.virtual_token_reserves,
                owner=str(ein.data.user),
                mint=str(ein.data.mint)
            )
        elif ein.name == 'CreateEvent':
            return PumpFunCreateEvent(
                name = ein.data.name,
                symbol = ein.data.symbol,
                uri = ein.data.uri,
                mint = str(ein.data.mint),
                bonding_curve = str(ein.data.bonding_curve),
                owner = str(ein.data.user)
            )
        elif ein.name == 'CompleteEvent':
            return PumpFunCompleteEvent(
                mint = str(ein.data.mint),
                bonding_curve = str(ein.data.bonding_curve),
                owner = str(ein.data.user)
            )
        elif ein.name == 'CreatePoolEvent':
            return PumpFunAmmCreatePoolEvent(
                timestamp = ein.data.timestamp,
                index = ein.data.index,
                creator = str(ein.data.creator),
                base_mint = str(ein.data.base_mint),
                quote_mint = str(ein.data.quote_mint),
                base_mint_decimals = ein.data.base_mint_decimals,
                quote_mint_decimals = ein.data.quote_mint_decimals,
                base_amount_in = ein.data.base_amount_in,
                quote_amount_in = ein.data.quote_amount_in,
                pool_base_amount = ein.data.pool_base_amount,
                pool_quote_amount = ein.data.pool_quote_amount,
                minimum_liquidity = ein.data.minimum_liquidity,
                initial_liquidity = ein.data.initial_liquidity,
                lp_token_amount_out = ein.data.lp_token_amount_out,
                pool_bump = ein.data.pool_bump,
                pool = str(ein.data.pool),
                lp_mint = str(ein.data.lp_mint),
                user_base_token_account = str(ein.data.user_base_token_account),
                user_quote_token_account = str(ein.data.user_quote_token_account)
            )
        elif ein.name == 'BuyEvent':
            return PumpFunAmmTradeEvent(
                timestamp = ein.data.timestamp,
                is_buy = True,
                amount_in = ein.data.quote_amount_in_with_lp_fee,   # token
                amount_out = ein.data.base_amount_out,              # SOL in lamports
                pool_base_token_reserves = ein.data.pool_base_token_reserves,
                pool_quote_token_reserves = ein.data.pool_quote_token_reserves,
                protocol_fee = ein.data.protocol_fee,
                owner = str(ein.data.user),
                pool = str(ein.data.pool)
            )
        elif ein.name == 'SellEvent':
            return PumpFunAmmTradeEvent(
                timestamp = ein.data.timestamp,
                is_buy = False,
                amount_in = ein.data.base_amount_in,
                amount_out = ein.data.user_quote_amount_out,
                pool_base_token_reserves = ein.data.pool_base_token_reserves,
                pool_quote_token_reserves = ein.data.pool_quote_token_reserves,
                protocol_fee = ein.data.protocol_fee,
                owner = str(ein.data.user),
                pool = str(ein.data.pool)
            )
        elif ein.name == 'DepositEvent':
            return PumpFunAmmDepositEvent(
                timestamp = ein.data.timestamp,
                lp_token_amount_out = ein.data.lp_token_amount_out,
                max_base_amount_in = ein.data.max_base_amount_in,
                max_quote_amount_in = ein.data.max_quote_amount_in,
                user_base_token_reserves = ein.data.user_base_token_reserves,
                user_quote_token_reserves = ein.data.user_quote_token_reserves,
                pool_base_token_reserves = ein.data.pool_base_token_reserves,
                pool_quote_token_reserves = ein.data.pool_quote_token_reserves,
                base_amount_in = ein.data.base_amount_in,
                quote_amount_in = ein.data.quote_amount_in,
                lp_mint_supply = ein.data.lp_mint_supply,
                pool = str(ein.data.pool),
                user_ = str(ein.data.user),
                user_base_token_account = str(ein.data.user_base_token_account),
                user_quote_token_account = str(ein.data.user_quote_token_account),
                user_pool_token_account = str(ein.data.user_pool_token_account)
            )
        elif ein.name == 'WithdrawEvent':
            return PumpFunAmmWithdrawEvent(
                timestamp = ein.data.timestamp,
                lp_token_amount_in = ein.data.lp_token_amount_in,
                min_base_amount_out = ein.data.min_base_amount_out,
                min_quote_amount_out = ein.data.min_quote_amount_out,
                user_base_token_reserves = ein.data.user_base_token_reserves,
                user_quote_token_reserves = ein.data.user_quote_token_reserves,
                pool_base_token_reserves = ein.data.pool_base_token_reserves,
                pool_quote_token_reserves = ein.data.pool_quote_token_reserves,
                base_amount_out = ein.data.base_amount_out,
                quote_amount_out = ein.data.quote_amount_out,
                lp_mint_supply = ein.data.lp_mint_supply,
                pool = str(ein.data.pool),
                user_ = str(ein.data.user),
                user_base_token_account = str(ein.data.user_base_token_account),
                user_quote_token_account = str(ein.data.user_quote_token_account),
                user_pool_token_account = str(ein.data.user_pool_token_account)
            )
        elif ein.name == 'SetMetaplexCreatorEvent':
            return PumpFunSetMetaplexCreatorEvent(
                timestamp=ein.data.timestamp,
                mint=str(ein.data.mint),
                bonding_curve=str(ein.data.bonding_curve),
                metadata=str(ein.data.metadata),
                creator=str(ein.data.creator)
            )
        elif ein.name == 'CompletePumpAmmMigrationEvent':
            return PumpFunAmmCompleteMigrationEvent(
                user_=str(ein.data.user),
                mint=str(ein.data.mint),
                mint_amount=ein.data.mint_amount,
                sol_amount=ein.data.sol_amount,
                pool_migration_fee=ein.data.pool_migration_fee,
                bonding_curve=str(ein.data.bonding_curve),
                timestamp=ein.data.timestamp,
                pool=str(ein.data.pool)
            )
    elif program_id == str(RAYDIUM_LAUNCHPAD):
        if ein.name == 'TradeEvent':
            if additional_data is None:
                raise Exception(f"ERROR event_converter(): RAYDIUM_LAUNCHPAD.{ein.name} missing additional data")
            elif 'payer' not in additional_data:
                raise Exception(f"ERROR event_converter(): RAYDIUM_LAUNCHPAD.{ein.name} missing payer/owner address")
            elif additional_data['quote_token_mint'] not in [str(WRAPPED_SOL_MINT), str(USD1)]:
                raise Exception(f"ERROR event_converter(): RAYDIUM_LAUNCHPAD.{ein.name} quote token != WSOL")
            
            return RaydiumLaunchpadTradeEvent(
                is_buy=type(ein.data.trade_direction).__name__ == 'Buy',
                amount_in=ein.data.amount_in,
                amount_out=ein.data.amount_out,
                virtual_base_reserves=ein.data.virtual_base,
                virtual_quote_reserves=ein.data.virtual_quote,
                real_base_reserves_after=ein.data.real_base_after,
                real_quote_reserves_after=ein.data.real_quote_after,
                owner=additional_data['payer'],
                mint=additional_data['base_token_mint']
            )
        elif ein.name == 'PoolCreateEvent':
            if additional_data is None or 'base_mint' not in additional_data:
                raise Exception(f"ERROR event_converter(): RAYDIUM_LAUNCHPAD.{ein.name} missing base_mint")
            if additional_data is None or 'quote_mint' not in additional_data:
                raise Exception(f"ERROR event_converter(): RAYDIUM_LAUNCHPAD.{ein.name} missing quote_mint")
            return RaydiumLaunchpadPoolCreateEvent(
                pool_state=str(ein.data.pool_state),
                creator=str(ein.data.creator),
                mint=str(additional_data['base_mint']),
                quote_mint=str(additional_data['quote_mint']),
                config=str(ein.data.config),
                base_mint_decimals=ein.data.base_mint_param.decimals,
                base_mint_name=ein.data.base_mint_param.name,
                base_mint_symbol=ein.data.base_mint_param.symbol,
                base_mint_uri=ein.data.base_mint_param.uri,
                curve_type=type(ein.data.curve_param).__name__,
                vesting_total_locked_amount=ein.data.vesting_param.total_locked_amount,
                vesting_cliff_period=ein.data.vesting_param.cliff_period,
                vesting_unlock_period=ein.data.vesting_param.unlock_period,
                supply=ein.data.curve_param.data.supply     # all types has supply (Constant, Fixed, LinearCurve)
            )
    
    if ein.name in ['CollectCoinCreatorFeeEvent',
                    'CollectCreatorFeeEvent',
                    'SetCreatorEvent',
                    'SetMetaplexCoinCreatorEvent',
                    'ExtendAccountEvent',
                    'SetBondingCurveCoinCreatorEvent',
                    'CloseUserVolumeAccumulatorEvent',
                    'InitUserVolumeAccumulatorEvent',
                    'AdminSetCoinCreatorEvent',
                    'AdminSetCreatorEvent']:
        return None # Explicitly ignore this event
    else:
        raise Exception(f"ERROR event_converter(): unknown event ({ein.name})")

KNOWN_EVENT_TYPES = [
    #RaydiumV4Initialize2Event,
    #RaydiumV4AddLiquidityEvent,
    #RaydiumV4RemoveLiquidityEvent,
    #RaydiumV4SwapEvent,
    #RaydiumV4WithdrawPnlEvent,
    PumpFunRemoveLiquidityEvent,
    PumpFunTradeEvent,
    PumpFunCreateEvent,
    PumpFunCompleteEvent,
    PumpFunSetMetaplexCreatorEvent,
    PumpFunAmmCreatePoolEvent,
    PumpFunAmmCompleteMigrationEvent,
    PumpFunAmmTradeEvent,
    PumpFunAmmDepositEvent,
    PumpFunAmmWithdrawEvent,
    RaydiumLaunchpadTradeEvent,
    RaydiumLaunchpadPoolCreateEvent,
    RaydiumLaunchpadMigrateToAmmEvent,
    RaydiumCPMMSwapEvent,
    RaydiumCPMMInitializeEvent
]
KNOWN_EVENTS = {e._event_name: e for e in KNOWN_EVENT_TYPES}
