#!/usr/bin/python3

import os
from web3 import Web3
from web3 import exceptions as w3_exceptions
from web3.middleware import geth_poa_middleware
from eth_utils import remove_0x_prefix, to_int, to_checksum_address, to_hex
import numpy as np
import random
from threading import Thread
import requests
import multiprocessing as mp
from multiprocessing.connection import Listener
import threading
import time
import sys
import json
import logging
import datetime
import pandas as pd
from statistics import median
import telegram_send
import ctypes
from enum import IntEnum
from random import randint
import re
from solidity_parser import parser
from pprint import pprint
import statistics
from subprocess import check_output
sys.path.append('../utils')
from scraper import Scraper
from icecream import ic
from directWeb3 import DirectWeb3
from walletFactory import WalletFactory
from db_handler import DBHandler, Network
import subprocess
import traceback
import web3Utils as w3u
from eth_abi import encode_abi, decode_abi
from hexbytes import HexBytes


def network_str(network: Network):
    if network == Network.BSC:
        return 'BSC'
    elif network == Network.ETH:
        return 'ETH'
    elif network == Network.MATIC:
        return 'MATIC'
    elif network == Network.BSC_TESTNET:
        return 'BSC_TESTNET'
    elif network == Network.FANTOM:
        return 'FANTOM'
    elif network == Network.AVAX:
        return 'AVAX'
    return 'UNKNOWN'


def str_2_network(network):
    if network == 'BSC':
        return Network.BSC
    elif network == 'ETH':
        return Network.ETH
    elif network == 'MATIC':
        return Network.MATIC
    elif network == 'BSC_TESTNET':
        return Network.BSC_TESTNET
    elif network == 'FANTOM':
        return Network.FANTOM
    elif network == 'AVAX':
        return Network.AVAX
    else:
        assert False
    return 'UNKNOWN'


class NodeProvider(IntEnum):
    ANKR = 0,
    QUICKNODE = 1,      # do not use - 9$ / 300k req - https://www.quicknode.com/pricing
    CHAINSTACK = 2,     # 0$ / 3M req - https://chainstack.com/pricing/
    BINANCE_MAIN = 3,
    BINANCE = 4,
    ETH_MAIN = 5,
    BINANCE_LOCAL_IPC = 6,
    BINANCE_LOCAL = 7


class NodeConnectionType(IntEnum):
    http = 0,
    wss = 1


class FilterEntryType(IntEnum):
    PENDING = 0,
    NEW_BLOCK_HASH = 1,
    NEW_BLOCK_TRANSACTION = 2,
    NEW_BLOCK = 3,
    MAX_VAL = 4


class TransactionType(IntEnum):
    BUY = 0,
    SELL = 1,
    SEND = 2,
    PRESALE_CLAIM_TOKENS = 3,
    SPEC_HASH = 4,
    SWAP_TOKENS = 5,
    PINKSALE_CONTRIBUE = 6

def empty():
    time.sleep(0.1)
    return


class Web3BSC():
    def __init__(self, barebone_init=False, data_json=None):
        # IMPORTANT
        self._TESTNET_ = False
        self._SKIP_PENDINGS_ = True
        self._LPPAIR_SEARCH_ = False
        self._COPY_TRADING_ENABLED_ = False     # could be enabled in data.json / 'trading_params
        self._wait_for_events_to_claim = False
        if self._wait_for_events_to_claim:
            self._wait_for_events_to_claim_prerequisite = mp.Array(ctypes.c_bool, [False] * 2)

        self.ZERO_ADDR = '0x0000000000000000000000000000000000000000'
        self.curr_path = os.path.dirname(os.path.abspath(__file__)) + '/'

        if not data_json:
            data_json = 'data.json'
            if len(sys.argv) > 1:
                # data.json specified
                data_json = str(sys.argv[1])
            print(f'loading {data_json}')
        else:
            self.curr_path = ''

        # read sensitive data from file
        with open(self.curr_path + data_json) as json_file:
            self.data_json = json.load(json_file)

        # set config from file
        try:
            self._NETWORK_ = str_2_network(self.data_json['config']['network'])
        except:
            self._NETWORK_ = Network.BSC
        self._ARMED_ = self.data_json['config']['armed']
        self._DISABLE_TELEGRAM_ = not self.data_json['config']['enable_telegram']
        try:
            self._PRESALE_ = mp.Value(ctypes.c_bool, self.data_json['config']['presale'])
        except:
            self._PRESALE_ = mp.Value(ctypes.c_bool, False)
        try:
            self._PRESALE_CLAIM_ = mp.Value(ctypes.c_bool, self.data_json['config']['presale_claim'])
        except:
            self._PRESALE_CLAIM_ = mp.Value(ctypes.c_bool, False)
        try:
            self._START_EXTERNAL_CMD_ = self.data_json['config']['enable_external_cmd']
        except:
            self._START_EXTERNAL_CMD_ = False
        try:
            self.poll_blocknum_offset = self.data_json['config']['poll_blocknum_offset']
        except:
            self.poll_blocknum_offset = -10

        # log
        ic.configureOutput(prefix=self.log_prefix)
        ic.configureOutput(includeContext=True)
        ic.enable()

        logdate = datetime.datetime.now().strftime("%Y%m%d_%H%M%S.%f")
        if not os.path.exists('./log'):
            os.makedirs('./log')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s|%(levelname)s|%(message)s',                 # '%(asctime)s.%(msecs)03d|%(levelname)s|%(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.FileHandler(
                    "./log/web3bsc" + "_" + logdate + "_" + network_str(self._NETWORK_) + ".log", mode='w',
                    encoding=None, delay=False),
                logging.StreamHandler()
            ]
        )

        # load db
        self.node_provider = None
        self.node_provider_real = None
        if self._NETWORK_ == Network.BSC:
            if 0:
                self.node_provider = NodeProvider.BINANCE_MAIN
                self.node_provider_real = NodeProvider.BINANCE
                logging.info('node provider = BINANCE_MAIN')
            else:
                try:
                    ips = check_output(['hostname', '--all-ip-addresses']).decode('ascii').strip().split(' ')
                    if '<ips_ip>' in ips:
                        self.node_provider = NodeProvider.BINANCE_LOCAL_IPC
                        self.node_provider_real = NodeProvider.BINANCE_LOCAL_IPC
                        logging.info('node provider = BINANCE_LOCAL_IPC')
                    else:
                        self.node_provider = NodeProvider.BINANCE_LOCAL
                        self.node_provider_real = NodeProvider.BINANCE_LOCAL
                        logging.info('node provider = BINANCE_LOCAL')
                except:
                    self.node_provider = NodeProvider.BINANCE_MAIN
                    self.node_provider_real = NodeProvider.BINANCE
                    logging.info('node provider = BINANCE_MAIN - failed to get local ip')
            db_file = 'dividend_token_BSC.db'
        else:
            db_file = f'dividend_token_{network_str(self._NETWORK_)}.db'
        self.db_handler = DBHandler(db_file, self._NETWORK_)

        # gather dex info
        dex_info = self.db_handler.get_network_info(self._NETWORK_)  # todo could be more

        # modify addresses based on network
        if 'contracts' not in self.data_json:
            self.data_json['contracts'] = {}
        if 'PancakeSwap' not in self.data_json['contracts']:
            self.data_json['contracts']['PancakeSwap'] = {
                "load": True
            }
        if 'PancakeSwap_factory_v2' not in self.data_json['contracts']:
            self.data_json['contracts']['PancakeSwap_factory_v2'] = {
                "load": True
            }
        self.data_json['contracts']['PancakeSwap']['addr'] = dex_info['router_address']
        self.data_json['contracts']['PancakeSwap_factory_v2']['addr'] = dex_info['factory_address']

        # TODO load from uniswap / pancakeswap
        if 'addrs' not in self.data_json:
            self.data_json['addrs'] = {}
        self.data_json['addrs']['WBNB'] = dex_info['base_token_address']
        self.data_json['addrs']['BUSD'] = dex_info['usd_token_address']

        # rm not 'load' == True contracts
        if 'contract_to_listen' not in self.data_json['trading_params']:
            self.data_json['trading_params']['contract_to_listen'] = None

        for c in list(self.data_json['contracts']):
            if not c == self.data_json['trading_params']['contract_to_listen']:
                if not 'load' in self.data_json['contracts'][c] or \
                   not self.data_json['contracts'][c]['load']:
                        self.data_json['contracts'].pop(c, None)

        self.workers = []
        self.workers_lock = threading.Lock()
        self.workers_idx_offset = 0
        self.worker_result_queue = mp.Queue()  # any results from threads

        # create connection instances
        self.chain_id = int(self.db_handler.get_network_chain_id(self._NETWORK_))
        if self._NETWORK_ == Network.BSC:
            if self.node_provider == NodeProvider.BINANCE_LOCAL_IPC or self.node_provider == NodeProvider.BINANCE_LOCAL:
                self.w3_get_block = [self.create_w3_connection(node_provider=self.node_provider)]
            else:
                self.w3_get_block = [Web3(Web3.HTTPProvider('https://bsc-dataseed.binance.org')),
                                     Web3(Web3.HTTPProvider('https://bsc-dataseed1.defibit.io')),
                                     Web3(Web3.HTTPProvider('https://bsc-dataseed1.ninicoin.io')),
                                     Web3(Web3.HTTPProvider('https://bsc-dataseed3.binance.org')),
                                     Web3(Web3.HTTPProvider('https://bsc-dataseed3.defibit.io')),
                                     Web3(Web3.HTTPProvider('https://bsc-dataseed3.ninicoin.io'))]
                for w3 in self.w3_get_block:
                    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        else:
            self.w3_get_block = [self.create_w3_connection(network=self._NETWORK_)]

        self.w3 = self.create_w3_connection(node_provider=self.node_provider,
                                            conn_type=NodeConnectionType.http,
                                            network=self._NETWORK_)
        # wait for node synching
        while sync_status := self.w3.eth.syncing:
            logging.info(f'wait for sync.. {sync_status}')
            time.sleep(5)

        self.dw3 = DirectWeb3(dex_info, w3=self.w3_get_block[0])

        self.wf = WalletFactory(1)
        # for i in range(0,10):
        #     print(self.wf.get_address(i)['addr'])
        # exit()

        # get number of private addresses
        private_address_cnt = len(self.data_json['private_data']['private_addresses'])
        # number of accounts * 2 (buying, selling)
        trading_array_length = private_address_cnt * 2
        # create trading w3s
        self.w3_real = []
        for i in range(trading_array_length):
            self.w3_real.append(self.create_w3_connection(node_provider=self.node_provider_real,
                                                          conn_type=NodeConnectionType.http,
                                                          network=self._NETWORK_))

        self.scraper = Scraper()

        # fix contract addresses
        for c in self.data_json['contracts']:
            if 'owner_addr' in self.data_json['contracts'][c]:
                owner_addr = self.data_json['contracts'][c]['owner_addr']
                self.data_json['contracts'][c]['owner_addr'] = self.w3.toChecksumAddress(owner_addr)

            # toChecksumAddress
            addr = self.data_json['contracts'][c]['addr']
            self.data_json['contracts'][c]['addr'] = self.w3.toChecksumAddress(addr)

        # load contracts
        for contr in self.data_json['contracts']:
            # contract address
            addr = self.data_json['contracts'][contr]['addr']
            # downloaded abi from bscscan/etherscan
            explorer = self.db_handler.get_network_explorer(self._NETWORK_)
            bscscan_apikey = self.data_json['private_data'][explorer]['apikey']
            bscscan_abi_req = 'https://api.' \
                              + explorer.split('https://')[1] \
                              + '/api?module=contract&action=getabi&address=' + addr + '&apikey=' + bscscan_apikey
            bscscan_response = requests.get(bscscan_abi_req).json()
            abi_txt = None
            if bscscan_response['message'] == 'OK' \
               and not 'upgradeTo' in bscscan_response['result']:   # looks like BEP20UpgradeableProxy
                abi_txt = bscscan_response['result']
                logging.info(contr + ' ABI loaded from bscscan')
            else:
                # try loading from file
                if 'abi_file' in self.data_json['contracts'][contr]:
                    logging.info('loading ABI from file for contr = ' + contr)
                    abi_file = self.data_json['contracts'][contr]['abi_file']
                    abi_txt = open(abi_file, 'r').read().replace('\n', '')
                elif 'source code not verified' in bscscan_response['result']:
                    # load minimal contract abi
                    dirname = os.path.dirname(__file__)
                    abi_txt = open(dirname + '/ABIs/minimal_ABI', 'r').read().replace('\n', '')
                    logging.error('minimal ABI loaded for ' + contr)
                else:
                    # abi loading failed
                    logging.info('ABI loading failed for ' + contr)
                    logging.info('bscscan response: ' + bscscan_response['result'])
                    exit()

            if abi_txt:
                self.data_json['contracts'][contr]['contract'] = self.w3.eth.contract(
                    address=addr,
                    abi=abi_txt)

        # get token decimals and owner
        for c in self.data_json['contracts']:
            decimals = 0
            try:
                decimals = self.data_json['contracts'][c]['contract'].functions.decimals().call()
            except:
                pass
            self.data_json['contracts'][c]['decimals'] = decimals

            if 'owner_addr' in self.data_json['contracts'][c]:
                owner_addr = self.data_json['contracts'][c]['owner_addr']
            else:
                owner_addr = '0x0000000000000000000000000000000000000000'
            try:
                # try to get owner address with 'owner'
                owner_addr = self.data_json['contracts'][c]['contract'].functions.owner().call()
            except:
                try:
                    # try to get owner address with 'getOwner'
                    owner_addr = self.data_json['contracts'][c]['contract'].functions.getOwner().call()
                except:
                    pass
            if 'owner_addr' in self.data_json['contracts'][c]:
                if self.data_json['contracts'][c]['owner_addr'] != owner_addr:
                    print('owner addresses not match for', c)
                    owner_addr = self.data_json['contracts'][c]['owner_addr']
            self.data_json['contracts'][c]['owner_addr'] = owner_addr

            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                         + c + ' decimals=' + str(decimals) + ', owner=' + owner_addr)

        if barebone_init:
            print('web3bsc barebone init done')
            return

        # list of RPC endpoints
        # https://docs.binance.org/smart-chain/developer/rpc.html
        # The rate limit of BSC endpoint on Testnet and Mainnet is 10K/5min -> 33/s

        # verify connection
        if not self.w3.isConnected:
            logging.error('web3 not connected')
            exit()

        # pending transactions poll interval
        self.poll_interval = mp.Value('f', 0.5)

        # block filter
        if not self._SKIP_PENDINGS_:
            self.event_filter_pending = self.w3.eth.filter('pending')

        self.mp_exit_main_loop = mp.Value(ctypes.c_bool, False)
        self.gas_price_initialized = mp.Value(ctypes.c_bool, False)
        self.max_wait_for_mining_sec = 4

        # create worker threads
        if self._SKIP_PENDINGS_:
            self.workers_max = int(1000)
            self.number_of_pending_workers = 0
        else:
            self.workers_max = int(2500)
            self.number_of_pending_workers = int(self.workers_max * 0.8)
        # block processing worker = self.workers_max - self.number_of_pending_workers
        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                     + 'workers_max=' + str(self.workers_max) + '|'
                                     + 'number_of_pending_workers=' + str(self.number_of_pending_workers) + '|'
                                     + 'number_of_block_workers=' + str(self.workers_max-self.number_of_pending_workers))

        # queue with waiting tx hashes to be processed
        # worker thread can put back tx hash if failed, main thread will send to new worker
        self.worker_tx_queue = mp.Queue()

        for i in range(self.workers_max):
            w3 = self.create_w3_connection(node_provider=self.node_provider,
                                           conn_type=NodeConnectionType.http,
                                           network=self._NETWORK_)
            self.workers.append({'thread': None, 'w3': w3})

        # gas price/limit buffer
        # average gas price can be calculated (as a median for the last several blocks)
        # ~150 tx / block, 5 block
        self.gas_price_collection_max_size = 150 * 5
        self.gas_price_collection_idx = mp.Value('Q', 1)
        self.gas_price_collection = mp.Array('Q', [5000000000] * self.gas_price_collection_max_size)  # 5 gwei init
        self.gas_limit_collection_max_size = self.gas_price_collection_max_size
        self.gas_limit_collection_idx = mp.Value('Q', 1)
        self.gas_limit_collection = mp.Array('Q', [100000] * self.gas_limit_collection_max_size)  # 100k init
        
        # block related
        self.prev_block_timestamp = mp.Value('i', -1)
        self.prev_block_number = mp.Value('i', -1)
        self.mp_manager = mp.Manager()
        self.block_list_lock = mp.Lock()
        self.block_list = self.mp_manager.list()

        # statistics
        self.event_cnt = mp.Array('i', [0] * FilterEntryType.MAX_VAL)

        # update account balance and nonce information
        for account_idx, _ in enumerate(self.data_json['private_data']['private_addresses']):
            self.data_json['private_data']['private_addresses'][account_idx]['balance'] = mp.Value('Q', 0)
            self.data_json['private_data']['private_addresses'][account_idx]['nonce'] = mp.Value('Q', 0)
        self.update_account_info()

        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                     + 'Trading with ' + str(private_address_cnt) + ' addresses')

        # trading details
        self.trading_details = self.data_json['trading_params']
        self.trading_details['is_running'] = mp.Array(ctypes.c_bool, [False] * trading_array_length)
        self.trading_details['kill_trading'] = mp.Array(ctypes.c_bool, [False] * trading_array_length)
        # Note: time.time() should be stored in ctypes.c_double!!
        self.trading_details['last_trade_ts'] = mp.Array(ctypes.c_double, [0.0] * trading_array_length)
        self.trading_details['successful_trade_cnt'] = mp.Array('i', [0] * trading_array_length)
        self.trading_details['successful_swap_trigger'] = mp.Array(ctypes.c_bool, [False] * trading_array_length)
        if 'max_number_of_buys' not in self.trading_details:
            self.trading_details['max_number_of_buys'] = 1
        if 'max_number_of_sells' not in self.trading_details:
            self.trading_details['max_number_of_sells'] = 1

        # copy trading
        if 'copy_trading' in self.trading_details:
            if 'enabled' in self.trading_details['copy_trading']:
                if self.trading_details['copy_trading']['enabled']:
                    self._COPY_TRADING_ENABLED_ = True

        # initial transaction lock time
        transaction_lock_time = 2
        if 'transaction_lock_time' in self.trading_details:
            transaction_lock_time = int(self.trading_details['transaction_lock_time'])
        # data types https://docs.python.org/3/library/array.html#module-array
        self.trading_details['transaction_lock_time'] = mp.Value('Q', transaction_lock_time)
        # initial max tokens to buy
        max_tokens_to_buy = int(-1)
        if 'max_tokens_to_buy' in self.trading_details:
            max_tokens_to_buy = int(self.trading_details['max_tokens_to_buy'])
        self.trading_details['max_tokens_to_buy'] = mp.Value('f', max_tokens_to_buy)
        max_bnb_to_buy = float(-1)
        if 'max_bnb_to_buy' in self.trading_details:
            max_bnb_to_buy = float(self.trading_details['max_bnb_to_buy'])
        self.trading_details['max_bnb_to_buy'] = mp.Value('f', max_bnb_to_buy)

        # initial max tokens to sell
        max_tokens_to_sell = int(1e12)
        if 'max_tokens_to_sell' in self.trading_details:
            max_tokens_to_sell = int(self.trading_details['max_tokens_to_sell'])
        self.trading_details['max_tokens_to_sell'] = mp.Value('f', max_tokens_to_sell)

        self.block_dt_collection_max_size = 100
        self.block_dt_collection_idx = mp.Value('Q', 1)
        self.block_dt_collection = mp.Array('Q', [3] * self.block_dt_collection_max_size)  # 3sec init

        self.data_json['contracts']['dxsale'] = {
            'contract': None,
            'addr': '0x0',
            'decimals': 0
        }
        self.data_json['contracts']['pinksale'] = {
            'contract': None,
            'addr': '0x0',
            'decimals': 0
        }

        self.is_pinksale_presale = mp.Value(ctypes.c_bool, False)
        if self._PRESALE_.value:
            if not 'max_bnb_to_buy' in self.trading_details:
                print('ERROR:: Presale enabled but no presale_address, presale_start_utc or max_bnb_to_buy field set in trading_params')
                exit()
            elif not 'pinksale_address' in self.trading_details and \
                 not 'presale_address' in self.trading_details:
                self.trading_details['presale_address'] = mp.Array('u', self.ZERO_ADDR)
                self.trading_details['presale_start_utc'] = mp.Value('i', -1)
            elif not 'presale_start_utc' in self.trading_details:
                self.trading_details['presale_start_utc'] = mp.Value('i', -1)

                if 'pinksale_address' in self.trading_details:
                    # https://www.pinksale.finance/
                    self.is_pinksale_presale.value = True
                    self.trading_details['presale_address'] = mp.Array('u', self.trading_details['pinksale_address'])
                    self.decode_pinksale_details(self.trading_details['pinksale_address'][0:])
                else:
                    # https://dxsale.network/
                    # initial values
                    self.trading_details['presale_address'] = mp.Array('u', self.trading_details['presale_address'])
                    # load utc from dxapp
                    self.decode_dxsale_details(self.trading_details['presale_address'][0:], False)
            else:
                if 'pinksale_address' in self.trading_details:
                    self.is_pinksale_presale.value = True
                    self.trading_details['presale_address'] = mp.Array('u', self.trading_details['pinksale_address'])
                else:
                    self.trading_details['presale_address'] = mp.Array('u', self.trading_details['presale_address'])
                self.trading_details['presale_start_utc'] = mp.Value('i', self.trading_details['presale_start_utc'])

                self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                             + 'presale_start_utc=' + str(self.trading_details['presale_start_utc'].value) + '|'
                                             + 'presale_address=' + self.trading_details['presale_address'][0:] + '|'
                                             + 'max_bnb_to_buy=' + str(self.trading_details['max_bnb_to_buy'].value))

        self.prev_claim_timestamp = mp.Value('i', -1)
        if self._PRESALE_CLAIM_.value:
            if not 'pinksale_address' in self.trading_details and \
               not 'presale_address' in self.trading_details:
                print('ERROR:: _PRESALE_CLAIM_ enabled but no presale_address/presale_address field set in trading_params')
                exit()
            else:
                if 'pinksale_address' in self.trading_details:
                    # https://www.pinksale.finance/
                    self.is_pinksale_presale.value = True
                    self.trading_details['presale_address'] = mp.Array('u', self.trading_details['pinksale_address'])
                    self.decode_pinksale_details(self.trading_details['pinksale_address'][0:])
                else:
                    self.trading_details['presale_address'] = mp.Array('u', self.trading_details['presale_address'])
                    self.decode_dxsale_details(self.trading_details['presale_address'][0:], False)
                self.trading_details['presale_start_utc'] = mp.Value('i', -1)

        # start external command listener
        if self._START_EXTERNAL_CMD_:
            th = mp.Process(target=self.listen_to_external_commands)
            th.start()

        print('STARTING...')

        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                     + 'type=STARTING')

        self.worker_result_queue.put('TELEGRAM' + '```'+ datetime.datetime.now().strftime("%H:%M:%S.%f") + '```\n'
                                     + '*STARTING...*\n')

    def transfer_bnb(self, value, from_widx, to_widx):
        account_from = self.wf.get_address(from_widx)
        account_to = self.wf.get_address(to_widx)
        print(f'sending {value} bnb from {account_from["addr"]} to {account_to["addr"]}')
        nonce = self.w3.eth.getTransactionCount(account_from['addr'])
        _txn = {
            'to': account_to['addr'],
            'value': value,
            'gas': 21000,
            'gasPrice': self.w3.toWei(5, 'Gwei'),
            'nonce': self.w3.toHex(nonce),
            'chainId': self.chain_id
        }
        signed_txn = self.w3_real[0].eth.account.sign_transaction(_txn, private_key=account_from['private_key'])
        if self._ARMED_:
            tx_token = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            tx_hash = self.w3.toHex(tx_token)
            tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if not tx_receipt or tx_receipt['status'] == 0:
                print(f'transaction {tx_hash} failed, exiting...')
                return
            else:
                print(f'\tsuccessful transaction {tx_hash}')
        else:
            print('not armed, transfer skipped')
            return

    def get_upgradeable_proxy_implementation(self,
                                             addr,
                                             _IMPLEMENTATION_SLOT = '0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'):
        impl_contract = self.w3.toHex(
            self.w3.eth.get_storage_at(self.w3.toChecksumAddress(addr), _IMPLEMENTATION_SLOT))
        print(impl_contract)

    def log_prefix(self):
        return datetime.datetime.now().strftime("%H%M%S.%f ")

    def load_pancake_pair_contract(self, addr, name, addr2=None):
        if not addr2:
            addr2 = self.data_json['addrs']['WBNB']

        addr = self.w3.toChecksumAddress(addr)
        addr2 = self.w3.toChecksumAddress(addr2)

        # check already loaded
        for c in self.data_json['contracts']:
            if 'PancakePair' in c:
                tokens = self.data_json['contracts'][c]['tokens']
                if addr in tokens and addr2 in tokens:
                    return self.data_json['contracts'][c]['contract']

        # get pair address from pancake factory
        pc_factory = self.data_json['contracts']['PancakeSwap_factory_v2']['contract']
        # https://ethereum.stackexchange.com/questions/101630/web3-get-token-address-from-pair-address
        # TODO: change to get_lppair_address: check, not always valid
        # TODO: solution: token0 is guaranteed to be strictly less than token1 by sort order.
        lp_pair = pc_factory.functions.getPair(addr, addr2).call()
        contract_name = 'PancakePair_' + name
        abi_txt = open('./ABIs/PancakePair_ABI', 'r').read().replace('\n', '')
        self.data_json['contracts'][contract_name] = {
            'contract': self.w3.eth.contract(address=lp_pair, abi=abi_txt),
            'tokens': [addr, addr2]
        }
        return self.data_json['contracts'][contract_name]['contract']

    def create_w3_connection(self, node_provider=None, conn_type=None, network=None):
        if node_provider is None and network is not None:
            rpc = self.db_handler.get_network_rpc(network)
            w3 = Web3(Web3.HTTPProvider(rpc))
        elif NodeProvider.ANKR == node_provider:
            s = requests.Session()
            s.auth = (self.data_json['nodes']['ankr']['user'], self.data_json['nodes']['ankr']['pw'])
            w3 = Web3(Web3.HTTPProvider(self.data_json['nodes']['ankr']['http'], session=s))
        elif NodeProvider.QUICKNODE == node_provider:
            if NodeConnectionType.http == conn_type:
                w3 = Web3(Web3.HTTPProvider(self.data_json['nodes']['quicknode']['http']))
            else:
                w3 = Web3(Web3.WebsocketProvider(self.data_json['nodes']['quicknode']['wss']))
        elif NodeProvider.CHAINSTACK == node_provider:
            if NodeConnectionType.http == conn_type:
                w3 = Web3(Web3.HTTPProvider('https://%s:%s@%s' % (self.data_json['nodes']['chainstack']['user'],
                                                                  self.data_json['nodes']['chainstack']['pw'],
                                                                  self.data_json['nodes']['chainstack']['http'])))
            else:
                w3 = Web3(Web3.WebsocketProvider('wss://%s:%s@%s' % (self.data_json['nodes']['chainstack']['user'],
                                                                     self.data_json['nodes']['chainstack']['pw'],
                                                                     self.data_json['nodes']['chainstack']['wss'])))
        # else:
        #     w3 = Web3(Web3.HTTPProvider('https://bsc-dataseed1.binance.org:443'))
        elif NodeProvider.BINANCE_MAIN == node_provider:
            # Mainnet is 10K/5min == 33.3 / sec
            # https://docs.binance.org/smart-chain/developer/rpc.html#rate-limit
            key = 'bsc_main'
            w3 = Web3(Web3.HTTPProvider(self.data_json['nodes'][key]['http']))
        elif NodeProvider.BINANCE_LOCAL_IPC == node_provider:
            w3 = Web3(Web3.IPCProvider('/mnt/data/crypto/bsc_mainnet_node/geth.ipc'))
        elif NodeProvider.BINANCE_LOCAL == node_provider:
            w3 = Web3(Web3.HTTPProvider('http://<ip>:8545'))
        else:  # BINANCE
            key = 'bsc'
            bsc_rpc_len = len(self.data_json['nodes'][key]['http'])
            w3 = Web3(Web3.HTTPProvider(self.data_json['nodes'][key]['http'][len(self.workers) % bsc_rpc_len]))

        w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        return w3

    def listen_to_external_commands(self):
        while not self.mp_exit_main_loop.value:
            address = ('localhost', 6006)  # family is deduced to be 'AF_INET'
            listener = Listener(address, authkey=b'web3sbc control')
            conn = listener.accept()
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                         + 'listener connection accepted')

            try:
                while not self.mp_exit_main_loop.value:
                    msg = conn.recv()
                    self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                                 + 'external command received: "' + msg + '"')
                    if msg == 'exit':
                        self.mp_exit_main_loop.value = True
                        conn.close()
                        break
                    elif msg == 'isarmed':
                        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                                     + 'self._ARMED_ = ' + str(self._ARMED_))
                    elif msg == 'echo':
                        print('echo')
                        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                                     + 'ECHO..')
                    elif msg == 'telegram_test':
                        self.worker_result_queue.put('TELEGRAM' + '```' + datetime.datetime.now().strftime("%H:%M:%S.%f") + '```\n'
                                                     + 'telegram test message')
                    elif 'kill' in msg:
                        kill_all = (len(msg.split(' ')) == 1)
                        is_buying_list = [False]
                        if kill_all:
                            is_buying_list = [True, False]
                            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                                         + 'kill all transaction')
                        elif 'buy' in msg:
                            is_buying_list = [True]
                            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                                         + 'kill BUY transaction')
                        else:
                            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                                         + 'kill SELL transaction')
                        for is_buying in is_buying_list:
                            for account_idx, _ in enumerate(self.data_json['private_data']['private_addresses']):
                                idx = self.get_trading_details_idx(is_buying, account_idx)
                                self.trading_details['kill_trading'][idx] = True

                    elif 'clear' in msg:
                        # clear trading flags and results
                        clear_all = (len(msg.split(' ')) == 1)
                        is_buying_list = [False]
                        if clear_all:
                            is_buying_list = [True, False]
                            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                                         + 'clearing all transaction flag')
                        elif 'buy' in msg:
                            is_buying_list = [True]
                            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                                         + 'clearing BUY transaction flag')
                        else:
                            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                                         + 'clearing SELL transaction flag')

                        for is_buying in is_buying_list:
                            for account_idx, _ in enumerate(self.data_json['private_data']['private_addresses']):
                                idx = self.get_trading_details_idx(is_buying, account_idx)
                                self.trading_details['kill_trading'][idx] = False
                                self.trading_details['last_trade_ts'][idx] = 0.0
                                self.trading_details['successful_trade_cnt'][idx] = 0
                    elif 'buythis' in msg:
                        contract = 0x0
                        if len(msg.split(' ')) > 1:
                            contract = msg.split(' ')[1]

                        th = mp.Process(target=self._trade_some_token_, args=(contract,
                                                                              TransactionType.BUY,
                                                                              0,
                                                                              None,
                                                                              0,
                                                                              False,
                                                                              False,
                                                                              None,
                                                                              4000000,  # gas_limit
                                                                              self.w3.toWei(15, 'Gwei'),
                                                                              ))
                        th.start()

                        # th = mp.Process(target=self.process_trading, args=(contract, True, 0,))
                        # th.start()

                        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                                     + 'buying ' + contract)
                    elif 'locktime' in msg:
                        try:
                            new_lock_time = int(msg.split(' ')[1])
                            print('set transaction lock time')
                            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                                         + 'previous transaction_lock_time = ' + str(self.trading_details['transaction_lock_time'].value))
                            self.trading_details['transaction_lock_time'].value = new_lock_time
                            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                                         + 'transaction_lock_time set to ' + str(self.trading_details['transaction_lock_time'].value))
                        except:
                            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                                         + 'external cmd, locktime exception')
                    elif ('buy' in msg) or ('sell' in msg):
                        is_buying = ('buy' in msg)
                        specific_number = -1
                        if len(msg.split(' ')) > 1:
                            specific_number = int(msg.split(' ')[1])

                        print('external command, is_buying =', is_buying)
                        trigger_contract_name = self.trading_details['contract_to_listen']
                        for account_idx, _ in enumerate(self.data_json['private_data']['private_addresses']):
                            idx = self.get_trading_details_idx(is_buying, account_idx)
                            if self.trading_details['is_running'][idx]:
                                # skip if running
                                continue
                            if specific_number > 0:
                                trade_cnt_limit = self.trading_details['max_number_of_buys'] if is_buying else self.trading_details['max_number_of_sells']
                                self.trading_details['kill_trading'][idx] = False
                                self.trading_details['last_trade_ts'][idx] = 0.0
                                self.trading_details['successful_trade_cnt'][idx] = trade_cnt_limit - specific_number

                            # start trading process
                            th = mp.Process(target=self.process_trading, args=(trigger_contract_name, is_buying, account_idx,))
                            th.start()
                    elif 'isblacklisted' in msg:
                        trigger_contract_name = self.trading_details['contract_to_listen']
                        if len(msg.split(' ')) > 1:
                            # which token
                            trigger_contract_name = msg.split(' ')[1]
                        if trigger_contract_name in self.data_json['contracts']:
                            for account_idx, _ in enumerate(self.data_json['private_data']['private_addresses']):
                                addr_struct = self.data_json['private_data']['private_addresses'][account_idx]
                                contract = self.data_json['contracts'][trigger_contract_name]['contract']
                                is_blacklisted = contract.functions.isBlacklisted(addr_struct['addr']).call()
                                self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                                             + ' ___ '
                                                             + addr_struct['name']
                                                             + ' isBlacklisted = '
                                                             + str(is_blacklisted))
                        pass
                    elif 'update' in msg:
                        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                                     + 'call updating account info')
                        self.update_account_info()
                    elif 'presale' in msg:
                        presale_address = self.trading_details['presale_address'][0:]
                        th = mp.Process(target=self._trade_some_token_, args=(presale_address, TransactionType.SEND, 0,))
                        th.start()
            except:
                pass
            listener.close()

    def get_trading_details_idx(self, is_buying, account_idx):
        return int(account_idx * 2 + int(is_buying == True))

    def add_noise(self, value, min_percentage: int = 95, max_percentage: int = 105):
        rnd_percentage = randint(min_percentage, max_percentage)
        return int(value * (rnd_percentage / 100))

    def process_trading(self, contract_name, is_buying, account_idx):
        # check previous transactions
        # take care of minimum transaction interval

        # get trading info array index
        idx = self.get_trading_details_idx(is_buying, account_idx)
        # return if we are already donw
        trade_cnt_limit = self.trading_details['max_number_of_buys'] if is_buying else self.trading_details['max_number_of_sells']
        if self.trading_details['successful_trade_cnt'][idx] >= trade_cnt_limit:
            return
        # already running?
        if self.trading_details['is_running'][idx]:
            # this is valid because pending and mined blocks are also processed
            # i.e. all transaction processed twice
            return
        self.trading_details['is_running'][idx] = True

        # opposite action running?
        not_is_buying_idx = self.get_trading_details_idx((not is_buying), account_idx)
        if self.trading_details['is_running'][not_is_buying_idx]:
            # stop that
            self.trading_details['kill_trading'][not_is_buying_idx] = True
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                         + '|opposite ongoing trading?! is_buying == ' + str(is_buying) + ', send kill_trading')

        # trading threads that needs to be joined at exit
        trading_threads = []
        while 1:
            last_trade_ts = float(self.trading_details['last_trade_ts'][idx])
            safety_delay = 1
            transaction_lock_time = float(self.trading_details['transaction_lock_time'].value + safety_delay)

            # lock time expired?
            curr_ts = time.time()
            if last_trade_ts + transaction_lock_time <= curr_ts:
                # BUY/SELL SOME TOKEN
                # start trading thread

                tx_type = TransactionType.BUY if is_buying else TransactionType.SELL
                th = mp.Process(target=self._trade_some_token_, args=(contract_name,
                                                                      tx_type,
                                                                      account_idx,
                                                                      None,
                                                                      0,
                                                                      False,
                                                                      False,
                                                                      None,
                                                                      4000000,  # gas_limit
                                                                      self.w3.toWei(15, 'Gwei'),
                                                                      ))
                th.start()
                break
                trading_threads.append(th)

            # necessary trading done?
            trade_cnt_limit = self.trading_details['max_number_of_buys'] if is_buying else self.trading_details['max_number_of_sells']
            if self.trading_details['successful_trade_cnt'][idx] >= trade_cnt_limit:
                # we are done. exiting..
                self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                             + '|successful_trade_cnt reached '
                                             + self.data_json['private_data']['private_addresses'][account_idx]['name']
                                             + ' account '
                                             + ('buying' if is_buying else 'selling')
                                             + ' thread, exiting...')
                break

            # order to stop?
            if self.trading_details['kill_trading'][idx]:
                self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                             + '|killing '
                                             + self.data_json['private_data']['private_addresses'][account_idx]['name']
                                             + ' account '
                                             + ('buying' if is_buying else 'selling')
                                             + ' thread')
                break

            time.sleep(0.05)

        # clear running flag
        self.trading_details['is_running'][idx] = False

        # wait trading threads to finish
        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                     + '|joining to trading threads')
        for idx, th in enumerate(trading_threads):
            th.join()

        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                     + '|exiting '
                                     + self.data_json['private_data']['private_addresses'][account_idx]['name']
                                     + ' account '
                                     + ('buying' if is_buying else 'selling')
                                     + ' thread')

    # decode called function with pancakgeswap ABI
    # https://bscscan.com/address/0x10ed43c718714eb63d5aa57b78b54704e256024e#code
    def pancakeswap_decode_input_field(self, transaction):
        tx = transaction['hash'].hex()
        start_buying_if_transaction_success = False

        # ABI needed to decode input
        try:
            decoded_input = self.data_json['contracts']['PancakeSwap']['contract'].decode_function_input(transaction.input)
        except:
            # self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + ' ERROR|'
            #                              + 'decode_function_input failed|' + tx)
            return
        decoded_input_function_name = decoded_input[0].function_identifier
        decoded_input_arguments = decoded_input[1]

        # decoded function
        trigger_contract_name = self.trading_details['contract_to_listen']
        if trigger_contract_name in self.data_json['contracts'] and 'trigger_func_to_buy' in self.data_json['contracts'][trigger_contract_name]:
            # trigger_func_to_buy set
            # if self.data_json['contracts'][trigger_contract_name]['trigger_func_to_buy'] == decoded_input_function_name \
            #         and 'addLiquidityETH' == decoded_input_function_name:
            #     # is LP added for trigger contract
            #     if decoded_input_arguments['token'] == self.data_json['contracts'][trigger_contract_name]['addr']:
            #         start_buying_if_transaction_success = True
            if 'swap' in decoded_input_function_name:
                # get path address (e.g. [WBNB, <token>]
                path_addrs = decoded_input_arguments['path']
                # if swap from anything to trigger contract address
                try:
                    if ((self.w3.toChecksumAddress(path_addrs[1]) == self.data_json['contracts'][trigger_contract_name]['addr']) or
                        (self.w3.toChecksumAddress(path_addrs[0]) == self.data_json['contracts'][trigger_contract_name]['addr'])):
                        if 0:
                            swap_to = self.w3.toChecksumAddress(decoded_input_arguments['to'])
                            filtered_to = self.w3.toChecksumAddress('0x0')
                            if filtered_to != swap_to:
                                start_buying_if_transaction_success = True
                            else:
                                self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|skip swap trigger for address 0x0' + tx)
                        else:
                            start_buying_if_transaction_success = True
                except:
                    self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|swap trigger failed ' + tx)

        if self._COPY_TRADING_ENABLED_:
            if transaction['from'] == self.w3.toChecksumAddress(self.trading_details['copy_trading']['address']):
                if self.trading_details['copy_trading']['trigger_function'] in decoded_input_function_name:
                    if len(decoded_input_arguments['path']) == 3:
                        # swap from USD -> BNB -> !COIN!
                        if decoded_input_arguments['path'][0] == self.data_json['addrs']['BUSD'] and \
                           decoded_input_arguments['path'][1] == self.data_json['addrs']['WBNB']:
                            # get coin address to buy
                            self.trading_details['contract_to_listen'] = self.w3.toChecksumAddress(decoded_input_arguments['path'][2])
                            # all good
                            start_buying_if_transaction_success = True

        if start_buying_if_transaction_success:
            # get tx receipt in separate thread
            with self.workers_lock:
                worker_idx = self.get_free_worker_idx(FilterEntryType.NEW_BLOCK_TRANSACTION)
                if worker_idx < 0:
                    logging.error('no free worker for start_buying_if_transaction_success|' + str(tx))
                else:
                    th = mp.Process(target=self.start_buying_if_transaction_success,
                                    args=(self.workers[worker_idx]['w3'], tx, transaction,))
                    # start thread
                    th.start()
                    # assign into self list
                    self.workers[worker_idx]['thread'] = th

    def start_buying_if_transaction_success(self, w3, tx, transaction):
        transaction_receipt = self.get_transaction_receipt(w3, tx)
        if transaction_receipt and transaction_receipt['status'] == 1:
            # successful transaction
            for account_idx, _ in enumerate(self.data_json['private_data']['private_addresses']):
                # check that trading is necessary
                idx = self.get_trading_details_idx(True, account_idx)
                if not self.trading_details['successful_swap_trigger'][idx]:
                    self.trading_details['successful_swap_trigger'][idx] = True
                    trigger_contract_name = self.trading_details['contract_to_listen']
                    th = mp.Process(target=self.process_trading, args=(trigger_contract_name, True, account_idx,))
                    th.start()

                    # write to result queue
                    self.worker_result_queue.put('LOG'
                                                 + 'trading triggered with this|'
                                                 + 'sym=' + trigger_contract_name + '|'
                                                 + 'block=' + str(transaction.blockNumber) + '|'
                                                 + 'idx=' + str(transaction.transactionIndex) + '|'
                                                 + transaction['hash'].hex())

    def bnb_2_usd(self, w3, bnb_ether):
        # TODO new pancake pair contracts
        return -1
        ctr = self.data_json['contracts']['PancakePair_BNB_BUSD']['contract']
        bnb_busd = ctr.functions.getReserves().call()
        bnb_2_usd_mulfactor = bnb_busd[1] / bnb_busd[0]
        return bnb_ether * bnb_2_usd_mulfactor

    def update_account_info(self):
        for account_idx, _ in enumerate(self.data_json['private_data']['private_addresses']):
            sender_address = self.data_json['private_data']['private_addresses'][account_idx]['addr']
            self.data_json['private_data']['private_addresses'][account_idx]['balance'].value = self.w3.eth.get_balance(sender_address)
            self.data_json['private_data']['private_addresses'][account_idx]['nonce'].value = self.w3.eth.getTransactionCount(sender_address)

            # n0 = self.w3_real[self.get_trading_details_idx(False, account_idx)].eth.getTransactionCount(sender_address)
            # n1 = self.w3_real[self.get_trading_details_idx(True, account_idx)].eth.getTransactionCount(sender_address)

            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|updated private address info'
                                         + '\n\r\t' + str(sender_address) + '\n\r'
                                         + '\t\tbalance=' + str(float(self.w3.fromWei(self.data_json['private_data']['private_addresses'][account_idx]['balance'].value, 'ether'))) + ' BNB\n\r'
                                         + '\t\tnonce=' + str(self.data_json['private_data']['private_addresses'][account_idx]['nonce'].value))

    def decode_pinksale_details(self, pinksale_addr):
        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                     + 'decode_pinksale_details(' + pinksale_addr + ') called')
        try:
            abi_txt = open('./ABIs/pinksale_ABI', 'r').read().replace('\n', '')
            pinksale_contract = self.w3.eth.contract(address=pinksale_addr, abi=abi_txt)

            self.data_json['contracts']['pinksale']['addr'] = pinksale_addr
            self.data_json['contracts']['pinksale']['contract'] = pinksale_contract

            # when the presale starts
            presaleStartTime = pinksale_contract.functions.startTime().call()
            # when the presale ends
            presaleEndTime = pinksale_contract.functions.endTime().call()
            # min bnb amount
            minContribution = float(self.w3.fromWei(pinksale_contract.functions.minContribution().call(), 'ether'))
            # max bnb amount
            maxContribution = float(self.w3.fromWei(pinksale_contract.functions.maxContribution().call(), 'ether'))
            # token address
            token_addr = pinksale_contract.functions.token().call()

            # print dxsale details
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                         + 'PinkSale details for ' + str(pinksale_addr) + '\n\t\t'
                                         + 'presaleEndTime = ' + str(presaleEndTime) + '\n\t\t'
                                         + 'presaleStartTime = ' + str(presaleStartTime) + '\n\t\t'
                                         + 'token_addr = ' + str(token_addr) + '\n\t\t'
                                         + 'minContribution = ' + str(minContribution) + '\n\t\t'
                                         + 'maxContribution = ' + str(maxContribution))

            # set presale info
            self.trading_details['presale_start_utc'].value = presaleStartTime
            self.trading_details['presale_address'][0:] = pinksale_addr
            if minContribution > self.trading_details['max_bnb_to_buy'].value:
                self.trading_details['max_bnb_to_buy'].value = minContribution

            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                         + 'presale_start_utc=' + str(self.trading_details['presale_start_utc'].value) + '|'
                                         + 'presale_address=' + pinksale_addr + '|'
                                         + 'max_bnb_to_buy=' + str(self.trading_details['max_bnb_to_buy'].value))
        except:
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                         + 'pinksale contract call exception')

    def decode_dxsale_details(self, dxsale_addr, check_addr = True):

        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                     + 'decode_dxsale_details(' + dxsale_addr + ') called')
        try:
            abi_txt = open('./ABIs/DxSale_presale_ABI', 'r').read().replace('\n', '')
            dxsale_contract = self.w3.eth.contract(address=dxsale_addr, abi=abi_txt)

            # fill data json contracts fields
            self.data_json['contracts']['dxsale']['addr'] = dxsale_addr
            self.data_json['contracts']['dxsale']['contract'] = dxsale_contract

            # when the presale ends (== closingTime)
            presaleEndTime = dxsale_contract.functions.presaleEndTime().call()
            # when the presale starts (== openingTime)
            presaleStartTime = dxsale_contract.functions.presaleStartTime().call()
            # token contract creator
            wallet = dxsale_contract.functions.wallet().call()
            # token address
            token_addr = dxsale_contract.functions.token().call()
            # min bnb amount
            minEthContribution = float(self.w3.fromWei(dxsale_contract.functions.minEthContribution().call(), 'ether'))
            # max bnb amount
            maxEthContribution = float(self.w3.fromWei(dxsale_contract.functions.maxEthContribution().call(), 'ether'))
            # claim after finalized
            isFinalized = dxsale_contract.functions.isFinalized().call()

            # print dxsale details
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                         + 'DxSale details for ' + str(dxsale_addr) + '\n\t\t'
                                         + 'presaleEndTime = ' + str(presaleEndTime) + '\n\t\t'
                                         + 'presaleStartTime = ' + str(presaleStartTime) + '\n\t\t'
                                         + 'token_addr = ' + str(token_addr) + '\n\t\t'
                                         + 'wallet (token owner) = ' + str(wallet) + '\n\t\t'
                                         + 'minEthContribution = ' + str(minEthContribution) + '\n\t\t'
                                         + 'maxEthContribution = ' + str(maxEthContribution) + '\n\t\t'
                                         + 'isFinalized = ' + str(isFinalized))

            if check_addr:
                trigger_contract_name = self.trading_details['contract_to_listen']
                # if wallet != self.data_json['contracts'][trigger_contract_name]['owner_addr']:
                #     self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                #                                  + 'owner_addr != wallet addr (' + wallet + ')')
                #     raise SystemExit

                if trigger_contract_name in self.data_json['contracts'] and token_addr != self.data_json['contracts'][trigger_contract_name]['addr']:
                    self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                                 + 'token_addr != [presale_token][addr]')
                    raise SystemExit

            # set presale info
            self.trading_details['presale_start_utc'].value = presaleStartTime
            self.trading_details['presale_address'][0:] = dxsale_addr
            if minEthContribution > self.trading_details['max_bnb_to_buy'].value:
                self.trading_details['max_bnb_to_buy'].value = minEthContribution

            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                         + 'presale_start_utc=' + str(self.trading_details['presale_start_utc'].value) + '|'
                                         + 'presale_address=' + dxsale_addr + '|'
                                         + 'max_bnb_to_buy=' + str(self.trading_details['max_bnb_to_buy'].value))
        except:
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                         + 'dxsale contract call exception')

    def process_transaction(self, transaction):
        # save gas limits
        self.gas_limit_collection[self.gas_limit_collection_idx.value % self.gas_limit_collection_max_size] = transaction.gas
        self.gas_limit_collection_idx.value = self.gas_limit_collection_idx.value + 1
        # save gas price
        self.gas_price_collection[self.gas_price_collection_idx.value % self.gas_price_collection_max_size] = transaction.gasPrice
        self.gas_price_collection_idx.value = self.gas_price_collection_idx.value + 1
        # print(transaction.gasPrice)   # Gas price provided by the sender in wei
        # print(transaction.gas)        # Gas provided
        initialized_limit = 1000
        if self._NETWORK_ == Network.FANTOM:
            initialized_limit = 30
        if self.gas_price_collection_idx.value > initialized_limit:
            # print('wait for more gas price.. len(self.gas_price_collection)=', self.gas_price_collection_idx.value)
            self.gas_price_initialized.value = True

        # hash
        tx = transaction['hash'].hex()

        if self._LPPAIR_SEARCH_:
            # looking for addLiquidity(address tokenA, address tokenB, ...)
            #   internal tx will be from PancakeSwap Factory v2 with the lp pair creation
            if ('0xe8e33700' == transaction['input'][:10]) and \
                    (transaction['to'] == self.data_json['contracts']['PancakeSwap']['addr']):
                self.lppair_search_process(transaction)
            return

        # looking for trigger transaction
        trigger_contract_name = self.trading_details['contract_to_listen']
        decode_input_field = False
        if trigger_contract_name and trigger_contract_name in self.data_json['contracts']:
            decode_input_field = transaction['to'] == self.data_json['contracts'][trigger_contract_name]['contract'].address \
                                 and \
                                 transaction['from'] == self.data_json['contracts'][trigger_contract_name]['owner_addr']

        if decode_input_field:
            # get contract
            contract = self.data_json['contracts'][trigger_contract_name]['contract']

            #TODO: minimal_ABI + decode?

            # decode input
            decoded_input = contract.decode_function_input(transaction.input)
            decoded_input_function_name = decoded_input[0].function_identifier
            decoded_input_arguments = decoded_input[1]

            max_tokens_to_buy = 0
            max_tokens_to_sell = 0

            # process other important function values
            if 'setTransactionlockTime' == decoded_input_function_name:
                try:
                    new_cooldown_time = int(decoded_input_arguments['transactiontime'])
                    self.trading_details['transaction_lock_time'].value = new_cooldown_time
                    self.worker_result_queue.put('LOG'
                                                 + '   __set__   |'
                                                 + 'sym=' + trigger_contract_name + '|'
                                                 + 'block=' + str(transaction.blockNumber) + '|'
                                                 + 'func=' + decoded_input_function_name + '|'
                                                 + 'transaction_lock_time=' + str(new_cooldown_time) + '|'
                                                 + transaction['hash'].hex())
                except:
                    print('no such field, but why?!')
                    pass
            elif 'setMaxTxTokensBuy' == decoded_input_function_name:
                try:
                    max_tokens_to_buy = int(decoded_input_arguments['maxTxTokens'])
                    if max_tokens_to_buy > 0 and self.trading_details['max_tokens_to_buy'].value > 0:
                        self.trading_details['max_tokens_to_buy'].value = min(max_tokens_to_buy, self.trading_details['max_tokens_to_buy'].value)
                    self.worker_result_queue.put('LOG'
                                                 + '   __set__   |'
                                                 + 'sym=' + trigger_contract_name + '|'
                                                 + 'block=' + str(transaction.blockNumber) + '|'
                                                 + 'func=' + decoded_input_function_name + '|'
                                                 + 'func max_tokens_to_buy=' + str(max_tokens_to_buy) + '|'
                                                 + 'set max_tokens_to_buy=' + str(self.trading_details['max_tokens_to_buy'].value) + '|'
                                                 + transaction['hash'].hex())
                except:
                    print('no such field, but why?!')
                    pass
            elif 'setMaxTxTokensSell' == decoded_input_function_name:
                try:
                    max_tokens_to_sell = float(decoded_input_arguments['maxTxTokens'])
                    if max_tokens_to_sell > 0:
                        self.trading_details['max_tokens_to_sell'].value = min(max_tokens_to_sell, self.trading_details['max_tokens_to_sell'].value)
                    self.worker_result_queue.put('LOG'
                                                 + '   __set__   |'
                                                 + 'sym=' + trigger_contract_name + '|'
                                                 + 'block=' + str(transaction.blockNumber) + '|'
                                                 + 'func=' + decoded_input_function_name + '|'
                                                 + 'func max_tokens_to_sell=' + str(max_tokens_to_sell) + '|'
                                                 + 'set max_tokens_to_sell=' + str(self.trading_details['max_tokens_to_sell'].value) + '|'
                                                 + transaction['hash'].hex())
                except:
                    print('no such field, but why?!')
                    pass
            elif self._PRESALE_.value and 'transfer' == decoded_input_function_name:
                self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                             + 'transfer function found for presale_token|'
                                             + tx)
                if 'recipient' in decoded_input_arguments:
                    self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                                 + 'calling decode_dxsale_details')
                    dxsale_addr = self.w3.toChecksumAddress(decoded_input_arguments['recipient'])
                    self.decode_dxsale_details(dxsale_addr)

            start_transaction = False
            is_buying = False
            if 'trigger_func_to_buy' in self.data_json['contracts'][trigger_contract_name]:
                if self.data_json['contracts'][trigger_contract_name]['trigger_func_to_buy'] == decoded_input_function_name:
                    if max_tokens_to_buy > 0 and self.trading_details['max_tokens_to_buy'].value > 0 or \
                       self.trading_details['max_bnb_to_buy'].value > 0:
                        if 'trigger_func_to_buy_value' not in self.data_json['contracts'][trigger_contract_name] or \
                            self.data_json['contracts'][trigger_contract_name]['trigger_func_to_buy_value'] == list(decoded_input_arguments.values())[0]:
                            start_transaction = True
                            is_buying = True
            elif 'trigger_func_to_sell' in self.data_json['contracts'][trigger_contract_name]:
                if self.data_json['contracts'][trigger_contract_name]['trigger_func_to_sell'] == decoded_input_function_name:
                    if max_tokens_to_sell > 0:
                        start_transaction = True
                        is_buying = False

            if start_transaction:
                # !!! BUY / SELL TRIGGER !!!
                # start trading process for all private addresses
                if 1:
                    for account_idx, _ in enumerate(self.data_json['private_data']['private_addresses']):
                        th = mp.Process(target=self.process_trading, args=(trigger_contract_name, is_buying, account_idx,))
                        th.start()
                else:
                    trigger_contract_name = self.trading_details['contract_to_listen']
                    contract = self.data_json['contracts'][trigger_contract_name]['contract']
                    nft_to_buy = 5  # max 5
                    mint_price = contract.functions.MINT_PRICE().call()
                    min_mint_price = contract.functions.price1().call()
                    mint_price = max(mint_price, min_mint_price)

                    sender = self.data_json['private_data']['private_addresses'][0]
                    _txn = contract.functions.createItem(nft_to_buy).buildTransaction({
                        'chainId': self.chain_id,
                        'from': sender['addr'],
                        'gas': 5000000,
                        'gasPrice': self.w3.toWei(6.6, 'Gwei'),
                        'nonce': self.w3.toHex(self.w3.eth.getTransactionCount(sender['addr'])),
                        'value': mint_price * nft_to_buy
                    })
                    signed_txn = self.w3.eth.account.sign_transaction(_txn, private_key=sender['private_key'])
                    if self._ARMED_:
                        tx_token = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
                        tx_hash = self.w3.toHex(tx_token)
                    else:
                        tx_hash = '0x0'
                    self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|TRIGGER TX ' + tx_hash)

            # write to result queue
            self.worker_result_queue.put('LOG'
                                         + 'type=contract|'
                                         + 'sym=' + trigger_contract_name + '|'
                                         + 'block=' + str(transaction.blockNumber) + '|'
                                         + 'idx=' + str(transaction.transactionIndex) + '|'
                                         + transaction['hash'].hex())

            func_argument_str = '\t' + decoded_input_function_name + '()'
            for key, value in decoded_input_arguments.items():
                func_argument_str += str('\r\n\t\t' + str(key) + ': ' + str(value))
            self.worker_result_queue.put('LOG\r\n' + func_argument_str)

            if self._wait_for_events_to_claim:
                # get tx receipt in separate thread
                with self.workers_lock:
                    worker_idx = self.get_free_worker_idx(FilterEntryType.NEW_BLOCK_TRANSACTION)
                    if worker_idx < 0:
                        logging.error('no free worker for process_wait_for_events_to_claim')
                    else:
                        th = mp.Process(target=self.process_wait_for_events_to_claim,
                                        args=(self.workers[worker_idx]['w3'], tx, transaction, decoded_input))
                        # start thread
                        th.start()
                        # assign into self list
                        self.workers[worker_idx]['thread'] = th

        # looking for self transactions
        for account in self.data_json['private_data']['private_addresses']:
            if transaction['from'] == account['addr']:
                # updating account information
                self.update_account_info()
                # get tx receipt in separate thread
                with self.workers_lock:
                    worker_idx = self.get_free_worker_idx(FilterEntryType.NEW_BLOCK_TRANSACTION)
                    if worker_idx < 0:
                        logging.error('no free worker for self transaction|' + str(tx))
                    else:
                        th = mp.Process(target=self.process_self_transaction,
                                        args=(self.workers[worker_idx]['w3'], tx, transaction, account,))
                        # start thread
                        th.start()
                        # assign into self list
                        self.workers[worker_idx]['thread'] = th
                break

        # PancakeSwap transaction
        if transaction['to'] == self.data_json['contracts']['PancakeSwap']['contract'].address:
            self.pancakeswap_decode_input_field(transaction)

    def lppair_search_process(self, transaction):
        if not self._LPPAIR_SEARCH_:
            return
        if '0xe8e33700' != transaction['input'][:10]:
            return
        if transaction['to'] != self.data_json['contracts']['PancakeSwap']['addr']:
            return
        transaction_hex = transaction['hash'].hex()
        transaction_receipt = self.get_transaction_receipt(self.w3, transaction_hex)
        if not transaction_receipt or transaction_receipt['status'] != 1:
            # reverted transaction
            return

        # addLiquidity(address tokenA, address tokenB, ...)
        decoded_input = self.data_json['contracts']['PancakeSwap']['contract'].decode_function_input(transaction.input)
        decoded_input_arguments = decoded_input[1]
        tokenA = decoded_input_arguments['tokenA']
        tokenB = decoded_input_arguments['tokenB']

        # save all lppair creation which is not WBNB
        wbnb_addr = self.data_json['addrs']['WBNB']
        if tokenA != wbnb_addr and tokenB != wbnb_addr:
            # check WBNB pair also exist
            # TODO: main token-wbnb pair should be enough but which one is it
            pc_factory = self.data_json['contracts']['PancakeSwap_factory_v2']['contract']
            wbnb_tokenA_lppair_addr = pc_factory.functions.getPair(tokenA, self.data_json['addrs']['WBNB']).call()
            wbnb_tokenB_lppair_addr = pc_factory.functions.getPair(tokenB, self.data_json['addrs']['WBNB']).call()
            if '0x0000000000000000000000000000000000000000' == wbnb_tokenA_lppair_addr or \
               '0x0000000000000000000000000000000000000000' == wbnb_tokenB_lppair_addr:
                # 0x0 address means no such pair
                return

            # get lp pair address
            lppair_addr = self.dw3.get_pancake_pair_address(tokenA, tokenB)

            # get symbols
            try:
                tokenA_symbol = self.dw3.symbol(tokenA)
            except:
                tokenA_symbol = 'UNKNOWN_tokenA_SYMBOL'
            try:
                tokenB_symbol = self.dw3.symbol(tokenB)
            except:
                tokenB_symbol = 'UNKNOWN_tokenB_SYMBOL'

            # write result into file
            with open('lppair_list.txt', 'a') as result_file:
                result_file.write(str(transaction['blockNumber']) + '; ' +
                                  transaction_hex + '; ' +
                                  tokenA + '; ' +
                                  tokenB + '; ' +
                                  lppair_addr + '; ' +
                                  tokenA_symbol + '-' + tokenB_symbol +
                                  '\r\n')

            self.worker_result_queue.put('DBGLOG' + datetime.datetime.now().strftime("%H:%M:%S.%f")
                                         + '|new lppair|' + transaction_hex)

    def process_self_transaction(self, w3, tx_hash, transaction, account):
        transaction_receipt = self.get_transaction_receipt(w3, tx_hash)
        if transaction_receipt:
            status = 'SUCCESS' if transaction_receipt['status'] == 1 else 'REVERTED'
        else:
            status = 'missing receipt'

        value_bnb = float(self.w3.fromWei(transaction.value, 'ether'))
        value_usd = self.bnb_2_usd(self.w3, value_bnb)
        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                     + 'type=personal (' + account['name'] + ')|'
                                     + 'status=___' + status + '___|'
                                     + 'block=' + str(transaction.blockNumber) + '|'
                                     + 'idx=' + str(transaction.transactionIndex) + '|'
                                     + 'value_BNB=' + f'{value_bnb:.3E}' + '|'
                                     + 'value_USD=' + f'{value_usd:.3E}' + '|'
                                     + tx_hash)

        self.worker_result_queue.put('TELEGRAM' + '```' + datetime.datetime.now().strftime("%H:%M:%S.%f") + '```\n'
                                     + f'personal [transaction](https://bscscan.com/tx/{tx_hash}) ({account["name"]})\n'
                                     + 'status=___' + status + '___')

    def _trade_some_token_(self, contract_name, tx_type: TransactionType, account_idx,
                           encoded_data=None,
                           decimals=18,
                           chill=False,
                           force=False,
                           spend_max_this_wei_without_tx_fee=None,
                           gas_limit=None,
                           gas_price=None,
                           nonce_2_set=None):
        # convert transaction type
        is_buying = False if tx_type == TransactionType.SELL else True
        # get trading array index
        if isinstance(account_idx, dict):
            # TODO
            trading_idx = 0
        else:
            trading_idx = self.get_trading_details_idx(is_buying, account_idx)

        # update trading info
        # set new last trading timestamp, should be one / account
        curr_ts = time.time()
        self.trading_details['last_trade_ts'][trading_idx] = curr_ts
        if isinstance(account_idx, dict):
            self.trading_details['last_trade_ts'][self.get_trading_details_idx((not is_buying), 0)] = curr_ts
        else:
            self.trading_details['last_trade_ts'][self.get_trading_details_idx((not is_buying), account_idx)] = curr_ts
        # update trade cnt
        self.trading_details['successful_trade_cnt'][trading_idx] += 1

        # get web3 object
        w3 = self.w3_real[trading_idx]

        swap_path = None
        if tx_type == TransactionType.SWAP_TOKENS:
            contract = None
            if len(contract_name) != 2:
                print('_trade_some_token_ SWAP_TOKENS ERROR')
            swap_path = [w3.toChecksumAddress(contract_name[0]), w3.toChecksumAddress(contract_name[1])]
            contract_name = swap_path[0] + '->' + swap_path[1]
            decimals = self.dw3.decimals(swap_path[0])
        elif '0x' in contract_name:
            contract = None
            contract_id = w3.toChecksumAddress(contract_name)
            try:
                decimals = self.dw3.decimals(contract_id)
            except:
                if tx_type != TransactionType.SEND:
                    self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                                 + f'ERROR: no decimals for {contract_id}')
                    return
                else:
                    decimals = 0
                    pass
        else:
            # contract
            contract = self.data_json['contracts'][contract_name]['contract']
            # contract decimals
            decimals = int(self.data_json['contracts'][contract_name]['decimals'])
            # contract id is the token we are swapping
            contract_id = w3.toChecksumAddress(contract.address)

        # name of the account
        if isinstance(account_idx, dict):
            # TODO
            account_dict = account_idx
            account_name = account_dict['name']
            sender_address = account_dict['addr']
            private_key = account_dict['private_key']
            account_idx = 0
        else:
            account_name = self.data_json['private_data']['private_addresses'][account_idx]['name']
            # account address
            sender_address = self.data_json['private_data']['private_addresses'][account_idx]['addr']
            # private key
            private_key = self.data_json['private_data']['private_addresses'][account_idx]['private_key']
        # pancakeswap v2 contract
        pancakeswap_contract = self.data_json['contracts']['PancakeSwap']['contract']

        # waiting for gas price initialization
        while not self.gas_price_initialized.value:
            time.sleep(0.5)

        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|-->'
                                     + account_name + ' account'
                                     + ' thread started'
                                     + (' BUYING ' if is_buying else ' SELLING ')
                                     + contract_name
                                     + ' token, max_no_tokens='
                                     + ((str(self.trading_details['max_bnb_to_buy'].value) + ' BNB') if self.trading_details['max_bnb_to_buy'].value > 0 else (str(self.trading_details['max_tokens_to_buy'].value)) \
            if is_buying else str(self.trading_details['max_tokens_to_sell'].value)))

        # howto
        # https://consensys.net/blog/developers/how-to-send-money-using-python-a-web3-py-tutorial/
        # https://zhiyan.blog/2021/05/23/how-to-create-a-pancakeswap-bot-using-python/

        # WBNB
        wbnb_addr = self.data_json['addrs']['WBNB']
        # get my balance before transaction
        # updated in update_account_info() with w3.eth.get_balance(sender_address)
        # my_balance = int(self.data_json['private_data']['private_addresses'][account_idx]['balance'].value)
        my_balance = w3.eth.get_balance(sender_address)

        # human readable balance
        my_balance_in_bnb = w3.fromWei(my_balance, 'ether')
        # keep this amount of bnb in the address
        keep_this_amount = w3.toWei(0.01, 'ether')
        # min money
        if not force and my_balance < keep_this_amount * 1.1:
            # no more money left
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                         + ' min_money reached, kill '
                                         + account_name
                                         + ' trading thread')
            self.trading_details['kill_trading'][trading_idx] = True
            return
        # my transaction id
        # updated in update_account_info() with w3.eth.getTransactionCount(sender_address)
        # nonc = w3.eth.getTransactionCount(sender_address)
        # print(int(self.data_json['private_data']['private_addresses'][account_idx]['nonce'].value), 'vs', nonc)
        # nonce = int(self.data_json['private_data']['private_addresses'][account_idx]['nonce'].value)
        if nonce_2_set is not None:
            nonce = nonce_2_set
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                         + f' nonce set to {nonce_2_set}')
        else:
            nonce = w3.eth.getTransactionCount(sender_address)
        ## gas setup
        # we can calculate the maximum bnb we want to spend for slippage and transaction fee
        spend_max_this_amount = my_balance - keep_this_amount
        # get gas limit median
        try:
            gas_limit_list = self.gas_limit_collection[0:(self.gas_limit_collection_idx.value % self.gas_limit_collection_max_size)]
            gas_limit_median = int(statistics.median(gas_limit_list))
        except:
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                         + 'ERROR: gas_limit_median exception')
            gas_limit_median = 4000000                      # gas_limit

        if not gas_limit:
            gas = int(gas_limit_median * 6)
            gas = self.add_noise(gas, 95, 102)
        else:
            gas = gas_limit

        # median gas price from previous blocks
        try:
            gas_price_list = self.gas_price_collection[0:(self.gas_price_collection_idx.value % self.gas_price_collection_max_size)]
            gas_price_median = int(statistics.median(gas_price_list))
            gas_price_median_gwei = w3.fromWei(gas_price_median, 'Gwei')
        except:
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                         + 'ERROR: gas_price_median exception')
            gas_price_median = self.w3.toWei(15, 'Gwei')    # gas_price
        if not gas_price:
            gas_price = gas_price_median
            if self._NETWORK_ != Network.ETH:
                # no gas price increase in ethereum network, cause its already expensive..
                # https://ethereum.stackexchange.com/questions/6107/what-is-the-default-ordering-of-transactions-during-mining
                # default 3x median
                gas_price = int(gas_price_median * 3)
                if chill:
                    gas = int(1100000)
                    gas_price = int(gas_price_median * 1.3)
            gas_price = self.add_noise(gas_price)

        # got max amount
        if spend_max_this_wei_without_tx_fee is not None:
            max_fee_wei = gas * gas_price
            max_fee_eth = w3.fromWei(max_fee_wei, 'ether')
            max_fee_usd = float(max_fee_eth) * self.get_bnb_price()

            spend_max_this_amount = spend_max_this_wei_without_tx_fee + max_fee_wei
            spend_max_this_amount_eth = w3.fromWei(spend_max_this_amount, 'ether')
            spend_max_this_amount_usd = float(spend_max_this_amount_eth) * self.get_bnb_price()

        # not enough money
        if spend_max_this_amount > my_balance:
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|<--'
                                         + 'ERROR:: not enough money|'
                                         + 'account=' + account_name + '|'
                                         + 'type=' + ('BUYING' if is_buying else 'SELLING') + '|'
                                         + 'spend_max_this_amount_usd=' + f'{spend_max_this_amount_usd:.2E}' + '|'
                                         + 'my_balance=' + f'{float(w3.fromWei(my_balance, "ether"))*self.get_bnb_price():.2E}' + '|'
                                         + 'gas_price_median=' + str(w3.fromWei(gas_price_median, 'Gwei')) + '|'
                                         + 'gas_price=' + str(w3.fromWei(gas_price, 'Gwei')) + '|'
                                         + 'gas=' + str(gas))
            return

        # transaction deadline
        deadline = (int(time.time()) + 20 * 60)
        deadline = self.add_noise(deadline, 100, 102)   # >= 20min
        amount = 0
        used_func = 'unknown'

        # TODO ETH vs fortrun bots?!
        if tx_type == TransactionType.SEND:
            # SEND some token
            used_func = 'send transaction'
            max_bnb_to_buy_wei = w3.toWei(self.trading_details['max_bnb_to_buy'].value, 'ether')
            if force:
                value = max_bnb_to_buy_wei
                if my_balance < value + gas * gas_price:
                    value = my_balance - gas * gas_price
            else:
                value = min(spend_max_this_amount, max_bnb_to_buy_wei)
            _txn = {
                'to': contract_id,
                'value': value,
                'gas': gas,
                'gasPrice': gas_price,
                'nonce': w3.toHex(nonce),
                'chainId': self.chain_id
            }
        elif tx_type == TransactionType.SPEC_HASH:
            used_func = 'spec hash'
            if not encoded_data:
                print('failed')
                _txn = {}
            else:
                # 'value': w3.toWei(1, 'ether'),
                # 'value': 0,
                # 'data': Web3.toBytes(hexstr=encoded_data),
                _txn = {
                    'chainId': self.chain_id,
                    'from': sender_address,
                    'gas': gas,
                    'gasPrice': gas_price,
                    'nonce': w3.toHex(nonce),
                    'to': contract_id,
                    'data': encoded_data
                }
        elif tx_type == TransactionType.PRESALE_CLAIM_TOKENS:
            if self.is_pinksale_presale.value:
                # pinksale
                used_func = 'claim'
                _txn = contract.functions.claim().buildTransaction({
                    'from': sender_address,
                    'gas': gas,
                    'gasPrice': gas_price,
                    'nonce': w3.toHex(nonce),
                })
            else:
                # claim DxSale tokens
                used_func = 'claimTokens'
                _txn = contract.functions.claimTokens().buildTransaction({
                    'from': sender_address,
                    'gas': gas,
                    'gasPrice': gas_price,
                    'nonce': w3.toHex(nonce),
                })
        elif tx_type == TransactionType.PINKSALE_CONTRIBUE:
            # PinkSale contribute presale
            used_func = 'PinkSale_contribute'
            max_bnb_to_buy_wei = w3.toWei(self.trading_details['max_bnb_to_buy'].value, 'ether')
            value = min(spend_max_this_amount, max_bnb_to_buy_wei)
            _txn = contract.functions.contribute().buildTransaction({
                'value': value,
                'gas': gas,
                'gasPrice': gas_price,
                'nonce': w3.toHex(nonce),
                'chainId': self.chain_id
            })
        elif tx_type == TransactionType.SWAP_TOKENS:
            if not swap_path or len(swap_path) != 2:
                print('TransactionType.SWAP_TOKENS ERROR')
                return
            # swap tokens for tokens
            amount = int(self.trading_details['max_tokens_to_sell'].value * 10 ** decimals)
            used_func = 'swapExactTokensForTokensSupportingFeeOnTransferTokens'
            _txn = pancakeswap_contract.functions.swapExactTokensForTokensSupportingFeeOnTransferTokens(
                # the amount of input tokens to send
                amountIn=amount,
                # the minimum amount of output tokens that must be received for the transaction not to revert.
                # specify slippage with this, 0 == dont care
                amountOutMin=0,
                # pay with wbnb
                path=swap_path,
                # receive address
                to=sender_address,
                # deadline = now + 20min
                deadline=deadline
            ).buildTransaction({
                'from': sender_address,
                'gas': gas,
                'gasPrice': gas_price,
                'nonce': w3.toHex(nonce),
            })
        elif is_buying:  # BUYING
            if self.trading_details['max_bnb_to_buy'].value > 0:
                max_bnb_to_buy_wei = w3.toWei(self.trading_details['max_bnb_to_buy'].value, 'ether')
                value = min(spend_max_this_amount, max_bnb_to_buy_wei)
                amount = value # for log
                used_func = 'swapExactETHForTokensSupportingFeeOnTransferTokens'
                _txn = pancakeswap_contract.functions.swapExactETHForTokensSupportingFeeOnTransferTokens(
                    # dont care how many token received
                    amountOutMin=0,
                    # pay with wbnb
                    path=[wbnb_addr, contract_id],
                    # receive address
                    to=sender_address,
                    # deadline = now + 30min
                    deadline=deadline
                ).buildTransaction({
                    'from': sender_address,
                    # this is the maximum WBNB amount we want to swap from
                    # my_balance == all in
                    'value': value,
                    'gas': gas,
                    'gasPrice': gas_price,
                    'nonce': w3.toHex(nonce),
                })
            else:  # swapETHForExactTokens
                amount = int(self.trading_details['max_tokens_to_buy'].value) * 10 ** decimals
                value = min(spend_max_this_amount, w3.toWei(0.1, 'ether'))
                used_func = 'swapETHForExactTokens'
                _txn = pancakeswap_contract.functions.swapETHForExactTokens(
                    # exact number of token to get
                    amountOut=amount,
                    # pay with wbnb
                    path=[wbnb_addr, contract_id],
                    # receive address
                    to=sender_address,
                    # deadline = now + 20min
                    deadline=deadline
                ).buildTransaction({
                    'from': sender_address,
                    # this is the maximum WBNB amount we want to swap from
                    # my_balance == all in
                    # this will eventually specify the slippage
                    'value': value,
                    'gas': gas,
                    'gasPrice': gas_price,
                    'nonce': w3.toHex(nonce),
                })
        else:  # SELLING
            amount = int(self.trading_details['max_tokens_to_sell'].value * 10 ** decimals)
            # set giga slippage
            slippage = 1000000
            amount_out_min = randint(int(amount/(10*slippage)), int(amount/slippage))
            if amount_out_min < (10 ** (decimals + 1)):
                # at least get one token
                amount_out_min = (10 ** (decimals + 1))

            # https://docs.pancakeswap.finance/code/smart-contracts/pancakeswap-exchange/router-v2#swapexacttokensforethsupportingfeeontransfertokens
            used_func = 'swapExactTokensForETHSupportingFeeOnTransferTokens'
            _txn = pancakeswap_contract.functions.swapExactTokensForETHSupportingFeeOnTransferTokens(
                # payable amount of input tokens
                amountIn=amount,
                # minimum amount tokens to receive
                # specify slippage with this, 0 would look suspicious
                amountOutMin=amount_out_min,
                # pay with wbnb
                path=[contract_id, wbnb_addr],
                # receive address
                to=sender_address,
                # deadline = now + 20min
                deadline=deadline
            ).buildTransaction({
                'from': sender_address,
                'gas': gas,
                'gasPrice': gas_price,
                'nonce': w3.toHex(nonce),
            })

        signed_txn = w3.eth.account.sign_transaction(_txn, private_key=private_key)
        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                     + '|' + account_name + ' account, tx signed for'
                                     + (' BUYING ' if is_buying else ' SELLING ')
                                     + contract_name
                                     + '|used_func=' + used_func)

        if self._ARMED_:
            tx_token = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            tx_hash = w3.toHex(tx_token)
        else:
            tx_hash = '0x0'

        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|<--'
                                     + 'account=' + account_name + '|'
                                     + 'type=' + used_func + '|'
                                     + 'amount=' + f'{amount / 10**decimals:.2E}' + '|'
                                     + 'gas_price_median=' + str(w3.fromWei(gas_price_median, 'Gwei')) + '|'
                                     + 'gas_price=' + str(w3.fromWei(gas_price, 'Gwei')) + '|'
                                     + 'gas=' + str(gas) + '|'
                                     + tx_hash)

        # self.worker_result_queue.put('TELEGRAM' + '```' + datetime.datetime.now().strftime("%H:%M:%S.%f") + '```\n'
        #                              + f'[{used_func}](https://bscscan.com/tx/{tx_hash}) sent')

        return tx_hash

    def wait_my_tx_to_be_mined(self, w3, tx, is_buying, account_idx):
        transaction_receipt = self.get_transaction_receipt(w3, tx, max_wait=self.max_wait_for_mining_sec*2)
        if transaction_receipt:
            if transaction_receipt['status'] == 1:
                # SUCCESS, nothing to do
                pass
            else:
                # REVERTED
                # if trade running, decrease success counter and reset last_trade time
                trading_idx = self.get_trading_details_idx(is_buying, account_idx)
                if self.trading_details['is_running'][trading_idx]:
                    # update trade cnt
                    self.trading_details['successful_trade_cnt'][trading_idx] -= 1
                    self.trading_details['last_trade_ts'][trading_idx] = 0
                    self.trading_details['last_trade_ts'][self.get_trading_details_idx((not is_buying), account_idx)] = 0
        else:
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H:%M:%S.%f")
                                         + '|wait_my_tx_to_be_mined() failed|'
                                         + tx)

    def get_transaction_receipt(self, w3, tx, max_wait=None):
        transaction_receipt = None
        try:
            if max_wait:
                transaction_receipt = w3.eth.wait_for_transaction_receipt(tx, timeout=max_wait)
            else:
                transaction_receipt = w3.eth.wait_for_transaction_receipt(tx)
        except w3_exceptions.TransactionNotFound:
            # transaction has not yet been mined throws
            time.sleep(0.1)
            pass
        except:  # catch *all* exceptions
            pass
        if not transaction_receipt:
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                         + '|ERROR get_transaction_receipt() failed for '
                                         + tx)
        return transaction_receipt

    # https://web3py.readthedocs.io/en/stable/web3.eth.html#web3.eth.Eth.get_transaction
    # get transaction from transaction_hash
    def get_transaction(self, w3, tx_ts_type):
        tx = tx_ts_type[0]
        ts = tx_ts_type[1]
        # entry_type = tx_ts_type[2]

        # p = psutil.Process(os.getpid())
        # p.nice(16384)

        success = False
        try:
            transaction = w3.eth.get_transaction(tx)
            success = True
        except w3_exceptions.TransactionNotFound:
            # transaction has not yet been mined throws
            # try again after some sleep
            # logging.warning("TransactionNotFound:: " + tx)
            pass
        except:  # catch *all* exceptions
            e = sys.exc_info()[0]
            logging.error('worker thread failed ' + e.__name__ + ' ' + e.__doc__.replace('\n', '') + ' :: ' + tx)

        if success:
            # got the transaction
            # process transaction
            self.process_transaction(transaction)
        elif time.time() < ts + self.max_wait_for_mining_sec:
            # put back into queue after some sleep
            time.sleep(0.1)
            self.worker_tx_queue.put(tx_ts_type)
            # logging.warning("tx put back: " + tx)
        else:
            # logging.info("get_transaction failed for|" + tx)
            pass

    def get_free_worker_idx(self, entry_type: FilterEntryType):
        worker_idx_start = 0
        worker_idx_end = self.number_of_pending_workers
        if entry_type == FilterEntryType.NEW_BLOCK_HASH or \
           entry_type == FilterEntryType.NEW_BLOCK_TRANSACTION:
            worker_idx_start = self.number_of_pending_workers
            worker_idx_end = self.workers_max

        no_worker = worker_idx_end - worker_idx_start
        self.workers_idx_offset = (self.workers_idx_offset + 1) % no_worker
        for i in range(worker_idx_start, worker_idx_end):
            idx = self.workers_idx_offset + i
            if idx >= worker_idx_end:
                idx -= no_worker
            if not self.workers[idx]['thread']:
                return idx
            elif not self.workers[idx]['thread'].is_alive():
                self.workers[idx]['thread'].join()
                self.workers[idx]['thread'] = None
                # free worker found
                return idx
        return -1

    def get_random_worker_w3(self):
        w3idx = random.randint(0, self.workers_max-1)
        return self.workers[w3idx]['w3']

    def start_worker(self):
        # send tx hashes into free worker threads
        while not self.worker_tx_queue.empty():
            tx_ts_type = self.worker_tx_queue.get()
            entry_type = tx_ts_type[2]

            if entry_type == FilterEntryType.NEW_BLOCK_TRANSACTION:
                transaction = tx_ts_type[0]
                self.process_transaction(transaction)
            else:
                worker_idx = self.get_free_worker_idx(entry_type)
                if worker_idx < 0:
                    # no free worker
                    logging.error('no free worker for '
                                  + 'BLOCK' if entry_type == FilterEntryType.NEW_BLOCK_HASH else 'PENDING' + ' tx|' +
                                                                                                 tx_ts_type[0])
                else:
                    th = mp.Process(target=self.get_transaction, args=(self.workers[worker_idx]['w3'], tx_ts_type,))
                    # start thread
                    th.start()
                    # assign into self list
                    self.workers[worker_idx]['thread'] = th

    def handle_worker_result_queue(self):
        while not self.worker_result_queue.empty():
            result_item = self.worker_result_queue.get()
            if 'DBGLOG' in result_item:
                msg = result_item.replace('DBGLOG', '')
                logging.info(msg)
                print('\x1b[80D\x1b[1A\x1b[K\r', end='')
            elif 'LOG' in result_item:
                msg = result_item.replace('LOG', '')
                logging.info(msg)
            elif 'TELEGRAM' in result_item and not self._DISABLE_TELEGRAM_:
                # send telegram notification
                msg = result_item.replace('TELEGRAM', '')
                msg = msg.replace('_', '')
                telegram_send.send(messages=[msg], parse_mode='markdown', disable_web_page_preview='True')

    def presale_claim(self):
        if not self.data_json['contracts']['pinksale']['contract'] and \
           not self.data_json['contracts']['dxsale']['contract']:
            return

        contract_name = 'dxsale'
        finalized = False
        if self.is_pinksale_presale.value:
            contract_name = 'pinksale'
            presale_contract = self.data_json['contracts'][contract_name]['contract']
            # 0 - incoming / inprogress / filled, 1 - ended, 2 - canceled
            finalized = (presale_contract.functions.poolState().call() == 1)
        else:
            # token claiming possible after dxsale is finalized
            presale_contract = self.data_json['contracts'][contract_name]['contract']
            finalized = presale_contract.functions.isFinalized().call()

        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                     + 'waiting for token claiming() :: finalized = ' + str(finalized))
        if finalized:
            # stop claiming process
            self._PRESALE_CLAIM_.value = False

            # claim
            # TODO: check private address index
            # in case of pinksale wait for owner's finalize() transaction
            th = mp.Process(target=self._trade_some_token_, args=(contract_name, TransactionType.PRESALE_CLAIM_TOKENS, 0,))
            th.start()

    def get_token_price(self, token0, token1=None, token0_decimals=None, token1_decimals=None):
        # how many token0 needed to buy 1 token1
        if not token1:
            token1 = self.data_json['addrs']['WBNB']
        # # swap if needed
        # if token0.lower() > token1.lower():
        #     # https://docs.uniswap.org/protocol/V2/reference/smart-contracts/factory
        #     # token0 is guaranteed to be strictly less than token1 by sort order
        #     token0, token1 = token1, token0
        # get token decimals
        if not token0_decimals:
            token0_decimals = self.dw3.decimals(token0)
        if not token1_decimals:
            token1_decimals = self.dw3.decimals(token1)
        # get reserves
        reserve0, reserve1 = self.dw3.getSortedReserves(token0, token1)
        if not reserve0 or not reserve1:
            # empty pair, try new base token
            if token1 == self.data_json['addrs']['WBNB']:
                # Binance-Peg BSC-USD (BSC-USD)
                base_token = '0x55d398326f99059fF775485246999027B3197955'
            else:
                return 0.0
            # get token price in base token unit
            token0_in_base_token = self.get_token_price(base_token, token0)
            # convert price to wbnb
            wbnb_in_base_token = self.get_token_price(base_token)
            return token0_in_base_token / wbnb_in_base_token
        price = reserve0 * (10 ** (token1_decimals - token0_decimals)) / reserve1
        return price

    def token_price_in_bnb(self, token_addr, token_decimals=None):
        if token_addr.lower() == self.data_json['addrs']['WBNB'].lower():
            return 1.0
        pc_pair_addr = self.dw3.get_pancake_pair_address(token_addr)
        # get reserves
        reserves = self.dw3.getReserves(pc_pair_addr)
        if 0 in reserves:
            # no liquidity
            return None
        # check which one is WBNB
        is_bnb_token1 = token_addr.lower() < self.data_json['addrs']['WBNB'].lower()
        if is_bnb_token1:
            token_price_in_bnb = reserves[1] / reserves[0]
        else:
            token_price_in_bnb = reserves[0] / reserves[1]

        if not token_decimals:
            # get token decimals
            token_decimals = self.dw3.decimals(self.w3.toChecksumAddress(token_addr))
        token_price_in_bnb = token_price_in_bnb / (10 ** (18 - token_decimals))
        return token_price_in_bnb

    def token_price_from_bnb_lp_pair_contract(self, bnb_lp_pair_contract, token_decimals=None):
        # get reserves
        reserves = bnb_lp_pair_contract.functions.getReserves().call()
        # check which one is WBNB
        token1 = bnb_lp_pair_contract.functions.token1().call()
        is_bnb_token1 = token1.lower() == self.data_json['addrs']['WBNB'].lower()
        if is_bnb_token1:
            token_price_in_bnb = reserves[1] / reserves[0]
        else:
            token_price_in_bnb = reserves[0] / reserves[1]

        if not token_decimals:
            # get token decimals
            if is_bnb_token1:
                token0 = bnb_lp_pair_contract.functions.token0().call()
                token_addr = token0
            else:
                token_addr = token1
            token_decimals = self.dw3.decimals(self.w3.toChecksumAddress(token_addr))
        token_price_in_bnb = token_price_in_bnb / (10 ** (18 - token_decimals))
        return token_price_in_bnb

    def get_wallet_tokens_etherscan(self, addr):
        if self._NETWORK_ != Network.ETH:
            assert False

        explorer = self.db_handler.get_network_explorer(self._NETWORK_)
        bscscan_abi_req = explorer + '/tokenholdings?a=' + addr
        wpage = self.scraper.get_page(bscscan_abi_req)

        # parse holdings table
        wallet_token_list = []
        try:
            htable = wpage.find('table', attrs={'id': 'mytable'})
            table_body = htable.find('tbody')
            for row in table_body.findAll('tr'):
                cols = row.findAll('td')
                # cols indexes
                #  0 - name
                #  1 - symbol
                #  2 - contract addr
                #  3 - quantity
                #  4 - price
                #  5 - change in 24h
                #  6 - $ value
                if cols[1].getText() != 'ETH':
                    currency_addr = hex(int(cols[2].getText().replace(' ', ''), 16))
                    token_addr = self.w3.toChecksumAddress(currency_addr)
                else:
                    # native token indication
                    token_addr = '-'
                wallet_token_list.append(token_addr)

        except:
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                         + 'EXCEPTION get_wallet_balance_etherscan() :: webscrape exception')
            return None
        return wallet_token_list

    def get_wallet_balance_etherscan(self, addr, get_balance_dict=False):
        if self._NETWORK_ != Network.ETH:
            assert(False)

        explorer = self.db_handler.get_network_explorer(self._NETWORK_)
        bscscan_abi_req = explorer + '/tokenholdings?a=' + addr
        wpage = self.scraper.get_page(bscscan_abi_req)
        holdings_usd = wpage.find('span', attrs={'id': 'HoldingsUSD'}).getText()
        holdings_usd = holdings_usd.replace('$', '')
        holdings_usd = holdings_usd.replace(',', '')
        holdings_usd = float(holdings_usd)

        if not get_balance_dict:
            return holdings_usd

        # parse holdings table
        balance_dict = []
        try:
            htable = wpage.find('table', attrs={'id': 'mytable'})
            table_body = htable.find('tbody')
            for row in table_body.findAll('tr'):
                cols = row.findAll('td')
                # cols indexes
                #  0 - name
                #  1 - symbol
                #  2 - contract addr
                #  3 - quantity
                #  4 - price
                #  5 - change in 24h
                #  6 - $ value
                if cols[1].getText() != 'ETH':
                    currency_addr = hex(int(cols[2].getText().replace(' ', ''), 16))
                    token_addr = self.w3.toChecksumAddress(currency_addr)
                    token_decimals = self.dw3.decimals(token_addr)
                    token_symbol = self.dw3.symbol(token_addr)
                    token_name = cols[0].getText()
                    balance = self.dw3.balanceOf(token_addr, addr) / 10**token_decimals
                    value_usd = float(cols[6].getText().replace(' ', '').replace('$', '').replace(',', ''))
                else:
                    # native token indication
                    token_addr = '-'
                    token_decimals = 18     # ?!
                    token_symbol = 'BNB'    # i.e. ETH
                    token_name = 'ETH'
                    balance = float(cols[3].getText().replace(' ', '').replace('$', '').replace(',', ''))
                    value_usd = float(cols[6].getText().replace(' ', '').replace('$', '').replace(',', ''))

                balance_dict.append({
                    'balance': balance,
                    'value_usd': value_usd,
                    'currency': {
                        'address': token_addr,
                        'decimals': token_decimals,
                        'name': token_name,
                        'symbol': token_symbol
                    }
                })
        except:
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                         + 'EXCEPTION get_wallet_balance_etherscan() :: webscrape exception')
            return [{}]

        if len(balance_dict):
            # sort ascending order
            balance_dict = sorted(balance_dict, key=lambda d: d['value_usd'], reverse=True)

        return balance_dict

    def get_wallet_balance_bscscan(self, addr, get_balance_dict=False):
        addr = self.w3.toChecksumAddress(addr)
        explorer = self.db_handler.get_network_explorer(self._NETWORK_)
        balance_dict = []
        try:
            # get token list
            # https://bscscan.com/tokenholdingsHandler.aspx?
            #       &a=<ADDRESS>&               - mandatory
            #       &q=
            #       &p=1
            #       &f=0
            #       &h=0                        !! hide $0.00 assets
            #       &sort=total_price_usd
            #       &order=desc
            #       &pUsd24hrs=408.31
            #       &pBtc24hrs=0.008909
            #       &pUsd=412.45
            #       &fav=                                               - mandatory
            #       &langMsg=A%20total%20of%20XX%20tokenSS%20found
            #       &langFilter=Filtered%20by%20XX
            #       &langFirst=First
            #       &langPage=Page%20X%20of%20Y
            #       &langLast=Last
            #       &ps=25

            bscscan_abi_req = explorer + '/tokenholdingsHandler.aspx?&a=' + addr + '&sort=total_price_usd&order=desc&fav=&pUsd=' + f'{self.get_bnb_price():.2f}'
            bscscan_response = self.scraper.get(bscscan_abi_req)
            if 200 == bscscan_response.status_code:
                bscscan_response = bscscan_response.json()

                if not get_balance_dict:
                    total_usd = 0.0
                    if not '-' in bscscan_response['totalusd']:
                        total_usd = float(bscscan_response['totalusd'].replace(',', '').replace('$',''))
                    return total_usd

                wpage = self.scraper.bs(bscscan_response['layout'])
                for row in wpage.findAll('tr'):
                    cols = row.findAll('td')
                    # cols indexes
                    #  0 - fav
                    #  1 - name + address
                    #  2 - symbol
                    #  3 - quantity
                    #  4 - token price
                    #  5 - change in 24h
                    #  6 - value in BNB
                    #  7 - value in USD
                    # TODO get currency from db, insert if not available
                    if cols[2].getText() != 'BNB':
                        hyperlinks = row.findAll('a')
                        currency_addr = hyperlinks[1].getText()
                        token_addr = self.w3.toChecksumAddress(currency_addr)
                        token_decimals = self.dw3.decimals(token_addr)
                        token_symbol = self.dw3.symbol(token_addr)
                        token_name = self.dw3.name(token_addr)
                        balance = self.dw3.balanceOf(token_addr, addr) / 10**token_decimals
                        token_price = self.token_price_in_bnb(currency_addr, token_decimals)
                        if token_price is None:
                            # TODO..
                            token_price = 0.0
                        value_usd = token_price * self.get_bnb_price() * balance
                        # value_usd = float(cols[7].getText().replace(' ', '').replace('$', '').replace(',', ''))
                    else:
                        # native BNB token indication
                        token_addr = '-'
                        token_decimals = 18
                        token_symbol = 'BNB'
                        token_name = 'Binance'
                        balance = self.w3.eth.getBalance(addr) / 10**token_decimals
                        value_usd = self.get_bnb_price() * balance
                        # balance_ = float(cols[3].getText().replace(' ', '').replace('$', '').replace(',', ''))
                        # value_usd_ = float(cols[7].getText().replace(' ', '').replace('$', '').replace(',', ''))

                    balance_dict.append({
                        'balance': balance,
                        'value_usd': value_usd,
                        'currency': {
                            'address': token_addr,
                            'decimals': token_decimals,
                            'name': token_name,
                            'symbol': token_symbol
                        }
                    })

        except:
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                         + 'EXCEPTION get_wallet_balance_bscscan() :: webscrape exception')
            return [{}]

        if len(balance_dict):
            # sort ascending order
            balance_dict = sorted(balance_dict, key=lambda d: d['value_usd'], reverse=True)

        return balance_dict

    def get_wallet_balance_poocoin(self, addr, only_first=False, get_balance_dict=None, enable_print=False):
        addr = self.w3.toChecksumAddress(addr)
        # poocoin request
        url = 'https://chartdata.poocoin.app/'
        header = {'authority': 'chartdata.poocoin.app',
                  'sec-ch-ua': '"Chromium";v="92", " Not A;Brand";v="99", "Google Chrome";v="92"',
                  'sec-ch-ua-mobile': '?0',
                  'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36',
                  'content-type': 'application/json',
                  'accept': '*/*',
                  'origin': 'https://poocoin.app',
                  'sec-fetch-site': 'same-site',
                  'sec-fetch-mode': 'cors',
                  'sec-fetch-dest': 'empty',
                  'referer': 'https://poocoin.app/',
                  'accept-language': 'hu-HU,hu;q=0.9,en-GB;q=0.8,en;q=0.7,en-US;q=0.6'}

        raw_data = '{"query":"query GetWalletTokens($network: EthereumNetwork\u0021, ' \
                   '$address: String\u0021) ' \
                   '{\\n    ethereum(network: $network) {\\n      address(address: { is: $address }) {\\n        address\\n        balances {\\n          value\\n          currency {\\n            address\\n            name\\n            symbol\\n            tokenType\\n            decimals\\n          }\\n        }\\n      }\\n    }\\n  }",' \
                   '"variables":{"network":"bsc","address":"' + addr + '"}}'

        sum_value_in_usd = 0
        try:
            response = requests.post(url, data=raw_data, headers=header)
            if 200 == response.status_code:
                wallet_tokens = response.json()
                addr_list = wallet_tokens['data']['ethereum']['address']
                if addr.lower() != addr_list[0]['address'].lower():
                    print('not the requested balance')
                else:
                    # filter fake tokens
                    balance_dict_filtered = []
                    for balance_dict in addr_list[0]['balances']:
                        currency_addr = balance_dict['currency']['address']
                        try:
                            currency_addr = self.w3.toChecksumAddress(balance_dict['currency']['address'])
                        except:
                            # e.g. Binance Native Token: balance_dict['currency']['address'] == '-'
                            pass
                        currency_name = balance_dict['currency']['name']
                        if '.io' in currency_name.lower() or \
                           '.org' in currency_name.lower() or \
                           '.net' in currency_name.lower():
                            continue
                        balance_dict_filtered.append(balance_dict)
                    addr_list[0]['balances'] = balance_dict_filtered

                    if get_balance_dict:
                        return addr_list[0]['balances']

                    for balance_dict in addr_list[0]['balances']:
                        currency_addr = balance_dict['currency']['address']
                        try:
                            currency_addr = self.w3.toChecksumAddress(balance_dict['currency']['address'])
                        except:
                            # e.g. Binance Native Token: balance_dict['currency']['address'] == '-'
                            pass
                        value = balance_dict['value']
                        currency_name = balance_dict['currency']['name']
                        currency_symbol = balance_dict['currency']['symbol']
                        currency_decimals = balance_dict['currency']['decimals']

                        if 'BNB' == currency_symbol:
                            # self.w3.eth.getBalance(addr)
                            value_in_usd = self.get_bnb_price() * value
                        else:
                            # update value with currency balanceof
                            currency_decimals = self.dw3.decimals(currency_addr)
                            value = self.dw3.balanceOf(currency_addr, addr) / 10 ** currency_decimals

                            if 'BUSD' == currency_symbol or 'USDT' == currency_symbol:
                                value_in_usd = value
                            else:
                                # get token price in wbnb

                                token_price_in_bnb = self.token_price_in_bnb(currency_addr, currency_decimals)
                                if token_price_in_bnb is None:
                                    # TODO..
                                    token_price_in_bnb = 0.0
                                if token_price_in_bnb > 1e-5 or value > 1e5:
                                    token_price_in_usd = token_price_in_bnb * self.get_bnb_price()
                                    value_in_usd = token_price_in_usd * value
                                else:
                                    value_in_usd = 0
                        if enable_print:
                            print('\t', float("{:.2f}".format(value_in_usd)), currency_name, currency_addr)
                        sum_value_in_usd += value_in_usd

                        if only_first:
                            break

                    # print(addr, sum_value_in_usd)
        except:
            e = sys.exc_info()[0]
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H:%M:%S.%f")
                                         + '|cannot get wallet balance for ' + addr \
                                         + '| ' + e.__name__ + e.__doc__.replace('\n', ''))
        if get_balance_dict:
            return None

        return sum_value_in_usd

    def get_wallet_tokens_bscscan(self, addr):
        addr = self.w3.toChecksumAddress(addr)
        explorer = self.db_handler.get_network_explorer(self._NETWORK_)
        native_token_symbol = 'BNB'
        if self._NETWORK_ == Network.MATIC:
            native_token_symbol = 'MATIC'
        elif self._NETWORK_ == Network.FANTOM:
            native_token_symbol = 'FTM'
        elif self._NETWORK_ == Network.AVAX:
            native_token_symbol = 'AVAX'
        wallet_token_list = []
        try:
            # get token list
            # https://bscscan.com/tokenholdingsHandler.aspx?
            #       &a=<ADDRESS>&               - mandatory
            #       &q=
            #       &p=1
            #       &f=0
            #       &h=0                        - hide $0.00 assets
            #       &sort=total_price_usd
            #       &order=desc                 - order
            #       &pUsd24hrs=408.31
            #       &pBtc24hrs=0.008909
            #       &pUsd=412.45                 - bnb price for correct token prices
            #       &fav=                        - mandatory
            #       &langMsg=A%20total%20of%20XX%20tokenSS%20found
            #       &langFilter=Filtered%20by%20XX
            #       &langFirst=First
            #       &langPage=Page%20X%20of%20Y
            #       &langLast=Last
            #       &ps=100                      - number of tokens per page
            bscscan_abi_req = explorer + '/tokenholdingsHandler.aspx?&a=' + addr + '&ps=1000&order=desc&fav='
            bscscan_response = self.scraper.get(bscscan_abi_req)
            if 200 == bscscan_response.status_code:
                bscscan_response = bscscan_response.json()
                wpage = self.scraper.bs(bscscan_response['layout'])
                if 'No token found' in wpage.getText():
                    # empty wallet
                    return wallet_token_list
                try:
                    for row in wpage.findAll('tr'):
                        cols = row.findAll('td')
                        # cols indexes
                        #  0 - fav
                        #  1 - name + address
                        #  2 - symbol
                        #  3 - quantity
                        #  4 - token price
                        #  5 - change in 24h
                        #  6 - value in BNB
                        #  7 - value in USD
                        if cols[2].getText() != native_token_symbol:
                            hyperlinks = row.findAll('a')
                            currency_addr = hyperlinks[1].getText()
                            token_addr = self.w3.toChecksumAddress(currency_addr)
                        else:
                            # native BNB token indication
                            token_addr = '-'
                        wallet_token_list.append(token_addr)
                except:
                    return wallet_token_list
        except:
            e = sys.exc_info()[0]
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                         + '|ERROR:: get_wallet_tokens_bscscan() for ' + addr
                                         + '| ' + e.__name__ + e.__doc__.replace('\n', ''))
            return None
        return wallet_token_list

    def get_wallet_tokens_poocoin(self, addr):
        addr = self.w3.toChecksumAddress(addr)
        # poocoin request
        url = 'https://chartdata.poocoin.app/'
        header = {'authority': 'chartdata.poocoin.app',
                  'sec-ch-ua': '"Chromium";v="92", " Not A;Brand";v="99", "Google Chrome";v="92"',
                  'sec-ch-ua-mobile': '?0',
                  'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36',
                  'content-type': 'application/json',
                  'accept': '*/*',
                  'origin': 'https://poocoin.app',
                  'sec-fetch-site': 'same-site',
                  'sec-fetch-mode': 'cors',
                  'sec-fetch-dest': 'empty',
                  'referer': 'https://poocoin.app/',
                  'accept-language': 'hu-HU,hu;q=0.9,en-GB;q=0.8,en;q=0.7,en-US;q=0.6'}

        raw_data = '{"query":"query GetWalletTokens($network: EthereumNetwork\u0021, ' \
                   '$address: String\u0021) ' \
                   '{\\n    ethereum(network: $network) {\\n      address(address: { is: $address }) {\\n        address\\n        balances {\\n          value\\n          currency {\\n            address\\n            name\\n            symbol\\n            tokenType\\n            decimals\\n          }\\n        }\\n      }\\n    }\\n  }",' \
                   '"variables":{"network":"bsc","address":"' + addr + '"}}'

        wallet_token_list = []
        try:
            response = requests.post(url, data=raw_data, headers=header)
            if 200 == response.status_code:
                wallet_tokens = response.json()
                addr_list = wallet_tokens['data']['ethereum']['address']
                if addr.lower() != addr_list[0]['address'].lower():
                    self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H:%M:%S.%f")
                                                 + '|get_wallet_tokens_poocoin() not the requested addr ' + addr)
                    return None
                elif addr_list[0]['balances'] is not None:
                    for balance_dict in addr_list[0]['balances']:
                        currency_addr = balance_dict['currency']['address']
                        try:
                            currency_addr = self.w3.toChecksumAddress(balance_dict['currency']['address'])
                        except:
                            # e.g. Binance Native Token: balance_dict['currency']['address'] == '-'
                            pass
                        wallet_token_list.append(currency_addr)
        except:
            e = sys.exc_info()[0]
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H:%M:%S.%f")
                                         + '|ERROR:: get_wallet_tokens_poocoin for ' + addr
                                         + '| ' + e.__name__ + e.__doc__.replace('\n', ''))
            return None
        return wallet_token_list

    def get_wallet_balance(self, wallet_address, force_update=False):
        wallet_address = self.w3.toChecksumAddress(wallet_address)
        expiration_sec = 30*60  # 30 min wallet's token holdings update interval

        retval = {
            'wallet_balance_usd': 0.0,
            'balances': [],
            'success': True
        }
        # try to get token holdings from db
        update_wallet_holdings = False
        wallet_token_list, last_value_update = self.db_handler.get_wallet_holding_addresses(wallet_address)
        if wallet_token_list is None:
            update_wallet_holdings = True
        if last_value_update and last_value_update + expiration_sec < time.time():
            update_wallet_holdings = True
        if force_update:
            update_wallet_holdings = True

        if update_wallet_holdings:
            # not jet in db or expired
            # clear db with address, insert new addresses later
            self.db_handler.remove_all_wallet_holdings_table(wallet_address)
            # get wallet holdings
            # TODO: testnet
            if self._NETWORK_ == Network.ETH:
                wallet_token_list = self.get_wallet_tokens_etherscan(wallet_address)
            elif self._NETWORK_ == Network.BSC:
                wallet_token_list = self.get_wallet_tokens_poocoin(wallet_address)    # ~0.1 s/req
            else:
                # self._NETWORK_ == Network.MATIC
                wallet_token_list = self.get_wallet_tokens_bscscan(wallet_address)    # ~0.3 s/req

        if wallet_token_list is None:
            print('ERROR:: get_wallet_balance()', wallet_address)
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                         + ' ERROR:: get_wallet_balance() ' + wallet_address)
            retval['success'] = False
            return retval

        for token_addr in wallet_token_list:
            token_currency = self.get_currency(token_addr)
            if not token_currency['fake']:
                balance_with_decimals = self.dw3.balanceOf(token_currency['address'], wallet_address)
                balance = balance_with_decimals / 10 ** token_currency['decimals']
                usd_value = balance * token_currency['value_usd']

                retval['wallet_balance_usd'] += usd_value
                retval['balances'].append({
                    'quantity': balance,
                    'balance': balance_with_decimals,
                    'value': usd_value,
                    'currency': token_currency
                })

                # print('\t\t', token_currency['address'], token_currency['name'], usd_value)
            if update_wallet_holdings:
                # insert into wallet holdings db
                self.db_handler.insert_into_wallet_holdings_table(wallet_address, token_currency['currency_id'])
        if update_wallet_holdings and not wallet_token_list:
            # empty wallet
            self.db_handler.insert_into_wallet_holdings_table(wallet_address)

        # sort ascending order
        if len(retval['balances']):
            retval['balances'] = sorted(retval['balances'], key=lambda d: d['value'], reverse=True)

        return retval

    def get_currency(self, token_addr):
        VALUE_UPDATE_INTERVAL_ = 5*60   # 5min
        curr = self.db_handler.get_currency(token_addr)
        if not curr:
            fake_token = False  # not fake by default
            # get token details
            if '-' == token_addr:
                 # TODO: eth
                # BNB native token, no address
                token_decimals = 18
                token_name = 'BNB native token'
                token_symbol = 'BNB'
                token_value_usd = self.get_token_price(token0=self.data_json['addrs']['BUSD'],
                                                       token1=self.data_json['addrs']['WBNB'])
            else:
                token_addr = self.w3.toChecksumAddress(token_addr)
                token_name = self.dw3.name(token_addr)
                token_symbol = self.dw3.symbol(token_addr)
                token_decimals = 0
                token_value_bnb = 0.0
                try:
                    token_decimals = self.dw3.decimals(token_addr)
                    token_value_bnb = self.token_price_in_bnb(token_addr, token_decimals)
                except:
                    # no decimals, probably NFT token
                    fake_token = True
                if token_value_bnb is None:
                    token_value_usd = self.get_token_price(token0=self.data_json['addrs']['BUSD'],
                                                        token1=token_addr,
                                                        token0_decimals=18,
                                                        token1_decimals=token_decimals)
                else:
                    token_value_usd = token_value_bnb * self.get_bnb_price()    # recursive
            # write into currency table
            self.db_handler.insert_into_currency_table(address=token_addr,
                                                       decimals=token_decimals,
                                                       name=token_name,
                                                       symbol=token_symbol,
                                                       usd_value=token_value_usd,
                                                       fake=fake_token)
            curr = self.db_handler.get_currency(token_addr)
            if not curr:
                print('get_currency()', token_addr)
                assert False
                return None
        elif (not curr[7]) and (curr[6] + VALUE_UPDATE_INTERVAL_ < time.time()):
            # not fake and price update necessary
            if '-' == token_addr:
                token_value_usd = self.get_token_price(token0=self.data_json['addrs']['BUSD'],
                                                       token1=self.data_json['addrs']['WBNB'])
            else:
                token_decimals = curr[2]
                token_value_bnb = self.token_price_in_bnb(token_addr, token_decimals)
                if token_value_bnb is None:
                    token_value_usd = self.get_token_price(token0=self.data_json['addrs']['BUSD'],
                                                           token1=token_addr,
                                                           token1_decimals=token_decimals)
                else:
                    token_value_usd = token_value_bnb * self.get_bnb_price()
            currency_id = curr[0]
            curr = self.db_handler.update_currency_price(currency_id, token_value_usd)

        return {
            'currency_id': curr[0],
            'address': curr[1],
            'decimals': curr[2],
            'name': curr[3],
            'symbol': curr[4],
            'value_usd': curr[5],
            'fake': curr[7]
        }

    def get_bnb_price(self):
        bnb_currency = self.get_currency('-')
        return bnb_currency['value_usd']

    def smart_contract_withdraw(self, token_addr):
        w3 = self.w3
        sender = self.SENDER
        token_addr = self.w3.toChecksumAddress(token_addr)

        abi_encoded = encode_abi(['address','bool'], [token_addr, True])
        data = w3u.get_encoded_function_signature('withdrawTokens(address,bool)') + abi_encoded.hex()
        _txn = {
            'chainId': self.chain_id,
            'from': sender['addr'],
            'gas': 2000000,
            'gasPrice': w3.toWei(5, 'Gwei'),
            'nonce': w3.toHex(self.w3.eth.getTransactionCount(sender['addr'])),
            'to': self.ONE_SHOT_CLAIM_FACTORY_ADDR,
            'data': data
        }
        try:
            gas_estimate = w3.eth.estimate_gas(_txn)
            bnb_currency = self.get_currency('-')
            gas_estimate_usd_value = gas_estimate * _txn['gasPrice'] / 10 ** bnb_currency['decimals'] * bnb_currency['value_usd']
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + f'|execution looks fine with gas_estimate {gas_estimate} (${gas_estimate_usd_value:.2f})')

            # modify gas based on gas_estimate
            _txn['gas'] = gas_estimate
            signed_txn = w3.eth.account.sign_transaction(_txn, private_key=sender['private_key'])
        except w3_exceptions.ContractLogicError as err:
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + f'|ERROR: execution will fail with "{err}"')
            return

        if self._ARMED_:
            tx_token = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            tx_hash = self.w3.toHex(tx_token)
        else:
            tx_hash = '0x0'
        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|tx sent, wait for result ' + tx_hash)
        tx_receipt = self.get_transaction_receipt(w3, tx_hash)
        if not tx_receipt or tx_receipt['status'] == 0:
            if tx_receipt:
                self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + f'|transaction failed for {tx_hash}, exiting..')
            else:
                self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + f'|failed to get receipt for {tx_hash}, exiting..')
            return
        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + f'|success {tx_hash}')

    def update_transfer_listener_filter(self):
        with self.tx_filter_lock:
            # save previous filter id
            prev_filter_id = self.filter_in_id.value

            # for testing
            filter_from_block = 'latest'  # 17266340
            filter_to_block = 'latest'  # 17266350

            # get tracker addresses
            tracker_addrs = set()
            for key, value in self.smart_contract_ths.items():
                for ta in value['tracker_addresses']:
                    tracker_addrs.add(ta)
            tracker_addrs_64byte = ['0x' + remove_0x_prefix(ta).lower().zfill(64) for ta in tracker_addrs]

            # setup filter for IN transactions to any tracker address
            new_log_filter = self.w3.eth.filter({
                'fromBlock': filter_from_block,
                'toBlock': filter_to_block,
                'topics': [
                    self.w3.keccak(text="Transfer(address,address,uint256)").hex(),
                    None,
                    tracker_addrs_64byte
                ]
            })
            # save filter_id
            self.filter_in_id.value = new_log_filter.filter_id

            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime('%H%M%S.%f')
                                         + f'|update_transfer_listener_filter() new filter  (id={self.filter_in_id.value}) '
                                           f'created with tracker_addrs = {tracker_addrs}')

        # lock released, uninstall old filter
        if len(prev_filter_id):
            is_uninstalled = self.w3.eth.uninstall_filter(prev_filter_id)
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime('%H%M%S.%f')
                                         + f'|update_transfer_listener_filter() prev filter (id={prev_filter_id}) '
                                           f'{"successful" if is_uninstalled else "failed"} uninstall')

    def get_token_source_code(self, addr):
        result = {
            'verified': False,
            'sols': None,
            'abi_json': None,
            'contract_name': None
        }
        addr = self.w3.toChecksumAddress(addr)
        # get source code
        explorer = self.db_handler.get_network_explorer(self._NETWORK_)
        bscscan_apikey = self.data_json['private_data'][explorer]['apikey']
        bscscan_abi_req = 'https://api.' \
                          + explorer.split('https://')[1] \
                          + '/api?module=contract&action=getsourcecode&address=' + addr + '&apikey=' + bscscan_apikey
        try:
            bscscan_response = requests.get(bscscan_abi_req).json()
            if bscscan_response['status']:
                result_source_code = bscscan_response['result'][0]['SourceCode']
                result_abi = bscscan_response['result'][0]['ABI'].replace('\n', '')

                if '' == result_source_code and 'not verified' in result_abi:
                    # missing source
                    result['verified'] = False
                    return result
                else:
                    result['verified'] = True

                try:
                    result['abi_json'] = json.loads(result_abi)
                except:
                    result['abi_json'] = None
                    self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H:%M:%S.%f")
                                                 + '|get_token_source_code() abi json creation failed')
                result['contract_name'] = bscscan_response['result'][0]['ContractName']

                if '{{' in result_source_code:
                    result_source_code = result_source_code.replace('{{', '{')
                    result_source_code = result_source_code.replace('}}', '}')

                # could be single or multiple sol files
                try:
                    sols = json.loads(result_source_code)
                except:
                    sols = {
                        bscscan_response['result'][0]['ContractName'] + '.sol': {
                            'content': result_source_code
                        }
                    }
                if 'sources' in sols:
                    sols = sols['sources']

                result['sols'] = sols
        except:
            e = sys.exc_info()[0]
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H:%M:%S.%f")
                                         + '|get_token_source_code() exception ::'
                                         + e.__name__ + ', ' + e.__doc__.replace('\n', ''))
        return result

    def get_magnified_dividend_storage_idxs(self, address=None, contract_code=None):
        '''
        magnifiedDividendPerShare and magnifiedDividendCorrections needed for direct dividend distribution calculation

        	function accumulativeDividendOf(address _owner) public view override returns(uint256) {
                    return magnifiedDividendPerShare.mul(balanceOf(_owner)).toInt256Safe()
                    .add(magnifiedDividendCorrections[_owner]).toUint256Safe() / magnitude;
            }
        '''
        magnified_dividend_per_share_storage_idx = None
        magnified_dividend_corrections_storage_idx = None
        magnitude = None
        try:
            # get contract code
            if address:
                address = self.w3.toChecksumAddress(address)
                contract_code = self.w3.eth.get_code(address).hex()
            elif not contract_code:
                self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                             + '|ERROR: get_magnified_dividend_storage_idxs() address or contract_code needed')
                return magnified_dividend_per_share_storage_idx, magnified_dividend_corrections_storage_idx

            # get decompiled version of accumulativeDividendOf(address) == unknown27ce0147 with storage
            decompiled_fn = subprocess.run(['panoramix',
                                         contract_code,
                                         'unknown27ce0147',
                                         '--silent'], stdout=subprocess.PIPE).stdout.decode('utf-8')
            # print(decompiled_fn)
            # remove color codes
            decompiled_fn = re.sub(r'\x1b(\[.*?[@-~]|\].*?(\x07|\x1b\\))', '', decompiled_fn)
            # crop storage information
            storage_info = re.findall(r'stor[0-9]+[ ]is.*', decompiled_fn)
            # get necessary indexes
            for si in storage_info:
                if 'is uint256 at storage' in si:
                    magnified_dividend_per_share_storage_idx = int(si.split(' ')[-1])
                elif 'is mapping of struct at storage' in si:
                    magnified_dividend_corrections_storage_idx = int(si.split(' ')[-1])
            if magnified_dividend_corrections_storage_idx is None:
                # alternative
                '''
                  stor0 is mapping of uint256 at storage 0
                  stor7 is uint256 at storage 7
                  stor9 is mapping of uint256 at storage 9
                '''
                for si in storage_info:
                    if 'stor0' in si:
                        continue
                    elif 'mapping of ' in si:
                        magnified_dividend_corrections_storage_idx = int(si.split(' ')[-1])

            # get magnitude constant
            #  return (Mask(128, 128, (stor5 * stor0[addr(_param1)]) + stor7[addr(_param1)].field_0) >> 128)
            magnitude = int(re.findall(r'(?<=>>).*(?=\))', decompiled_fn)[0])
        except:
            e = sys.exc_info()[0]
            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                         + '|get_magnified_dividend_storage_idxs() exception ::'
                                         + e.__name__ + ', ' + e.__doc__.replace('\n', ''))
        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                     + f'|get_magnified_dividend_storage_idxs() '
                                       f'magnified_dividend_per_share_storage_idx={magnified_dividend_per_share_storage_idx}, '
                                       f'magnified_dividend_corrections_storage_idx={magnified_dividend_corrections_storage_idx}, '
                                       f'magnitude={magnitude}')
        return magnified_dividend_per_share_storage_idx, \
               magnified_dividend_corrections_storage_idx, \
               None if magnitude is None else 2**magnitude

    def presale_process(self, block):
        # get block timestamp
        curr_ts = block.timestamp

        if self._PRESALE_CLAIM_.value:
            presale_claim_check_min_interval = 0  # 10
            if curr_ts - self.prev_claim_timestamp.value > presale_claim_check_min_interval:
                # 10 sec poll
                th = mp.Process(target=self.presale_claim())
                th.start()
                self.prev_claim_timestamp.value = curr_ts

        if not self._PRESALE_.value:
            return

        presale_address = self.trading_details['presale_address'][0:]
        # print(' ', presale_address)
        if self.trading_details['presale_start_utc'].value < 0 or \
           presale_address == self.ZERO_ADDR:
            return

        if self.prev_block_timestamp.value < 0:
            self.prev_block_timestamp.value = curr_ts
        if self.prev_block_timestamp.value > curr_ts:
            return

        dt_block = curr_ts - self.prev_block_timestamp.value
        self.prev_block_timestamp.value = curr_ts

        self.block_dt_collection[self.block_dt_collection_idx.value % self.block_dt_collection_max_size] = dt_block
        self.block_dt_collection_idx.value = self.block_dt_collection_idx.value + 1
        block_dt_list = self.block_dt_collection[0:(self.block_dt_collection_idx.value % self.block_dt_collection_max_size)]
        dt_median = int(statistics.median(block_dt_list))

        wait_for_this_utc = int(self.trading_details['presale_start_utc'].value)
        # after next is timeout --> send now
        if curr_ts + dt_median * 2 >= wait_for_this_utc:
            # send money
            if self.is_pinksale_presale.value:
                th = mp.Process(target=self._trade_some_token_, args=(
                                'pinksale',
                                TransactionType.PINKSALE_CONTRIBUE,
                                0,
                                None,
                                0,
                                False,
                                False,
                                None,
                                4000000,                     # gas_limit
                                self.w3.toWei(16, 'Gwei')))  # gas_price

            else:
                th = mp.Process(target=self._trade_some_token_, args=(
                                presale_address,
                                TransactionType.SEND,
                                0,
                                None,
                                0,
                                False,
                                False,
                                None,
                                4000000,                     # gas_limit
                                self.w3.toWei(16, 'Gwei')))  # gas_price
            th.start()

            print('#################################### PRESALE trigger ##################################')
            self._PRESALE_.value = False

        countdown_sec = wait_for_this_utc - curr_ts
        countdown_min = int(countdown_sec / 60)
        countdown_h = int(countdown_min / 60)
        countdown_min -= countdown_h * 60
        countdown_sec -= (countdown_h * 60 * 60 + countdown_min * 60)
        countdown_str = f' {countdown_h}h {countdown_min}m {countdown_sec}s '
        self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f") + '|'
                                     + 'presale countdown=' + countdown_str + '|curr time=' + str(curr_ts) + ', dt_block=' + str(dt_block) + ', dt_median=' + str(dt_median))

    def get_block_transactions(self, block_num, w3=None, recursion_cnt=0):
        full_transactions = True
        if not w3:
            w3len = len(self.w3_get_block)
            w3 = self.w3_get_block[recursion_cnt % w3len]
        try:
            # statistic
            self.event_cnt[int(FilterEntryType.NEW_BLOCK)] += 1

            # self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
            #                              + f'|w3.eth.get_block({block_num})')
            # call get block
            block = w3.eth.get_block(block_num, full_transactions=full_transactions)
        except:  # catch *all* exceptions
            # e = sys.exc_info()[0]
            # estr = e.__doc__.replace('\n', '')
            # logging.error(f'get_block_transactions({block_num}) exception {e.__name__}, {estr}, recursion_cnt={recursion_cnt}')

            if recursion_cnt > 4:
                # no more try
                logging.error(f'{datetime.datetime.now().strftime("%H%M%S.%f")} get_block_transactions({block_num}) missed block')
            else:
                # tune next processing time with recursion
                time_to_process = time.time() + (3 * (recursion_cnt + 1) * 10) * randint(90, 110) / 100
                with self.block_list_lock:
                    self.block_list.append({
                        'block_num': block_num,
                        'time_to_process': time_to_process,
                        'recursion_cnt': recursion_cnt+1
                    })
                # self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                #                              + f'| retry block {block_num}, recursion_cnt={recursion_cnt}, time until next try={time_to_process-time.time():.2f}')
            return

        self.worker_result_queue.put('DBGLOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                     + '| ##### block=' + str(block['number']) + '|tx_cnt=' + str(len(block['transactions'])))

        # start new process with presale
        self.presale_process(block)

        for t in block['transactions']:
            if full_transactions:
                # put transaction into queue with current timestamp
                self.worker_tx_queue.put([t, time.time(), FilterEntryType.NEW_BLOCK_TRANSACTION])
            else:
                tx = t.hex()
                # put tx hashes into queue with current timestamp
                self.worker_tx_queue.put([tx, time.time(), FilterEntryType.NEW_BLOCK_HASH])
            self.event_cnt[int(FilterEntryType.NEW_BLOCK_HASH)] += 1

    def tune_poll_interval(self, target_req_per_sec, start_time):
        # curr_time = time.time()
        # block_per_sec = self.event_cnt[int(FilterEntryType.NEW_BLOCK)] / (curr_time - start_time)
        # if 0 == (int(curr_time) - int(start_time)) % 5:
        #     # print('\r', end='')
        #     # print(f'{block_per_sec:.2f}', 'block/sec ', end='\n')
        #     print(f'{block_per_sec:.2f}', 'block/sec ')
        if target_req_per_sec:
            self.poll_interval.value = 1/target_req_per_sec
        else:
            self.poll_interval.value = 0

    def poll_block_num(self):
        block_dt_theoretical = 3
        block_dt_moving = block_dt_theoretical
        last_block_ts = -1
        prev_block_number = -1
        block_offset = self.poll_blocknum_offset       # to ensure block available

        while not self.mp_exit_main_loop.value:
            curr_time = time.time()

            block_nums = []
            for w3 in self.w3_get_block:
                try:
                    block_num = w3.eth.block_number
                    block_nums.append(block_num)
                except:
                    e = sys.exc_info()[0]
                    self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                                 + f'|ERROR: poll_block_num() {e.__name__} {e.__doc__}')
            if not block_nums:
                block_nums = [-1]

            block_num_web3 = max(block_nums) + block_offset
            block_num_pred = prev_block_number + int((curr_time - last_block_ts) / block_dt_moving)
            # self.worker_result_queue.put('DBGLOG' + datetime.datetime.now().strftime('%H%M%S.%f')
            #                              + f'| {block_num_web3}, {block_num_pred}, {prev_block_number}, {curr_time - last_block_ts}, {block_dt_moving}')

            if prev_block_number < block_num_web3:
                block_num = block_num_web3
                if prev_block_number < 0:
                    prev_block_number = block_num - 1
                block_dt_moving = block_dt_theoretical
                # self.worker_result_queue.put('DBGLOG' + datetime.datetime.now().strftime('%H%M%S.%f')
                #                              + f'|blocknum received |{block_num_web3}')
            elif prev_block_number < block_num_pred:
                block_num = block_num_pred
                block_dt_moving += 0.1
                # self.worker_result_queue.put('DBGLOG' + datetime.datetime.now().strftime('%H%M%S.%f')
                #                              + f'|blocknum predicted|{block_num_pred}')

            for b in range(prev_block_number, block_num):
                block_to_proc = b + 1
                # insert new block to process
                with self.block_list_lock:
                    self.block_list.append({
                        'block_num': block_to_proc,
                        'time_to_process': time.time(),
                        'recursion_cnt': 0
                    })
                # self.worker_result_queue.put('DBGLOG' + datetime.datetime.now().strftime('%H%M%S.%f')
                #                              + f'|blocks into queue |{block_to_proc}')

                prev_block_number = block_to_proc
                last_block_ts = curr_time

            time.sleep(1)

    # infinite loop to handle pending and mined block transactions
    # open new thread for each transaction_hash to get the actual transaction
    def poll_transactions(self, data=None, keepalive=False, skip_multithreading=False):
        start_time = time.time()
        is_realtime = True

        if data and isinstance(data, list):
            block_num_inc = 1
            is_realtime = False
            list_of_blocks = None
            if len(data) > 2:
                list_of_blocks = data
                block_num = 0
                end_block = len(data)
            else:
                block_num = data[0]
                end_block = data[0]+1
                if len(data) > 1:
                    if data[0] < data[1]:
                        block_num = data[0]
                        end_block = data[1]+1

                        if 0 in data:
                            # reverse
                            block_num_inc = -1
                            block_num = data[0] if data[0] != 0 else data[1]
                            end_block = 0
                    else:
                        end_block = data[1]+1
        else:
            # start block number getter
            th = mp.Process(target=self.poll_block_num)
            th.start()

        while not self.mp_exit_main_loop.value:
            # process new block tx hashes
            loop_start_time = time.time()
            try:
                # get current block number
                bs_to_rm = []
                for b in self.block_list:
                    b_num = b['block_num']
                    b_time = b['time_to_process']
                    b_rec = b['recursion_cnt']

                    if b_time < time.time():
                        worker_idx = self.get_free_worker_idx(FilterEntryType.NEW_BLOCK_TRANSACTION)
                        if worker_idx < 0:
                            self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                                         + f'ERROR: poll_transactions() no free worker for block #{b_num}')
                        else:
                            # self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                            #                              + f'|start get_block_transactions({b_num}) with worker #{worker_idx} len={len(self.block_list)}')
                            if 1:
                                th = mp.Process(target=self.get_block_transactions,
                                                args=(b_num,
                                                    self.workers[worker_idx]['w3'],
                                                    b_rec,))
                                with self.workers_lock:
                                    self.workers[worker_idx]['thread'] = th
                                    th.start()
                            else:
                                self.get_block_transactions(b_num, self.workers[worker_idx]['w3'], b_rec)

                        bs_to_rm.append(b)
                for b_to_rm in bs_to_rm:
                    # remove from list
                    with self.block_list_lock:
                        self.block_list.remove(b_to_rm)

                if not is_realtime:
                    # push through blocks
                    if block_num * block_num_inc >= end_block:
                        # self.worker_result_queue.put('DBGLOG' + datetime.datetime.now().strftime("%H:%M:%S.%f")
                        #                              + '|___DONE___')
                        # time.sleep(1)
                        # self.mp_exit_main_loop.value = True
                        break
                    else:
                        stop_cnt_2_wait = 50
                        if self._NETWORK_ == Network.FANTOM:
                            stop_cnt_2_wait = 150
                        process_this_block = block_num
                        if list_of_blocks:
                            process_this_block = list_of_blocks[block_num]
                            self.worker_result_queue.put('DBGLOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                                         + f' {100 * block_num / len(list_of_blocks):.2f}' + '%')
                        elif not block_num % stop_cnt_2_wait:
                            self.wait_all_th_finish()
                            if block_num_inc > 0:
                                self.worker_result_queue.put('DBGLOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                                            + f' {100 * (block_num-data[0]) / (end_block-data[0]):.2f}' + '%')
                            else:
                                self.worker_result_queue.put('DBGLOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                                            + f' status {block_num}')
                        # push into free worker
                        with self.workers_lock:
                            worker_idx = self.get_free_worker_idx(FilterEntryType.NEW_BLOCK_TRANSACTION)
                            if worker_idx < 0:
                                logging.error('no free worker for BLOCK #' + str(process_this_block))
                            else:
                                if skip_multithreading:
                                    # skip multiple threading
                                    self.wait_all_th_finish()
                                    self.get_block_transactions(process_this_block, self.workers[worker_idx]['w3'])
                                    self.wait_all_th_finish()
                                else:
                                    th = mp.Process(target=self.get_block_transactions,
                                                    args=(process_this_block, self.workers[worker_idx]['w3'],))
                                    # start thread
                                    th.start()
                                    # assign into self list
                                    self.workers[worker_idx]['thread'] = th

                        # tune poll_interval to max out 33 request / sec (binance RPC limit)
                        if self._NETWORK_ == Network.MATIC:
                            self.tune_poll_interval(40, start_time)
                        elif self._NETWORK_ == Network.FANTOM:
                            self.tune_poll_interval(0, start_time)
                        else:
                            self.tune_poll_interval(30, start_time)
                    block_num += block_num_inc
            except:  # catch *all* exceptions
                e = sys.exc_info()[0]
                print(traceback.format_exc())
                traceback.print_exc()
                self.worker_result_queue.put('LOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                    + f'|ERROR: exception in poll_transactions() {block_num} {e.__name__} {e.__doc__}')
                time.sleep(1.0)

            # process new pending tx hashes
            if not self._SKIP_PENDINGS_:
                is_any_ongoing_trading = False
                for is_running in self.trading_details['is_running']:
                    if is_running:
                        is_any_ongoing_trading = True
                        break
                for event in self.event_filter_pending.get_new_entries():
                    tx = event.hex()
                    if not is_any_ongoing_trading:
                        # process if trading is not running
                        self.event_cnt[int(FilterEntryType.PENDING)] += 1
                        # put tx hashes into queue with current timestamp
                        self.worker_tx_queue.put([tx, time.time(), FilterEntryType.PENDING])

            # start new workers with received tx hashes
            self.start_worker()

            # read result queue
            self.handle_worker_result_queue()

            # 5sec log
            if 0 == (int(time.time()) - int(start_time)) % 5:
                if 0:
                    end_time = time.time()
                    pending_tx_per_sec = self.event_cnt[int(FilterEntryType.PENDING)] / (end_time - start_time)
                    block_tx_per_sec = self.event_cnt[int(FilterEntryType.NEW_BLOCK_HASH)] / (end_time - start_time)
                    print('block=', int(block_tx_per_sec), ', pending=', int(pending_tx_per_sec), 'tx/sec')
                elif 0:
                    # ongoing threads vs all web3 endpoint
                    th_stat = ''
                    for i, w in enumerate(self.workers):
                        if not w['thread'].is_alive():
                            th_stat += '-'
                        else:
                            th_stat += 'x'
                    logging.info(th_stat)
                elif 0:
                    # ongoing threads vs all web3 endpoint in %
                    used_cnt = [0, 0]
                    for i, w in enumerate(self.workers):
                        if w['thread'].is_alive():
                            if i >= self.number_of_pending_workers:
                                used_cnt[int(FilterEntryType.NEW_BLOCK_HASH)] += 1
                            else:
                                used_cnt[int(FilterEntryType.PENDING)] += 1
                    all_pending_worker = self.number_of_pending_workers
                    all_block_worker = self.workers_max - self.number_of_pending_workers
                    if all_pending_worker:
                        free_worker_pending_str = str(100 * used_cnt[int(FilterEntryType.PENDING)] / all_pending_worker)
                    else:
                        free_worker_pending_str = '-'
                    free_worker_block_str = str(100 * used_cnt[int(FilterEntryType.NEW_BLOCK_HASH)] / all_block_worker)
                    msg = free_worker_block_str + '% block,' + free_worker_pending_str + '% pending worker used'
                    self.worker_result_queue.put('DBGLOG' + datetime.datetime.now().strftime("%H:%M:%S.%f")
                                                 + '|' + msg)

            # main loop sleep
            dt = time.time() - loop_start_time
            sleep_time = self.poll_interval.value - dt 
            if sleep_time > 0:
                time.sleep(sleep_time)

        self.wait_all_th_finish()
        while keepalive or (not is_realtime):
            self.handle_worker_result_queue()
            time.sleep(1)

    def push_through_tx(self, tx):
        self.worker_tx_queue.put([tx, time.time(), FilterEntryType.NEW_BLOCK_HASH])
        self.wait_for_free_block_worker()

    def push_through_transaction(self, transaction):
        self.worker_tx_queue.put([transaction, time.time(), FilterEntryType.NEW_BLOCK_TRANSACTION])
        self.wait_for_free_block_worker()

    def wait_for_free_block_worker(self):
        free_worker_found = False
        while not free_worker_found:
            worker_idx_start = self.number_of_pending_workers
            worker_idx_end = self.workers_max
            for i in range(worker_idx_start, worker_idx_end):
                if not self.workers[i]['thread'].is_alive():
                    # free worker found, start it
                    self.start_worker()
                    free_worker_found = True
                    break
            if not free_worker_found:
                time.sleep(0.05)

    def wait_all_th_finish(self, max_wait=60):
        all_worker_free = False
        t0 = time.time()
        while not all_worker_free:
            if max_wait and time.time() > t0 + max_wait:
                # kill all ongoing process
                self.worker_result_queue.put('DBGLOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                             + '|ERROR wait_all_th_finish() timeout kill ongoing processes')
                for i, w in enumerate(self.workers):
                    if w['thread'] and w['thread'].is_alive():
                        w['thread'].terminate()
                        w['thread'] = None
                        self.worker_result_queue.put('DBGLOG' + datetime.datetime.now().strftime("%H%M%S.%f")
                                                     + f'|ERROR wait_all_th_finish() process {i} terminated')
                break

            all_worker_free = True
            for i, w in enumerate(self.workers):
                if w['thread'] and w['thread'].is_alive():
                    all_worker_free = False
            # read result queue
            self.start_worker()
            self.handle_worker_result_queue()
            time.sleep(0.1)

    def manual_push_through(self, data, data_type='account'):
        start_time = time.time()
        if isinstance(data, list):
            blocks = data
            start_block = blocks[0]
            end_block = start_block
            if len(blocks) > 1:
                # should be reverse order
                if blocks[0] > blocks[1]:
                    start_block = blocks[1]
                    end_block = blocks[0]
                else:
                    end_block = blocks[1]
            for bnum in reversed(range(start_block, end_block + 1)):
                # get block
                while 1:
                    try:
                        b = self.w3_get_block.eth.get_block(bnum, full_transactions=True)
                        self.event_cnt[int(FilterEntryType.NEW_BLOCK)] += 1
                        break
                    except:
                        e = sys.exc_info()[0]
                        print('get_block failed for', bnum, ', get some sleep and try again',
                              e.__name__, e.__doc__.replace('\n', ''))
                        time.sleep(10)

                # presale stuff
                self.presale_process(b)

                # progress bar
                block_per_sec = self.event_cnt[int(FilterEntryType.NEW_BLOCK)] / (time.time() - start_time)
                print('\r', end='')
                print('block number', bnum, ', ', f'{block_per_sec:.2f}', 'block/sec ', end='')

                self.handle_worker_result_queue()
        elif data_type == 'single':
            self.push_through_tx(data)
            self.handle_worker_result_queue()
        elif isinstance(data, str):
            # get all transaction of specific address from bscscan
            addr = data
            explorer = self.db_handler.get_network_explorer(self._NETWORK_)
            bscscan_apikey = self.data_json['private_data'][explorer]['apikey']
            bscscan_abi_req = 'https://api.' \
                              + explorer.split('https://')[1] \
                              +'/api?module=account&action=txlist&address=' + addr + \
                              '&startblock=1&endblock=99999999&sort=asc' +\
                              '&apikey=' + bscscan_apikey
            bscscan_response = requests.get(bscscan_abi_req).json()
            if bscscan_response['message'] == 'OK':
                for transaction in bscscan_response['result']:
                    tx = transaction['hash']
                    # self.push_through_tx(tx)
                    transaction = self.w3.eth.get_transaction(tx)
                    self.push_through_transaction(transaction)
                    self.start_worker()
                    self.handle_worker_result_queue()

        self.wait_all_th_finish()


def main():
    # main
    bsc_listener = Web3BSC()

    ## process single block
    # bsc_listener_th = Thread(target=bsc_listener.manual_push_through, args=([10173314,],))

    ## process block range
    # bsc_listener_th = Thread(target=bsc_listener.manual_push_through, args=([10200000, 10362808],))
    
    ## get missed block list from previous log
    #with open('./log/web3bsc_20220708_205504.609066_BSC.log', 'r') as f:
    #    block_list = re.findall(r"([0-9]{7,8})(?=\) missed block)", f.read())
    #    block_list = [int(b.strip()) for b in block_list]
    
    ## real process
    ths=[]
    # ths.append(Thread(target=bsc_listener.poll_transactions, args=([19452859, bsc_listener.w3.eth.block_number], False,)))
    # ths.append(Thread(target=bsc_listener.poll_transactions, args=([19357312, 19380447], False,)))
    # ths.append(Thread(target=bsc_listener.poll_transactions, args=(block_list, False,)))
    # ths.append(Thread(target=bsc_listener.poll_transactions, args=([17525931], True,)))
    ths.append(Thread(target=bsc_listener.poll_transactions))

    t0 = time.time()
    for th in ths:
        th.start()
    for th in ths:
        th.join()
        
    print('runtime = ', time.time() - t0)


if __name__ == '__main__':
    main()
