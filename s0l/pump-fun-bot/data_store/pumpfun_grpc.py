from typing import Optional, Dict, Any
import asyncio
import grpc
import geyser_pb2
import geyser_pb2_grpc
import logging
import sys
import os
import time
import base58
import db_store
import hashlib
import uuid
import binascii
from pyheck import snake
from datetime import datetime, timezone
from anchorpy import Idl, Coder
from anchorpy import Event, EventParser, InstructionCoder
import argparse
import cProfile
import pstats
from functools import lru_cache

from collections.abc import AsyncIterator
from geyser_pb2 import SubscribeRequest, SubscribeRequestFilterTransactions, CommitmentLevel
from geyser_pb2_grpc import GeyserStub

from pumpfun_event_types import *
from spl.token.constants import WRAPPED_SOL_MINT, TOKEN_2022_PROGRAM_ID
from spl.token.instructions import get_associated_token_address
from solders.pubkey import Pubkey
from utils.telegram_handler import send_telegram_message, get_telegram_updates

'''
sample code
    https://github.com/Shyft-to/solana-defi/tree/main/PumpFun
    https://github.com/rpcpool/yellowstone-grpc/tree/master/examples/python
'''
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.logger_factory import get_logger
log = get_logger('grpc')
from config import *

THIS_PATH = os.path.dirname(os.path.abspath(__file__))
SKIP_DB = False
FROM_FILE = False
SAVE_SERIALIZED_UPDATE = False
ALL_RAY_SUB = True
MSG_FILTER = {
#   <instruction program_id filter>: list(<what to decode>) }
    str(PUMP_PROGRAM)                : [str(PUMP_PROGRAM), str(SYSTEM_TOKEN_PROGRAM)],                    # widthraw / remove liquidity e.g.: https://solscan.io/tx/5PLQ8mdSpQf4qcq7XTSSch3d1vR76vWXtTaX5yyCb84DDJEKLcCTZA8MdEqmx6QpLxBEvC3S9EWpwPqydBeu5RhJ
##    str(RAYDIUM_LIQUIDITY_POOL_V4)   : [str(RAYDIUM_LIQUIDITY_POOL_V4), str(SYSTEM_TOKEN_PROGRAM)],      # raydium swaps    e.g.: https://solscan.io/tx/2QHypU6XQtnQZSpXWTEpco2yBW6DJAH6K5ppz4VKo8DBTvhameuG6EiKeKYF7itBJKCu2YSfa5KPffrt4gGB5dAA
    str(PUMP_AMM_PROGRAM)            : [str(PUMP_AMM_PROGRAM), str(SYSTEM_TOKEN_PROGRAM)],                # pumpfun swap AMM e.g.: https://solscan.io/tx/5LU1KP7EAM321dTPAFzuBdqSHP92FczV9ZroXnyjqsFdhEVkukDZyQSMQGPQwq7p3kisdCSa9RrVS21z7XHXmodd
    str(RAYDIUM_LAUNCHPAD)           : [str(RAYDIUM_LAUNCHPAD), str(RAYDIUM_CPMM_PROGRAM)],               # RAYDIUM_CPMM_PROGRAM -> graduation tracking CPMM.initialize after launchpad.migrate_to_cpswap
    str(RAYDIUM_CPMM_PROGRAM)        : [str(RAYDIUM_CPMM_PROGRAM), str(SYSTEM_TOKEN_PROGRAM)]
}

# global vars and caches
event_parsers = {}
coders = {}

# Performance optimization caches
_base58_cache = {}  # Cache for base58 encoding
_account_address_cache = {}  # Cache for processed account addresses
_signature_cache = {}  # Cache for transaction signatures
_decoder_cache = {}  # Cache for instruction decoders

# Cache size limits to prevent memory leaks
MAX_CACHE_SIZE = 10000

def clear_caches_if_needed():
    """Clear caches if they get too large to prevent memory leaks"""
    global _base58_cache, _account_address_cache, _signature_cache, _decoder_cache
    
    if len(_base58_cache) > MAX_CACHE_SIZE:
        _base58_cache.clear()
    if len(_account_address_cache) > MAX_CACHE_SIZE:
        _account_address_cache.clear()
    if len(_signature_cache) > MAX_CACHE_SIZE:
        _signature_cache.clear()
    if len(_decoder_cache) > MAX_CACHE_SIZE:
        _decoder_cache.clear()

def cached_b58encode(data: bytes) -> str:
    """Cached version of base58 encoding to avoid redundant computations"""
    # Use bytes as key since they're hashable
    if data in _base58_cache:
        return _base58_cache[data]
    
    result = base58.b58encode(data).decode()
    _base58_cache[data] = result
    return result

def process_account_addresses_batch(account_keys, loaded_writable, loaded_readonly):
    """Batch process account addresses with caching"""
    # Create a cache key from the combination of all address lists
    cache_key = (tuple(account_keys), tuple(loaded_writable), tuple(loaded_readonly))
    
    if cache_key in _account_address_cache:
        return _account_address_cache[cache_key]
    
    # Process all addresses in one go
    account_addresses = []
    
    # Process account_keys
    for k in account_keys:
        account_addresses.append(cached_b58encode(bytes(k)))
    
    # Process loaded addresses
    for k in loaded_writable:
        account_addresses.append(cached_b58encode(bytes(k)))
    
    for k in loaded_readonly:
        account_addresses.append(cached_b58encode(bytes(k)))
    
    _account_address_cache[cache_key] = account_addresses
    return account_addresses

def get_next_sim_file():
    folder_path = f'{THIS_PATH}/serialized_txs/error_new/'
    #folder_path = f'{THIS_PATH}/serialized_txs/raydium_launchpad/'
    #folder_path = f'{THIS_PATH}/serialized_txs/raydium_cpmm/'
    #folder_path = f'{THIS_PATH}/serialized_txs/migration/'
    #folder_path = f'{THIS_PATH}/serialized_txs/raydium_swaps/'
    #folder_path = f'{THIS_PATH}/serialized_txs/pump_program/'
    
    for filename in sorted(os.listdir(folder_path)):
        log.info(f'https://solscan.io/tx/{filename.split("_")[-1].split(".")[0]}')
        yield folder_path+filename

def get_idl(program_id):
    # IDL files are named with the program id suffix, which lets the decoder
    # support several Solana programs without hard-coding every file path.
    idl_folder_path = f'{THIS_PATH}/../idl/'
    idl_file_path = None
    for filename in os.listdir(idl_folder_path):
        # Check if the file starts with the specified prefix
        if filename.endswith(f'{program_id}.json'):
            # Join the folder path with the filename to get the full path
            idl_file_path = os.path.join(idl_folder_path, filename)
            break
    if idl_file_path is None:
        log.info(f'no idl for {program_id}')
        exit()
    with open(idl_file_path) as f:
        raw_idl = f.read()
    return Idl.from_json(raw_idl)

@lru_cache(maxsize=128)
def get_coder(program_id):
    if program_id not in coders:
        idl = get_idl(program_id)
        coders[program_id] = (Coder(idl), idl)
    return coders[program_id]

@lru_cache(maxsize=128)
def get_event_parser(program_id):
    if program_id not in event_parsers:
        idl = get_idl(program_id)
        coder = Coder(idl)
        # parsing with anychorpy
        event_parsers[program_id] = EventParser(program_id, coder)
    return event_parsers[program_id]

def _triton_sign_request(
    callback: grpc.AuthMetadataPluginCallback,
    x_token: Optional[str],
    error: Optional[Exception],
):
    metadata = (("x-token", x_token),)
    return callback(metadata, error)

class TritonAuthMetadataPlugin(grpc.AuthMetadataPlugin):
    def __init__(self, x_token: str):
        self.x_token = x_token

    def __call__(
        self,
        context: grpc.AuthMetadataContext,
        callback: grpc.AuthMetadataPluginCallback,
    ):
        return _triton_sign_request(callback, self.x_token, None)
    
def calculate_discriminator(instruction_name):
    # Create a SHA256 hash object
    sha = hashlib.sha256()
    # Update the hash with the instruction name
    sha.update(instruction_name.encode('utf-8'))
    # Get the first 8 bytes of the hash
    return sha.digest()[:8]

class GeyserSubscriber:
    def __init__(
        self,
        provider = "SolanaVibeStation",
        commitment: CommitmentLevel = CommitmentLevel.PROCESSED # CommitmentLevel.CONFIRMED
    ):
        self.amm_account_filter = []
        self.amm_account_filter_track = {}
        self.RAYDIUM_MAX_SEC_TRACK = 18000    # 5 hour
        self.db_data = {}
        self.last_pg_upload_time = time.time()
        self.commitment = commitment
        self.export_list = []
        self.debug_cnt = {}
        self.cache_clear_counter = 0  # Track when to clear caches
        
        # Performance monitoring
        self.perf_metrics = {
            'cache_hits': {'base58': 0, 'account_batch': 0, 'signature': 0},
            'cache_misses': {'base58': 0, 'account_batch': 0, 'signature': 0},
            'total_transactions_processed': 0,
            'start_time': time.time()
        }
        
        self.provider = provider
        if provider == "SolanaVibeStation":
            self._x_token = SOLANAVIBESTATION_X_TOKEN
            self._rpc_fqdn = SOLANAVIBESTATION_RPC_FQDN
        elif provider == "Shyft":
            self._x_token = SHYFT_X_TOKEN
            self._rpc_fqdn = SHYFT_RPC_FQDN
        else:
            raise Exception("unkown provider")
            
        self._request_queue = asyncio.Queue()
        self._stream = None
        self._channel = None
        self._stub = None
        self._running = False

        send_telegram_message(f'data logger started..')

    async def connect(self):
        if not FROM_FILE:
            channel_options = [
                ("grpc.keepalive_time_ms", 8000),
                ("grpc.keepalive_timeout_ms", 5000),
                ("grpc.http2.max_pings_without_data", 5),
                ("grpc.keepalive_permit_without_calls", 1),
            ]
            if self.provider == "SolanaVibeStation":
                # Create an insecure channel to the gRPC service
                self._channel = grpc.aio.insecure_channel(self._rpc_fqdn, options=channel_options)
                # Create a stub (client) for the Geyser service
                self._stub = GeyserStub(self._channel)
            else:
                """Connect to gRPC service and start processing updates"""
                auth = TritonAuthMetadataPlugin(self._x_token)
                ssl_creds = grpc.ssl_channel_credentials()
                call_creds = grpc.metadata_call_credentials(auth)
                combined_creds = grpc.composite_channel_credentials(ssl_creds, call_creds)
                self._channel = grpc.aio.secure_channel(self._rpc_fqdn, credentials=combined_creds, options=channel_options)
                self._stub = GeyserStub(self._channel)
        self._running = True
 
        # Send initial subscription
        await self._update_subscription()

    async def start(self):

        # Initialize the database connection
        if not SKIP_DB:
            await db_store.connect_to_db()
            ## clear db
            #await db_store.drop_tables()
            #exit()
            await db_store.create_tables()
        
        await self.connect()

        # Start reader task
        await self._process_stream()

    async def stop(self):
        """Graceful shutdown"""
        self._running = False
        # Send empty request to unsubscribe
        await self._request_queue.put(SubscribeRequest())
        await self._channel.close()

    async def add_to_amm_account_filter(self, new_account):
        """Update account filter and modify subscription"""
        if new_account not in self.amm_account_filter:
            self.amm_account_filter.append(new_account)
            if not ALL_RAY_SUB:
                await self._update_subscription()

    async def _update_subscription(self):
        """Push new subscription configuration to the queue"""
        request = self._build_request()
        await self._request_queue.put(request)

    def _build_request(self) -> SubscribeRequest:
        """Construct SubscribeRequest with current filters"""
        transactions={
            # Pump program filter
            'pumpfun': SubscribeRequestFilterTransactions(
                vote=False,
                failed=False,
                account_include=[str(PUMP_PROGRAM), str(PUMP_MINT_PROGRAM)]
            ),
        }
        ## Raydium filter with current account_filter
        ## Note: skip raydium as pumpfun moved to own AMM
        #if ALL_RAY_SUB or self.amm_account_filter:
        #    transactions['raydium'] = SubscribeRequestFilterTransactions(
        #        vote=False,
        #        failed=False,
        #        account_include=None if ALL_RAY_SUB else self.amm_account_filter,
        #        account_required=[str(RAYDIUM_LIQUIDITY_POOL_V4)]
        #    )
        # pumpfun swap AMM
        transactions['pumpfun_amm'] = SubscribeRequestFilterTransactions(
                vote=False,
                failed=False,
                account_include=[str(PUMP_AMM_PROGRAM)]
            )

        # raydium launchpad
        transactions['raydium_launchpad'] = SubscribeRequestFilterTransactions(
                vote=False,
                failed=False,
                account_include=[str(RAYDIUM_LAUNCHPAD)]
            )
        
        # raydium CPMM
        transactions['raydium_cpmm'] = SubscribeRequestFilterTransactions(
                vote=False,
                failed=False,
                account_include=[str(RAYDIUM_CPMM_PROGRAM)]
            )
    
        # return with subscribe request
        return SubscribeRequest(
            transactions=transactions,
            commitment=self.commitment
        )

    async def _request_iterator(self) -> AsyncIterator[SubscribeRequest]:
        """Async generator for subscription requests"""
        while self._running:
            yield await self._request_queue.get()

    async def _process_stream(self):
        """Process incoming stream updates"""
        #try:
        if FROM_FILE:
            # read and deserialize
            update = geyser_pb2.SubscribeUpdate()
            for sim_file in get_next_sim_file():
                with open(sim_file, "rb") as file:
                    binary_data = file.read()
                update.ParseFromString(binary_data)
                # call data processing
                await self._process_update(update)
            self._running = False
            
            if not SKIP_DB:
                await db_store.upload_batch(self.db_data, True)
        else:
            stats = {}
            while True:
                try:
                    log.info(f'start..')
                    self._stream = self._stub.Subscribe(self._request_iterator())
                    
                    async for update in self._stream:
                        if update.transaction:
                            # for f in update.filters:
                            #     stats[f] = stats.get(f, 0) + 1
                            await self._process_update(update)
                        
                        # write to databased
                        if self.last_pg_upload_time + PG_UPLOAD_BATCH_TIMEOUT < time.time():
                            # send data to db
                            if not SKIP_DB:
                                # log.info(f"stat :: {', '.join([f'{k}:{v}' for k, v in stats.items()])}")
                                await db_store.upload_batch(self.db_data)
                            else:
                                if len(self.db_data.items()):
                                    sorted_keys = sorted(list(self.db_data.keys()))
                                    print(', '.join([f'{k}:{len(self.db_data[k])}' for k in sorted_keys]))
                            self.db_data = {}
                            self.last_pg_upload_time = time.time()
                            
                            # Periodically clear caches to prevent memory leaks
                            self.cache_clear_counter += 1
                            if self.cache_clear_counter % 100 == 0:  # Every 100 batches
                                clear_caches_if_needed()
                        ##dbg
                        #if time.time() > self.t0 + 10:
                        #    log.info('#### update raydium filter')
                        #    self.t0 = 10**10
                        #    await self.update_amm_account_filter(['CNRS3hzzPz6AQUAW2p2AuWYppNjZVKXHcXk1Maaygvnq'])
                except Exception as e:
                    # dump transation to file to be able to debug
                    log.exception(f'grpc exception')
    
                    tx_info = update.transaction.transaction
                    if tx_info:
                        tx_signature = base58.b58encode(bytes(tx_info.signature)).decode()
                    else:
                        tx_signature=str(uuid.uuid4())
                        log.info(f'no signiture, using uuid = {tx_signature} for dump')
                    self.export_to_file(tx_signature)

                    # send telegram message
                    send_telegram_message(f'grpc exception, time to check contabo')
                    await self.stop()
                    await self.connect()
                
                log.info(f'Reconnecting in 1 second...')
                await asyncio.sleep(1)  # Non-blocking sleep for asynchronous code
    
        #    print(f"Stream error: {e}")
        #finally:
        #    await self.stop()

    def export_to_file(self, tx_signature, idata = None):
        if idata:
            if idata.name in self.export_list:
                return
            self.export_list.append(idata.name)
            log.info(f'## {idata.name} event not found :: https://solscan.io/tx/{tx_signature}')
            log.info(f'idata:: {idata}')
        if FROM_FILE:
            return
        current_timestampz_str = self.current_timestampz.strftime("%Y%m%d_%H%M%S_") + f"{self.current_timestampz.microsecond:06d}"
        tx_fname = current_timestampz_str + '_' + tx_signature + '.bin'
        tx_fpath = f'{THIS_PATH}/serialized_txs/{tx_fname}'
        if not os.path.isfile(tx_fpath):
            with open(tx_fpath, "wb") as f:
                f.write(self.current_update.SerializeToString())
        log.info(f'tx exported to {tx_fname}')


    def rm_old_amm_account_filter_track_items(self):
        # remove old raydium pf pairs
        keys_to_delete = []
        for mint, vd in self.amm_account_filter_track.items():
            if vd['t0'] < time.time()-self.RAYDIUM_MAX_SEC_TRACK:
                if 'pool_addr' in vd:
                    self.amm_account_filter.remove(vd['pool_addr'])
                    log.info(f"removing old pair {mint} :: {vd['pool_addr']}")
                else:
                    log.error(f'No raydium init after complete event?! {mint}')
                keys_to_delete.append(mint)
            else:
                break
        for key in keys_to_delete:
            del self.amm_account_filter_track[key]

    # collect data for db insertion
    def pumpfun_event_handler(self, event, program_id, additional_data = None):
        if event is None:
            return
        
        # convert events coming from log
        if isinstance(event, Event):
            event = event_converter(event, program_id, additional_data)
            if event is None:
                return
        
        # filter
        if 'PumpFunComplete' == event._event_name:
            # Since Python 3.7, regular dict also maintains insertion order
            self.amm_account_filter_track[event.mint] = {
                't0': time.time()
            }
            log.info(f'Complete event for {event.mint}')
        elif 'RaydiumLaunchpadMigrateToAmm' == event._event_name:
            self.amm_account_filter_track[event.base_mint] = {
                't0': time.time()
            }
            log.info(f'Complete event for Raydium Launchpad token (migrate_to_amm) {event.base_mint}')
        elif 'RaydiumV4Initialize2' == event._event_name or 'PumpFunAmmCreatePool' == event._event_name:
            mint_addr = event.pc_mint if 'RaydiumV4Initialize2' == event._event_name else event.base_mint
            pool_addr = event.pool_pc_token_account if 'RaydiumV4Initialize2' == event._event_name else event.pool

            if mint_addr in self.amm_account_filter_track:
                self.amm_account_filter_track[mint_addr]['pool_addr'] = pool_addr
                if pool_addr not in self.amm_account_filter:
                    self.amm_account_filter.append(pool_addr)

                self.rm_old_amm_account_filter_track_items()
                log.info(f'Bounding event for {mint_addr}.. adding {pool_addr}, len(amm_account_filter)={len(self.amm_account_filter)}')
            else:
                return
        elif 'RaydiumV4Swap' == event._event_name and event.pool_pc_token_account not in self.amm_account_filter:
            # not in amm_account_filter
            return
        elif 'PumpFunAmmTrade' == event._event_name and event.pool not in self.amm_account_filter:
            # not in amm_account_filter
            return
        elif 'RaydiumCPMMInitialize' == event._event_name:
            # launchpad token graduation add mint to account_filter
            mint_addr = event.token0_mint if event.token1_mint == str(WRAPPED_SOL_MINT) else event.token1_mint
            pool_addr = mint_addr
            self.amm_account_filter_track[mint_addr] = {
                't0': time.time(),
                'pool_addr': pool_addr  # make bw compatible with old pf bounding to raydium 
            }
            if pool_addr not in self.amm_account_filter:
                self.amm_account_filter.append(pool_addr)
            self.rm_old_amm_account_filter_track_items()
            log.info(f'Bounding event (CPMM) for raydium launchpad token {mint_addr}, len(amm_account_filter)={len(self.amm_account_filter)}')
        
        # common tuple convert, add timestampz and slot number to data
        data_tuple = (self.current_timestampz, self.current_update.transaction.slot) + tuple(event)

        # if event._event_name == 'PumpFunCreate':
        #     print(data_tuple)
        try:
            self.db_data[event._event_name].append(data_tuple)
        except KeyError:
            # Handle the case where the key _event_name does not exist in `db_data`
            self.db_data[event._event_name] = [data_tuple]  # Create a new list with the data_tuple as the first element
        except Exception as e:
            # Handle any other unexpected errors
            log.error(f'ERROR: pumpfun_event_handler({event})')

    async def _process_update(self, update):
        tx_meta = update.transaction.transaction.meta  # geyser_pb2.TransactionStatusMeta
        if len(tx_meta.err.err) or not update.transaction.transaction.signature or not tx_meta.log_messages:
            return

        self.current_timestampz = datetime.now(timezone.utc)
        self.current_update = update

        tx_info = update.transaction.transaction       # geyser_pb2.SubscribeRequestFilterTransactions
        
        #? timestamp :: https://github.com/rpcpool/yellowstone-grpc/issues/452#issuecomment-2476299810
        tx_signature_bytes = bytes(tx_info.signature)
        if tx_signature_bytes in _signature_cache:
            tx_signature = _signature_cache[tx_signature_bytes]
        else:
            tx_signature = base58.b58encode(tx_signature_bytes).decode()
            _signature_cache[tx_signature_bytes] = tx_signature
        
        # Track performance metrics
        self.perf_metrics['total_transactions_processed'] += 1
        #log.info(f'https://solscan.io/tx/{tx_signature}')

        # want to be able to connect multiple events from the same transaction, so use timestamp
        # format the string
        if not FROM_FILE and SAVE_SERIALIZED_UPDATE:
            self.export_to_file(tx_signature)

        ## find instructions which are processed by pumpfun program
        tx_msg = tx_info.transaction.message

        ## find instructions which are processed by selected programs
        # https://solana.com/docs/core/transactions#array-of-account-addresses
        # Use optimized batch processing for account addresses
        account_addresses = process_account_addresses_batch(
            tx_msg.account_keys,
            tx_info.meta.loaded_writable_addresses,
            tx_info.meta.loaded_readonly_addresses
        )

        # get progra id indexes
        program_id_indexes_to_process = []
        for program_id in MSG_FILTER:
            try:
                program_id_index = account_addresses.index(program_id)
                program_id_indexes_to_process.append(program_id_index)
            except:
                # no worries, this transaction does not contain this specific program_id
                continue
        if not program_id_indexes_to_process:
            # thats insteresting as the subscription is based on MSG_FILTER..
            # could be: https://solscan.io/tx/64kWLu8TPzibPtSpo4bYrAkwAwMnfWfPwoaDtGLxoZJoESm9DijZKU3NURVFFCrLKgPhUVX5RjzbCcLp6dHkwQAg
            #log.error(f'no program_id to be processed found in the transaction accounts tx_signature={tx_signature}')
            return

        # iterate through instructions with inner instruction, filter the ones matching MSG_FILTER
        filtered_instructions = []
        for iidx, instruction in enumerate(tx_msg.instructions):
            # https://solana.com/docs/core/transactions#array-of-instructions
            inner_instructions = next((ii.instructions for ii in tx_info.meta.inner_instructions if ii.index == iidx), [])
            # create a list with main and inner instructions
            instruction_list = [instruction]
            instruction_list.extend(inner_instructions)
            # scan for program_id_index
            if instruction_list[0].program_id_index in program_id_indexes_to_process:
                # shortcut..
                filtered_instructions.append(instruction_list)
            else:
                ilist = []
                for i in instruction_list:
                    if ilist:
                        if i.stack_height > ilist[0].stack_height:
                            ilist.append(i)
                        else:
                            filtered_instructions.append(ilist)
                            ilist = []
                    if not ilist and i.program_id_index in program_id_indexes_to_process:
                        # start of instruction to be processed
                        ilist.append(i)
                if ilist:
                    filtered_instructions.append(ilist)

        # process collected instructions
        for instructions in filtered_instructions:
            
            # decode instruction
            decoded_instructions = None
            decoded_instructions = self.decode_instructions(instructions, account_addresses, tx_info)
            try:
                pass
            except Exception as e:
                tx=f'{base58.b58encode(bytes(tx_info.signature)).decode()}'
                log.warning(f'decoding exception ({e}):: https://solscan.io/tx/{tx}')
                self.export_to_file(tx)
            
            if decoded_instructions is None:
                continue
            decoded_instructions_iter = iter(decoded_instructions)

            # get main instruction
            (idata, iaccounts, program_id) = next(decoded_instructions_iter)

            # convert to events
            e = None

            if idata.name in ['extend_account',
                              'collect_creator_fee',
                              'set_creator',
                              'set_coin_creator',
                              'collect_coin_creator_fee',
                              'sync_user_volume_accumulator',
                              'claim_creator_fee',
                              'claim_platform_fee_from_vault',
                              'create_config',
                              'update_config']:
                # Explicitly ignore these
                continue
            # Pumpfun mint program
            elif str(PUMP_PROGRAM) == program_id:
                if idata.name == 'withdraw':
                    e = PumpFunRemoveLiquidityEvent(
                            mint=iaccounts.get('mint', ''),
                            amount=next(decoded_instructions_iter)[0].data.amount
                    )
                elif idata.name in ['migrate']:
                    # Explicitly ignore these
                    continue
            # Raydium liquidity pool
            elif str(RAYDIUM_LIQUIDITY_POOL_V4) == program_id:
                if idata.name == 'swap_base_in':
                    ## take as input the amount of token that the user wants to swap, and the minimum amount of token in output needed to avoid excessive slippage
                    pool_coin_token_account = iaccounts['poolCoinTokenAccount']     # SOL (token account that holds the liquidity for the base currency)
                    pool_pc_token_account = iaccounts['poolPcTokenAccount']         # PF token (token account that holds the liquidity for the quote currency)
                    amount_in = idata.data.amount_in
                    t1_idata, t1_iaccounts, _ = next(decoded_instructions_iter)        # transfer 1: amount_in sized SOL if buy or PF token if sell
                    t2_idata, t2_iaccounts, _ = next(decoded_instructions_iter)        # transfer 2: actual amount out
                    is_buy = t1_iaccounts['destination'] == pool_coin_token_account
                    if (not is_buy) != (t1_iaccounts['destination'] == pool_pc_token_account):
                        raise Exception("is_buy mismatch")
                    if t1_idata.data.amount != amount_in:
                        raise Exception("amount mismatch")
                    # minimum_amount_out = idata.data.minimum_amount_out            # for slippage calculation
                    e = RaydiumV4SwapEvent(
                            is_buy = is_buy,
                            amount_in = amount_in,
                            amount_out = t2_idata.data.amount,
                            owner = iaccounts['userSourceOwner'],
                            pool_pc_token_account = pool_pc_token_account
                        )
                elif idata.name == 'swap_base_out':
                    ## take the amount of token that the user wants to receive, and the maximum amount of token in input needed to avoid excessive slippage
                    pool_coin_token_account = iaccounts['poolCoinTokenAccount']     # SOL (token account that holds the liquidity for the base currency)
                    pool_pc_token_account = iaccounts['poolPcTokenAccount']         # PF token (token account that holds the liquidity for the quote currency)
                    amount_out = idata.data.amount_out
                    t1_idata, t1_iaccounts, _ = next(decoded_instructions_iter)        # transfer 1: actual amount in
                    t2_idata, t2_iaccounts, _ = next(decoded_instructions_iter)        # transfer 2: amount_out sized SOL if buy or PF token if sell
                    is_buy = t1_iaccounts['destination'] == pool_coin_token_account
                    if (not is_buy) != (t1_iaccounts['destination'] == pool_pc_token_account):
                        raise Exception("is_buy mismatch")
                    if t2_idata.data.amount != amount_out:
                        raise Exception("amount mismatch")
                    # max_amount_in = idata.data.max_amount_in            # for slippage calculation
                    e = RaydiumV4SwapEvent(
                            is_buy = is_buy,
                            amount_in = t1_idata.data.amount,
                            amount_out = amount_out,
                            owner = iaccounts['userSourceOwner'],
                            pool_pc_token_account = pool_pc_token_account
                        )
                elif idata.name == 'initialize2':
                    e = RaydiumV4Initialize2Event(
                            nonce=idata.data.nonce,
                            init_pc_amount=idata.data.init_pc_amount,
                            init_coin_amount=idata.data.init_coin_amount,
                            coin_mint=iaccounts.get('coinMint', ''),
                            pc_mint=iaccounts.get('pcMint', ''),
                            pool_coin_token_account=iaccounts.get('poolCoinTokenAccount', ''),
                            pool_pc_token_account=iaccounts.get('poolPcTokenAccount', '')
                        )
                elif idata.name in ['deposit', 'withdraw', 'withdraw_pnl']:
                    pool_coin_token_account = iaccounts['poolCoinTokenAccount']
                    pool_pc_token_account = iaccounts['poolPcTokenAccount']

                    # filter based on account filter
                    if pool_pc_token_account not in self.amm_account_filter:
                        continue

                    t1_idata, t1_iaccounts, _ = next(decoded_instructions_iter)
                    t2_idata, t2_iaccounts, _ = next(decoded_instructions_iter)
                    
                    coin_amount = t1_idata.data.amount
                    pc_amount = t2_idata.data.amount

                    account_dir = 'source' if 'withdraw' in idata.name else 'destination'
                    if t1_iaccounts[account_dir] == pool_pc_token_account:
                        coin_amount, pc_amount = pc_amount, coin_amount
                        if t2_iaccounts[account_dir] != pool_coin_token_account:
                            self.export_to_file(tx_signature)
                            raise Exception("pool mismatch")
                    elif t2_iaccounts[account_dir] != pool_pc_token_account:
                        self.export_to_file(tx_signature)
                        raise Exception("pool mismatch")

                    if idata.name == 'deposit':
                        t3_idata, _, _ = next(decoded_instructions_iter)
                        mint_lp_token_amount = t3_idata.data.amount
                        e = RaydiumV4AddLiquidityEvent(
                                coin_amount = coin_amount,
                                pc_amount=pc_amount,
                                mint_lp_token_amount=mint_lp_token_amount,
                                pool_pc_token_account=pool_pc_token_account
                            )
                    elif idata.name == 'withdraw':
                        t3_idata, _, _ = next(decoded_instructions_iter)
                        burn_lp_token_amount = t3_idata.data.amount
                        e = RaydiumV4RemoveLiquidityEvent(
                                coin_amount=coin_amount,
                                pc_amount=pc_amount,
                                burn_lp_token_amount=burn_lp_token_amount,
                                pool_pc_token_account=pool_pc_token_account
                            )
                    elif idata.name == 'withdraw_pnl':
                        e = RaydiumV4WithdrawPnlEvent(
                                coin_amount=coin_amount,
                                pc_amount=pc_amount,
                                pool_pc_token_account=pool_pc_token_account
                            )
            
            elif str(RAYDIUM_LAUNCHPAD) == program_id:
                if idata.name in ['claim_platform_fee',
                                  'claim_vested_token',
                                  'create_platform_config',
                                  'create_vesting_account',
                                  'update_platform_config']:
                    ## explicitly ignore these
                    # claim_platform_fee
                    #   https://solscan.io/tx/2a9Hji86X8MSLynjATLvAyCkvG4Qsam1T6YFrEiJ7pxd91CbrAhpaLigNUwfTLGx5qozZn9SWKZdaMEDBckD75d6
                    # claim_vested_token
                    #   https://solscan.io/tx/53kqYNJVGYs5c2hq3Ds8nX9WhdTjWThf5bPh7L7PU4yG3ZVgHQekTYf4odVGGsY7DDoumHCdQB2guTAxJzNh2u67
                    # create_platform_config
                    #   https://solscan.io/tx/3FJe4aQ6XVpXDagme8xwokvmFbvUoZvLd43eqNucjbW4LwDBuE2nvZ9idUG98QFL35SEbGj9sKvLUkYXumi29TZn
                    # create_vesting_account
                    #   https://solscan.io/tx/4Knmu2KaRj5kYoJbhapmhx9qf8vAcDL4XbLt3P8fw3wmwGWrVxKXYubncZGsP88zEoN92muhVCMHGycV1nRMVtqc
                    # update_platform_config
                    #   https://solscan.io/tx/3A6ptEJooqqJBvDQVqkVAgKMxXt5TNW8Q66Lg6sh6SYLxqBmkYaJbKqJH7pUQcmjrtQtj4Bq5jruiezA12Li9pLn
                    continue
                elif idata.name == 'migrate_to_amm':
                    # https://solscan.io/tx/4jgPYEBUhMucVpjdxTQHcGVSzVAoBtKRHBVRBre8ego4MUKPChp9dpuAUwY4QAAWF7TLbLLYqv8NwNMcVPpfMmsi
                    e = RaydiumLaunchpadMigrateToAmmEvent(
                        base_mint=iaccounts['base_mint'],
                        quote_mint=iaccounts['quote_mint']
                    )
                    # TODO
                    self.debug_cnt['migrate_to_amm'] = self.debug_cnt.get('migrate_to_amm', 0) + 1
                    log.warning(f'unhandled migrate_to_amm event #{self.debug_cnt['migrate_to_amm']} :: https://solscan.io/tx/{tx_signature}')
                    continue
                elif idata.name == 'migrate_to_cpswap':
                    # handled with Raydium CPMM
                    # https://solscan.io/tx/12oaxGcDQew5hjQ3vEGEBgvwSL1ov5NSsoezxZ2NzjxvhWgsRWAKXwTQXzkDU3NqJNyo4ibHop7wM3cP6pQzwZz
                    cpmm_initialize_idata_, cpmm_initialize_iaccounts, _ = next(decoded_instructions_iter)
                    if cpmm_initialize_iaccounts['token_0_mint'] not in [str(WRAPPED_SOL_MINT), str(USD1)] and cpmm_initialize_iaccounts['token_1_mint'] not in [str(WRAPPED_SOL_MINT), str(USD1)]:
                        self.export_to_file(tx_signature)
                        log.error(f'cpmm init pair without SOL or USD1 :: https://solscan.io/tx/{tx_signature}')

                    e = RaydiumCPMMInitializeEvent(
                        amm_config=cpmm_initialize_iaccounts['amm_config'],
                        pool_state=cpmm_initialize_iaccounts['pool_state'],
                        token0_mint=cpmm_initialize_iaccounts['token_0_mint'],
                        token1_mint=cpmm_initialize_iaccounts['token_1_mint'],
                        lp_mint=cpmm_initialize_iaccounts['lp_mint'],
                        token0_vault=cpmm_initialize_iaccounts['token_0_vault'],
                        token1_vault=cpmm_initialize_iaccounts['token_1_vault'],
                        observation_state=cpmm_initialize_iaccounts['observation_state'],
                        init_amount0=cpmm_initialize_idata_.data['init_amount_0'],
                        init_amount1=cpmm_initialize_idata_.data['init_amount_1'],
                        open_time=cpmm_initialize_idata_.data['open_time']
                    )
            elif str(RAYDIUM_CPMM_PROGRAM) == program_id:
                if idata.name == 'swap_base_input':
                    input_token_mint_str = iaccounts.get('input_token_mint')
                    output_token_mint_str = iaccounts.get('output_token_mint')
                    is_buy = input_token_mint_str == str(WRAPPED_SOL_MINT)
                    mint_acc = output_token_mint_str if is_buy else input_token_mint_str
                    if mint_acc not in self.amm_account_filter:
                        continue
                    amount_in_val = idata.data.amount_in
                    actual_amount_out = 0 # Default
                    t1_idata, _, _ = next(decoded_instructions_iter) # First transfer: input token from user to vault
                    try:
                        t2_idata, _, _ = next(decoded_instructions_iter) # Second transfer: output token from vault to user
                    except:
                        log.info(f'## {idata.name} TOKEN2022? event not found :: https://solscan.io/tx/{tx_signature}')
                        self.export_to_file(tx_signature)
                        continue

                    actual_amount_out = t2_idata.data.amount
                    if t1_idata.data.amount != amount_in_val:
                        log.warning(
                            f"CPMM swap_base_input: Input amount mismatch. "
                            f"Instruction: {amount_in_val}, Transfer1: {t1_idata.data.amount}. TX: {tx_signature}"
                        )
                    owner_acc = iaccounts.get('payer')
                    e = RaydiumCPMMSwapEvent(
                        is_buy=is_buy,
                        amount_in=amount_in_val,
                        amount_out=actual_amount_out,
                        owner=owner_acc,
                        mint=mint_acc
                    )
                elif idata.name == 'swap_base_output':
                    input_token_mint_str = iaccounts.get('input_token_mint')
                    output_token_mint_str = iaccounts.get('output_token_mint')
                    is_buy = input_token_mint_str == str(WRAPPED_SOL_MINT)
                    mint_acc = output_token_mint_str if is_buy else input_token_mint_str
                    if mint_acc not in self.amm_account_filter:
                        continue
                    amount_out_val = idata.data.amount_out
                    actual_amount_in = 0 # Default
                    t1_idata, _, _ = next(decoded_instructions_iter) # First transfer: input token from user to vault
                    try:
                        t2_idata, _, _ = next(decoded_instructions_iter) # Second transfer: output token from vault to user
                    except:
                        log.info(f'## {idata.name} TOKEN2022? event not found :: https://solscan.io/tx/{tx_signature}')
                        self.export_to_file(tx_signature)
                        continue
                    actual_amount_in = t1_idata.data.amount
                    if t2_idata.data.amount != amount_out_val:
                        log.warning(
                            f"CPMM swap_base_output: Output amount mismatch. "
                            f"Instruction: {amount_out_val}, TX: {tx_signature}"
                        )
                    owner_acc = iaccounts.get('payer')
                    e = RaydiumCPMMSwapEvent(
                        is_buy=is_buy,
                        amount_in=actual_amount_in,
                        amount_out=amount_out_val,
                        owner=owner_acc,
                        mint=mint_acc
                    )
                elif idata.name in ['initialize', 
                                    'withdraw', 
                                    'deposit', 
                                    'collect_protocol_fee', 
                                    'collect_fund_fee',
                                    'update_amm_config']:
                    ## explicitly ignore these
                    # initialize
                    #   https://solscan.io/tx/LgrqZeHMt3x5jCjKGgcZ18VYoQSYQZTqwRLJEAdKfUi8H9pWdYyGv7UtfqixcFtR8ap2Z6p42DzbLjMfLQH2PMa
                    #   skip because we listen to layunchpad init RAYDIUM_LAUNCHPAD.migrate_to_cpswap (https://solscan.io/tx/12oaxGcDQew5hjQ3vEGEBgvwSL1ov5NSsoezxZ2NzjxvhWgsRWAKXwTQXzkDU3NqJNyo4ibHop7wM3cP6pQzwZz) 
                    #   cpmm init can be non-launchpad token
                    # withdraw - guess no need
                    #   https://solscan.io/tx/4tGbtPMAMrhhpTwipzSM675n8i6mZ95g7AYqBRs28MPwVxdr43B7kFgDepPSZAsdErc3mjo9Rb9RR5Tb55rLeZzA
                    # deposit
                    #   https://solscan.io/tx/5mVniVXwHXfPLEVw1TyRr1zyVZmtiFVSqPjAy3XVTNbJvPvSZ6yypEccLYjuTupDYMVwyEWqbbazvoo8REg4AJBe
                    # collect_protocol_fee
                    #   https://solscan.io/tx/5kb4SgqefRwHww6AdN9AAfUn6RDQsoo5CV6DVjYonij3qvZmdvwjjFFYPSeShWSPxdycCfXgr9vfLdWQYCBEkhe4
                    # collect_fund_fee
                    #   https://solscan.io/tx/4xcyerH7kxkj1PzNssA9hv6Sfi27A4RxFzGGSpsHdWjM54y38fUM993sxxSsa7TxpjuP6KtpLyAw7TqSSFjgX3V7
                    continue

            if e is None:
                self.export_to_file(tx_signature, idata)
            else:   
                # elif 'PumpFunCreate' == e._event_name:
                #     log.info(f'{e.symbol}')
                # elif 'RaydiumV4Swap' == e._event_name:
                #     color = '\033[92m' if e.is_buy else '\033[91m'
                #     log.info(f'{color}https://solscan.io/tx/{tx_signature}\033[0m')
                #     log.info(f'{e}')

                # push to event handler
                self.pumpfun_event_handler(e, program_id)

    def decode_instructions(self, instructions, account_addresses, tx_info):
        
        program_ids_to_decode = MSG_FILTER[account_addresses[instructions[0].program_id_index]]
        decoded_instructions = []

        def _decode(program_id, i):
            #hex_string = binascii.hexlify(i.data).decode()
            coder, idl = get_coder(program_id)
            ic = coder.instruction
            if program_id in [str(PUMP_PROGRAM), str(PUMP_AMM_PROGRAM), str(RAYDIUM_LAUNCHPAD), str(RAYDIUM_CPMM_PROGRAM)]:
                # frameworks like Anchor, the discriminator is a fixed-length (usually 8 bytes) prefix added to the instruction data 
                # this prefix uniquely identifies the specific function (or instruction) being invoked within the program
                try:
                    idata = ic.parse(i.data)
                except:
                    log.warning(f'unable to decode')
                    return None, None
                ifunc = idata.name
                idl_instruction = next((iins for iins in idl.instructions if iins.name == ifunc or snake(iins.name) == ifunc), None)
            else:
                # 1 byte discriminator
                discriminator = i.data[0]
                # function which is called
                ifunc = idl.instructions[discriminator].name
                try:
                    encoded_function_name = ic.sighashes[snake(ifunc)]
                except:
                    try:
                        encoded_function_name = ic.sighashes[ifunc]
                    except:
                        log.info(f'ERROR: giving up.. no function found in idl ({ifunc}, program_id={program_id}, \
                                tx=https://solscan.io/tx/{cached_b58encode(bytes(tx_info.signature))})')
                # instruction data
                idata = ic.parse(encoded_function_name + i.data[1:])
                idl_instruction = idl.instructions[discriminator]
            return idata, idl_instruction

        # shortcut for anchor Self CPI Log
        event_log_handled = False
        for i in instructions:
            if len(i.accounts) == 1 and ((str(PUMP_PROGRAM) == account_addresses[i.program_id_index] and str(PUMP_EVENT_AUTHORITY) == account_addresses[i.accounts[0]]) or \
                                         (str(PUMP_AMM_PROGRAM) == account_addresses[i.program_id_index] and str(PUMP_AMM_EVENT_AUTHORITY) == account_addresses[i.accounts[0]]) or \
                                         (str(RAYDIUM_LAUNCHPAD) == account_addresses[i.program_id_index] and str(RAYDIUM_LAUNCHPAD_EVENT_AUTHORITY) == account_addresses[i.accounts[0]])):
            
                coder, _ = get_coder(account_addresses[i.program_id_index])
                if i.data[8:16] in coder.events.discriminators:
                    try:
                        # NOTE: could be more like in https://solscan.io/tx/3J98pLbj4PERTGqbZYs4YDsPCQAXRG1izZmEyFf3qjUUKwjFUzCrrxYr1ByWWNGDuu1oyCpeqbAjWGBH86oBddKf
                        # TODO: whats in i.data[:8]??
                        e = coder.events.parse(i.data[8:])
                        additional_data = None
                        # Raydium Launchpad case need to extract the payer / user from original intruction cause its not in the event data
                        if str(RAYDIUM_LAUNCHPAD) == account_addresses[i.program_id_index]:
                            inst = instructions[0]
                            idata, idl_instruction = _decode(account_addresses[inst.program_id_index], inst)
                            additional_data = {a.name: account_addresses[inst.accounts[aidx]] for aidx, a in enumerate(idl_instruction.accounts)}
                        event_log_handled = True
                        self.pumpfun_event_handler(e, account_addresses[i.program_id_index], additional_data)
                    except Exception as e:
                        tx=cached_b58encode(bytes(tx_info.signature))
                        self.export_to_file(tx)
                        send_telegram_message(f'event parsing failed ({e}) :: tx={tx}')
                        log.warning(f'event parsing failed ({e}) :: tx={tx}')
                elif binascii.hexlify(i.data[8:16]).decode() == 'e445a52e51cb9a1dbde95db95c94ea94'[16:]:
                    # known unknown
                    # PumpFun call at create pool
                    # https://solscan.io/tx/2gwL4eCyFH9eEtGxFV7orp46QQKmY8JxRh4j59SCgUut3SSt3vrA5QGhJAzeATr2ZveDNxP5K6UZztkHJv8AsJPi
                    pass
                else:
                    tx=cached_b58encode(bytes(tx_info.signature))
                    self.export_to_file(tx)
                    log.warning(f'anchor event log expected :: tx={tx}')
        if event_log_handled:
            return None
        
        for i in instructions:
            program_id = account_addresses[i.program_id_index]
            if program_id not in program_ids_to_decode:
                continue
            
            idata, idl_instruction = _decode(program_id, i)
            if idl_instruction is None:
                tx=f'{base58.b58encode(bytes(tx_info.signature)).decode()}'
                self.export_to_file(tx)
                continue

            # instruction accounts
            idl_accounts = idl_instruction.accounts
            if len(idl_accounts) > len(i.accounts):
                # rm optional accounts?? TODO
                idl_accounts = [a for a in idl_instruction.accounts if not a.is_optional]
            if len(idl_accounts) != len(i.accounts):
                tx=f'{base58.b58encode(bytes(tx_info.signature)).decode()}'
                if len(idl_accounts) > len(i.accounts):
                    self.export_to_file(tx)
                    raise Exception(f"optional account hell tx={tx}")
                #elif str(PUMP_PROGRAM) != program_id:
                #    log.warning(f'account mismatch :: tx={tx}')
                #    self.export_to_file(tx)

            iaccounts = {idl_accounts[idx].name: account_addresses[aidx] for idx, aidx in enumerate(i.accounts) if idx < len(idl_accounts)}
            decoded_instructions.append((idata, iaccounts, program_id))

            if False: #'userSourceOwner' in iaccounts:
                from spl.token.constants import TOKEN_PROGRAM_ID, WRAPPED_SOL_MINT, ASSOCIATED_TOKEN_PROGRAM_ID
                from spl.token.instructions import get_associated_token_address
                from solders.pubkey import Pubkey

                #owner = Pubkey.from_string(iaccounts['userSourceOwner'])
                owner = Pubkey.from_string('Evmc4QgBE9yCujAsxQoFJsCakdg2VvvawkFo1VVGQjK7')
                ata  = get_associated_token_address(owner=owner, mint=Pubkey.from_string('So11111111111111111111111111111111111111112'))
                ata2 = get_associated_token_address(owner=owner, mint=Pubkey.from_string('6WG2zDjDHTAfwF1gvNdU7ieQbVUwo4Cz9P93HuEspump'))
                print(ata)
                print(ata2)
                Pubkey.create_with_seed(Pubkey.from_string('Evmc4QgBE9yCujAsxQoFJsCakdg2VvvawkFo1VVGQjK7'), 'ytKP16naR6j6SxgJupSsj7U5C8s5Rk4L', Pubkey.from_string('Evmc4QgBE9yCujAsxQoFJsCakdg2VvvawkFo1VVGQjK7'))
                
                stop = 1
        
        if not len(decoded_instructions):
            return None
        return decoded_instructions

async def start_with_profiling(duration: int = 30):
    """
    Wrapper to run subscriber.start() for a limited duration.
    """
    subscriber = GeyserSubscriber(provider="SolanaVibeStation")
    task = asyncio.create_task(subscriber.start())
    
    # Wait for the specified duration
    await asyncio.sleep(duration)
    
    # Cancel the task to stop the infinite loop
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    
    await subscriber.stop()
    log.info(f"Profiling completed after {duration} seconds.")

def profile_start(duration: int = 30):
    """
    Profile the start function for the given duration and save readable output to file.
    """
    profiler = cProfile.Profile()
    profiler.enable()
    asyncio.run(start_with_profiling(duration))
    profiler.disable()
    
    # Create filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'pumpfun_grpc_profile_{timestamp}.txt'
    
    # Save readable stats to text file
    with open(filename, 'w') as f:
        stats = pstats.Stats(profiler, stream=f).sort_stats('cumulative')
        stats.print_stats(50)
    
    print(f"Readable profile results saved to {filename}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run the Geyser subscriber.")
    parser.add_argument(
        '--profile',
        action='store_true',
        help='Enable profiling.'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=120,
        help='Duration in seconds for profiling (default: 120).'
    )
    args, _ = parser.parse_known_args()
    
    if args.profile:
        profile_start(args.duration)
    else:
        subscriber = GeyserSubscriber(provider="SolanaVibeStation")
        asyncio.run(subscriber.start())
