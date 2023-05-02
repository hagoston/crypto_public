import sqlite3 as sl
import os
import sys
import re
import pandas as pd
import time
from enum import IntEnum
sys.path.append('../')
from directWeb3 import DirectWeb3, BSC_INFO
import threading


class Network(IntEnum):
    BSC = 1,
    ETH = 2,
    MATIC = 3,
    BSC_TESTNET = 4,
    FANTOM = 5,
    AVAX = 6


class RiskStatus(IntEnum):
    NO_RISK = 1,
    RISK_DETECTED = 2,
    RISK_NOT_SURE = 3,
    SOURCE_CODE_AVAILABLE = 4,
    DONE = 5,
    PUBLIC_SETDIVIDENDTOKENADDRESS = 6,
    IMMUTABLE_WRONG_DIVIDEND_TOKEN = 7,
    FIXABLE_WRONG_DIVIDEND_TOKEN = 8,
    BNB_DIVIDEND_WITH_WRONG_TRANSFER_FUNCTION = 9,
    DIFFERENT_DIVIDEND_TRACKER = 10,
    TRADING_DISABLED_OR_ZERO_FEE = 11,
    CONTRACT_EXCEPTION = 12,
    OTHER_PROBLEM = 13,
    ONLY_OWNER_DISTRIBUTE_FUNCTION = 14,
    PAYOUT_DETECTED = 15,

    LAST_ELEMENT = 16


class DBHandler:
    def __init__(self, db_file, network_id=Network.BSC):
        create_db = False
        if not os.path.isfile(db_file):
            create_db = True
        self.conn = sl.connect(db_file, check_same_thread=False)
        self.conn_lock = threading.Lock()
        self.risk_status_list = [
            (RiskStatus.NO_RISK, 'no risk', 1),
            (RiskStatus.RISK_DETECTED, 'risk detected', 0),
            (RiskStatus.RISK_NOT_SURE, 'risk not sure', 0),
            (RiskStatus.SOURCE_CODE_AVAILABLE, 'source code available', 0),
            (RiskStatus.DONE, 'done', 0),
            (RiskStatus.PUBLIC_SETDIVIDENDTOKENADDRESS, 'public setDividendTokenAddress', 0),
            (RiskStatus.IMMUTABLE_WRONG_DIVIDEND_TOKEN, 'immutable wrong dividend token', 1),
            (RiskStatus.FIXABLE_WRONG_DIVIDEND_TOKEN, 'fixable wrong dividend token', 0),
            (RiskStatus.BNB_DIVIDEND_WITH_WRONG_TRANSFER_FUNCTION, 'BNB dividend with wrong transfer function', 1),
            (RiskStatus.DIFFERENT_DIVIDEND_TRACKER, 'different dividend tracker', 1),
            (RiskStatus.TRADING_DISABLED_OR_ZERO_FEE, 'trading disabled or zero fee', 1),
            (RiskStatus.CONTRACT_EXCEPTION, 'contract exception', 1),
            (RiskStatus.OTHER_PROBLEM, 'other problem', 1),
            (RiskStatus.ONLY_OWNER_DISTRIBUTE_FUNCTION, 'only owner distribute function', 1),
            (RiskStatus.PAYOUT_DETECTED, 'payout detected', 0)
        ]
        if create_db:
            self.create_db()

        dex_info = self.get_dex_info(network_id)[0]  # todo could be more
        dex_info['base_token_address'] = self.get_network_base_token_address(network_id)
        dex_info['rpc'] = self.get_network_rpc(network_id)
        self.dw3 = DirectWeb3(dex_info)

    def create_db(self):
        with self.conn_lock:
            cur = self.conn.cursor()

            # create network type table
            #   type of crypto network
            cur.execute('''
                CREATE TABLE network (
                    network_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    explorer TEXT,
                    rpc TEXT,
                    chain_id INTEGER,
                    base_token_address TEXT,
                    usd_token_address TEXT
                );
            ''')
            sql = 'INSERT INTO network (network_id, name, explorer, rpc, chain_id, base_token_address, usd_token_address) values(?, ?, ?, ?, ?, ?, ?)'
            data = [
                (1, BSC_INFO['name'],       BSC_INFO['explorer'],            BSC_INFO['rpc'],                              BSC_INFO['chain_id'],               BSC_INFO['base_token_address'],                BSC_INFO['usd_token_address']),
                (2, 'ETH',                  'https://etherscan.io',         'https://mainnet.infura.io/v3/9aa3d95b3bc440fa88ea12eaa4456161',  1, '0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2', '0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48'),
                (3, 'MATIC',                'https://polygonscan.com',      'https://polygon-rpc.com',                                      137, '0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270', '0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174'),
                (4, 'BSC_TESTNET',          'https://testnet.bscscan.com',  'https://data-seed-prebsc-1-s1.binance.org:8545',                97, '0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd', '0x337610d27c682e347c9cd60bd4b3b107c9d34ddd'),
                (5, 'FANTOM',               'https://ftmscan.com',          'https://rpc.ftm.tools',                                        250, '0x21be370D5312f44cB42ce377BC9b8a0cEF1A4C83', '0x04068DA6C83AFCFA0e13ba15A6696662335D5B75'),
                (6, 'AVAX',                 'https://snowtrace.io',         'https://api.avax.network/ext/bc/C/rpc',                      43114, '0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7', '0xc7198437980c041c805A1EDcbA50c1Ce5db95118')
            ]
            cur.executemany(sql, data)

            # create table for DEXs
            cur.execute('''
                CREATE TABLE dex (
                    dex_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    router_address TEXT,
                    factory_address TEXT,
                    hexadem TEXT,
                    FK_network_id INTEGER,
                    FOREIGN KEY(FK_network_id) REFERENCES network(network_id)
                );
            ''')
            # https://docs.spookyswap.finance/contracts-1/contracts
            sql = 'INSERT INTO dex (dex_id, name, router_address, factory_address, hexadem, FK_network_id) values(?, ?, ?, ?, ?, ?)'
            data = [
                (1, BSC_INFO['router_name'],                          BSC_INFO['router_address'],                  BSC_INFO['factory_address'],                                                  BSC_INFO['hexadem'], 1),
                (2, 'UniswapV2',                    '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D', '0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f', '0x96e8ac4277198ff8b6f785478aa9a39f403cb768dd02cbee326c3e7da348845f', 2),
                (3, 'QuickSwap',                    '0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff', '0x5757371414417b8C6CAad45bAeF941aBc7d3Ab32', '0x96e8ac4277198ff8b6f785478aa9a39f403cb768dd02cbee326c3e7da348845f', 3),
                (4, 'PancakeSwap_testnet',          '0xD99D1c33F9fC3444f8101754aBC46c52416550D1', '0x6725F303b657a9451d8BA641348b6761A6CC7a17', '0x00fb7f630766e6a796048ea87d01acd3068e8ff67d078148a3fa3f4a84f69bd5', 4),
                (5, 'SpookySwap',                   '0xF491e7B69E4244ad4002BC14e878a34207E38c29', '0x152eE697f2E276fA89E96742e9bB9aB1F2E61bE3', '0xcdf2deca40a0bd56de8e3ce5c7df6727e5b1bf2ac96f283fa9c4b3e6b42ea9d2', 5),
                (6, 'TraderJoe',                    '0x60aE616a2155Ee3d9A68541Ba4544862310933d4', '0x9Ad6C38BE94206cA50bb0d90783181662f0Cfa10', '0x0bbca9af0511ad1a1da383135cf3a8d2ac620e549ef9f6ae3a4c33c2fed0af91', 6)
            ]
            cur.executemany(sql, data)

            # create currency table
            #   table to store token price with token details
            #   last_value_update - could be use to control price update
            cur.execute('''
                CREATE TABLE currency (
                    currency_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    address TEXT,
                    decimals INTEGER,
                    name TEXT,
                    symbol TEXT,
                    usd_value REAL,
                    last_value_update INTEGER,
                    fake INTEGER
                );
            ''')

            # reward_token table
            #   main reward contract info
            cur.execute('''
                CREATE TABLE reward_token (
                    reward_token_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    address TEXT,
                    block INTEGER,
                    name TEXT,
                    note TEXT,
                    FK_network_id INTEGER,
                    FOREIGN KEY(FK_network_id) REFERENCES network(network_id)
                );
            ''')

            # dividend_token table
            #   reward contract's dividend contract storage
            cur.execute('''
                CREATE TABLE dividend_token (
                    dividend_token_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    address TEXT,
                    FK_reward_token_id INTEGER,
                    distribute_function TEXT,
                    price REAL,
                    FK_currency_id INTEGER, 
                    note TEXT,
                    last_value_update INTEGER,
                    FOREIGN KEY(FK_reward_token_id) REFERENCES reward_token(reward_token_id),
                    FOREIGN KEY(FK_currency_id) REFERENCES currency(currency_id)
                );
            ''')

            # create risk type table (web3bsc.reward_token_status)
            cur.execute('''
                CREATE TABLE risk_status (
                    risk_status_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    description TEXT,
                    showstopper INTEGER
                );
            ''')
            sql = 'INSERT INTO risk_status (risk_status_id, description, showstopper) values(?, ?, ?)'
            cur.executemany(sql, self.risk_status_list)

            # risk table
            #   dividend contract's vulnerabilities
            cur.execute('''
                CREATE TABLE risk (
                    risk_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    FK_dividend_token_id INTEGER,
                    FK_risk_status_id INTEGER,
                    FOREIGN KEY(FK_dividend_token_id) REFERENCES dividend_token(dividend_token_id)
                    FOREIGN KEY(FK_risk_status_id) REFERENCES risk_status(risk_status_id)
                );
            ''')

            # wallet token holdings
            #   storing given address token (= currency) holdings
            cur.execute('''
                CREATE TABLE wallet_holdings (
                    wallet_holdings_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    address TEXT,
                    FK_currency_id INTEGER,
                    last_value_update INTEGER,
                    FOREIGN KEY(FK_currency_id) REFERENCES currency(currency_id)
                );
            ''')
            self.conn.commit()

    def clear_risk_status_for_dividend(self, dividend_token_id, risk_status_ids=None):
        '''
            risk_id,
            FK_dividend_token_id INTEGER,
            FK_risk_status_id INTEGER,
        '''
        with self.conn_lock:
            c = self.conn.cursor()
            if risk_status_ids is None:
                c.execute('DELETE FROM risk '
                          'WHERE FK_dividend_token_id=:dividend_token_id',
                          {'dividend_token_id': dividend_token_id})
            else:
                try:
                    iter(risk_status_ids)
                except TypeError:
                    risk_status_ids = [risk_status_ids]
                for risk_status_id in risk_status_ids:
                    if RiskStatus.LAST_ELEMENT <= risk_status_id:
                        return -1
                    c.execute('DELETE FROM risk '
                              'WHERE FK_dividend_token_id=:dividend_token_id '
                              'AND FK_risk_status_id=:risk_status_id',
                              {'dividend_token_id': dividend_token_id,
                               'risk_status_id': risk_status_id})
            self.conn.commit()
            return []

    def set_risk_status(self,
                                 dividend_token_id,
                                 risk_status_id):
        '''
            risk_id,
            FK_dividend_token_id INTEGER,
            FK_risk_status_id INTEGER,
        '''
        with self.conn_lock:
            if RiskStatus.LAST_ELEMENT <= risk_status_id:
                return -1

            c = self.conn.cursor()
            c.execute('SELECT risk_id FROM risk '
                      'WHERE FK_dividend_token_id=:dividend_token_id '
                      'AND FK_risk_status_id=:risk_status_id',
                      {'dividend_token_id': dividend_token_id,
                       'risk_status_id': risk_status_id})
            div = c.fetchone()
            if div:
                # already set, return with risk_id
                return div[0]
            c.execute('INSERT INTO risk (FK_dividend_token_id, FK_risk_status_id) VALUES (?,?)',
                      (dividend_token_id, risk_status_id))
            self.conn.commit()
            return c.lastrowid

    def insert_into_dividend_token_table(self,
                                         address,
                                         reward_token_id,
                                         distribute_function,
                                         price,
                                         currency_id,
                                         note=None,
                                         update=False):
        '''
            dividend_token_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            address TEXT,
            FK_reward_token_id INTEGER,
            distribute_function TEXT,
            price REAL,
            FK_currency_id INTEGER,
            note TEXT,
            last_value_update INTEGER
        '''
        c = self.conn.cursor()
        c.execute('SELECT * FROM dividend_token WHERE address=:addr', {'addr': address})
        div = c.fetchone()
        if div:
            # already inserted, return with dividend_token_id
            dividend_token_id = div[0]
            if update:
                self.update_dividend_token_table(dividend_token_id, price, currency_id, distribute_function)
            return dividend_token_id
        with self.conn_lock:
            last_value_update = int(time.time())
            c.execute('INSERT INTO dividend_token (address,FK_reward_token_id,distribute_function,price,FK_currency_id,note,last_value_update) VALUES (?,?,?,?,?,?,?)',
                      (address, reward_token_id, distribute_function, price, currency_id, note, last_value_update))
            self.conn.commit()
            return c.lastrowid

    def update_dividend_token_table(self, dividend_token_id, price, currency_id, distribute_function=None):
        with self.conn_lock:
            c = self.conn.cursor()
            c.execute('''UPDATE dividend_token 
                         SET price=:price 
                         WHERE dividend_token_id=:dividend_token_id''',
                      {'price': price,
                       'dividend_token_id': dividend_token_id})
            c.execute('''UPDATE dividend_token 
                         SET FK_currency_id=:FK_currency_id 
                         WHERE dividend_token_id=:dividend_token_id''',
                      {'FK_currency_id': currency_id,
                       'dividend_token_id': dividend_token_id})
            if distribute_function is not None:
                c.execute('''UPDATE dividend_token 
                             SET distribute_function=:distribute_function 
                             WHERE dividend_token_id=:dividend_token_id''',
                          {'distribute_function': distribute_function,
                           'dividend_token_id': dividend_token_id})
            # update time
            last_value_update = int(time.time())
            c.execute('''UPDATE dividend_token 
                         SET last_value_update=:last_value_update 
                         WHERE dividend_token_id=:dividend_token_id''',
                      {'last_value_update': last_value_update,
                       'dividend_token_id': dividend_token_id})
            self.conn.commit()
            c.execute('SELECT * FROM dividend_token WHERE dividend_token_id=:dividend_token_id',
                      {'dividend_token_id': dividend_token_id})
            return c.fetchone()

    def get_network_info(self, network_id):
        c = self.conn.cursor()
        c.execute('SELECT * FROM dex WHERE FK_network_id=:id', {'id': network_id})
        result = c.fetchall()
        retval = []
        for dex in result:
            retval.append({
                'name': dex[1],
                'router_address': dex[2],
                'factory_address': dex[3],
                'hexadem': dex[4]
            })
        retval = retval[0]
        retval['router_name'] = retval.pop('name')
        retval['rpc'] = self.get_network_rpc(network_id)
        retval['base_token_address'] = self.get_network_base_token_address(network_id)
        retval['usd_token_address'] = self.get_network_usd_token_address(network_id)
        retval['chain_id'] = self.get_network_chain_id(network_id)
        return retval

    def get_dex_info(self, network_id):
        c = self.conn.cursor()
        c.execute('SELECT * FROM dex WHERE FK_network_id=:id', {'id': network_id})
        result = c.fetchall()
        retval = []
        for dex in result:
            retval.append({
                'name': dex[1],
                'router_address': dex[2],
                'factory_address': dex[3],
                'hexadem': dex[4]
            })
        return retval

    def get_network_explorer(self, network_id):
        c = self.conn.cursor()
        c.execute('SELECT explorer FROM network WHERE network_id=:id', {'id': network_id})
        return c.fetchone()[0]

    def get_network_rpc(self, network_id):
        c = self.conn.cursor()
        c.execute('SELECT rpc FROM network WHERE network_id=:id', {'id': network_id})
        return c.fetchone()[0]

    def get_network_name(self, network_id):
        c = self.conn.cursor()
        c.execute('SELECT name FROM network WHERE network_id=:id', {'id': network_id})
        return c.fetchone()[0]

    def get_network_base_token_address(self, network_id):
        c = self.conn.cursor()
        c.execute('SELECT base_token_address FROM network WHERE network_id=:id', {'id': network_id})
        return c.fetchone()[0]

    def get_network_chain_id(self, network_id):
        c = self.conn.cursor()
        c.execute('SELECT chain_id FROM network WHERE network_id=:id', {'id': network_id})
        return c.fetchone()[0]

    def get_network_usd_token_address(self, network_id):
        c = self.conn.cursor()
        c.execute('SELECT usd_token_address FROM network WHERE network_id=:id', {'id': network_id})
        return c.fetchone()[0]

    def get_max_block_number(self):
        c = self.conn.cursor()
        c.execute('SELECT MAX(block) FROM reward_token')
        result = c.fetchone()
        return result[0]

    def get_dividend_token_ids_with_risk_status_ids(self):
        c = self.conn.cursor()
        c.execute('''SELECT
                        FK_dividend_token_id AS dividend_token_id, 
                        group_concat(FK_risk_status_id) AS risk_status_ids 
                     FROM 
                        risk 
                     GROUP BY FK_dividend_token_id''')
        result = c.fetchall()
        return result

    def get_dividend_token(self, dividend_token_id):
        c = self.conn.cursor()
        c.execute('SELECT * FROM dividend_token WHERE dividend_token_id=:id', {'id': dividend_token_id})
        return c.fetchone()

    def get_dividend_token_ids(self, reward_token_id):
        c = self.conn.cursor()
        c.execute('SELECT * FROM dividend_token WHERE FK_reward_token_id=:id', {'id': reward_token_id})
        return c.fetchall()

    def get_risk_status_ids(self, dividend_token_id):
        c = self.conn.cursor()
        c.execute('SELECT FK_risk_status_id FROM risk WHERE FK_dividend_token_id=:id', {'id': dividend_token_id})
        result = c.fetchall()
        return [int(vid[0]) for vid in result]

    def get_reward_token(self, reward_token_id):
        c = self.conn.cursor()
        c.execute('SELECT * FROM reward_token WHERE reward_token_id=:id', {'id': reward_token_id})
        return c.fetchone()

    def get_reward_token_id(self, reward_token_addr):
        c = self.conn.cursor()
        c.execute('SELECT reward_token_id FROM reward_token WHERE address=:addr', {'addr': reward_token_addr})
        result = c.fetchone()
        if result:
            return result[0]
        return None

    def get_reward_token_blocks(self):
        c = self.conn.cursor()
        c.execute('SELECT block FROM reward_token')
        result = c.fetchall()
        if not result:
            return []
        return [int(b[0]) for b in result]

    def get_showstopper_ids(self):
        c = self.conn.cursor()
        c.execute('SELECT risk_status_id FROM risk_status WHERE showstopper')
        result = c.fetchall()
        return [int(sid[0]) for sid in result]

    def insert_into_reward_token_table(self, block, token_addr, token_name, network_id):
        '''
            reward_token_id
            address TEXT,
            block INTEGER,
            name TEXT,
            note TEXT,
            FK_network_id INTEGER,
        '''
        with self.conn_lock:
            c = self.conn.cursor()

            c.execute('SELECT reward_token_id FROM reward_token WHERE address=:addr', {'addr': token_addr})
            result = c.fetchone()
            if result:
                # already inserted, return with id
                return result[0]

            c.execute('INSERT INTO reward_token (address, block,name,FK_network_id) VALUES (?,?,?,?)',
                      (token_addr, block, token_name, network_id))
            self.conn.commit()
            return c.lastrowid

    def get_currency(self, address):
        c = self.conn.cursor()
        c.execute('SELECT * FROM currency WHERE address=:addr', {'addr': address})
        return c.fetchone()

    def remove_all_wallet_holdings_table(self, address):
        '''
            wallet_holdings_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            address TEXT,
            FK_currency_id INTEGER,
            last_value_update INTEGER
        '''
        with self.conn_lock:
            c = self.conn.cursor()
            c.execute('DELETE FROM wallet_holdings '
                      'WHERE address=:address', {'address': address})
            self.conn.commit()
            return c.lastrowid

    def insert_into_wallet_holdings_table(self, address, currency_id_list=None):
        '''
            wallet_holdings_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            address TEXT,
            FK_currency_id INTEGER,
            last_value_update INTEGER
        '''
        with self.conn_lock:
            c = self.conn.cursor()
            last_value_update = int(time.time())
            if not isinstance(currency_id_list, list):
                currency_id_list = [currency_id_list]
            for cid in currency_id_list:
                c.execute('INSERT INTO wallet_holdings (address,FK_currency_id,last_value_update) VALUES (?,?,?)',
                          (address, cid, last_value_update))
            self.conn.commit()
            return c.lastrowid

    def get_wallet_holding_addresses(self, address):
        '''
            wallet_holdings_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            address TEXT,
            FK_currency_id INTEGER,
            last_value_update INTEGER
        '''
        c = self.conn.cursor()
        c.execute('SELECT FK_currency_id, last_value_update FROM wallet_holdings WHERE address=:addr', {'addr': address})
        currency_ids = c.fetchall()
        wallet_token_list = None
        last_value_update = None
        if currency_ids:
            wallet_token_list = []
            for cid, lvu in currency_ids:
                if cid is not None:
                    c.execute('SELECT address FROM currency WHERE currency_id=:cid', {'cid': cid})
                    cadd = c.fetchone()
                    if cadd:
                        wallet_token_list.append(cadd[0])
                if not last_value_update or last_value_update > lvu:
                    last_value_update = lvu
        return wallet_token_list, last_value_update

    def update_currency_price(self, currency_id, usd_value):
        with self.conn_lock:
            c = self.conn.cursor()
            last_value_update = int(time.time())
            c.execute('''UPDATE currency 
                         SET usd_value=:usd_value, 
                             last_value_update=:last_value_update 
                         WHERE currency_id=:currency_id''',
                      {'usd_value': usd_value,
                       'currency_id': currency_id,
                       'last_value_update': last_value_update})
            self.conn.commit()
            c.execute('SELECT * FROM currency WHERE currency_id=:currency_id', {'currency_id': currency_id})
            return c.fetchone()

    def insert_into_currency_table(self, address, decimals, name, symbol, usd_value=None, fake=False):
        '''
            currency_id,
            address TEXT,
            decimals INTEGER,
            name TEXT,
            symbol TEXT,
            usd_value REAL,
            last_value_update INTEGER,
            fake INTEGER
        '''
        curr = self.get_currency(address)
        with self.conn_lock:
            if curr:
                # already inserted, return with currency_id
                return curr[0]

            c = self.conn.cursor()
            if usd_value is None:
                usd_value = 0.0
            last_value_update = int(time.time())

            # fake list check
            is_fake = fake
            if '.io' in name.lower() or \
                    '.org' in name.lower() or \
                    '.net' in name.lower():
                is_fake = True
            c.execute('INSERT INTO currency (address,decimals,name,symbol,usd_value,last_value_update,fake) VALUES (?,?,?,?,?,?,?)',
                      (address, decimals, name, symbol, usd_value, last_value_update, is_fake))
            self.conn.commit()
            return c.lastrowid

    def fill_db_from_file(self, ifile):
        # load file
        df = pd.read_csv(ifile,
                         delimiter=';',
                         header=None,
                         index_col=False,
                         names=['status', 'status_str', 'block', 'contract_addr', 'balance', 'dividend_addr',
                                'src_str'],
                         dtype={'status': int,
                                'status_str': str,
                                'block': int,
                                'contract_addr': str,
                                'balance': str,
                                'dividend_addr': str,
                                'src_str': str})
        df = df.iloc[:, :-1]
        df = df.dropna()
        # strip contract address
        df.iloc[:, 3] = df.iloc[:, 3].str.strip()
        df.iloc[:, 2] = df.iloc[:, 2].astype(int)
        df = df.sort_values(by=df.columns[2], ascending=True)

        c = self.conn.cursor()
        # get BSCC network_id
        c.execute('SELECT * FROM network WHERE name="BSC"')
        network_id = c.fetchone()[0]

        for index, row in df.iterrows():

            # reward token table
            block = int(row.block)
            token_addr = re.findall(r"(?:[0][x][a-fA-F0-9]{40})", row.contract_addr)[0]
            token_name = self.dw3.name(contract_addr=token_addr)

            c.execute('INSERT INTO reward_token (block,token_addr,name,FK_network_id) VALUES (?,?,?,?)',
                      (block, token_addr, token_name, network_id))
            reward_token_id = c.lastrowid

            # dividend token table
            FK_reward_token_id = reward_token_id
            distribute_function = re.findall(r"(?<=function)(.*)(?=amount)", row.src_str)[0].strip() + ')'
            '''
            CREATE TABLE dividend_token (
                dividend_token_id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                FK_reward_token_id INTEGER,
                distribute_function TEXT,
                price REAL,
                note TEXT,
                FOREIGN KEY(FK_reward_token_id) REFERENCES reward_token(reward_token_id)
            );
            '''

        # # write result
        # df.to_csv(ifile + '_mod.txt', index=False, quoting=csv.QUOTE_NONE, sep=';', quotechar='', header=False)

        self.conn.commit()


def main():
    dbfile = 'dividend_token.db'
    # rm prev file
    try:
        os.remove(dbfile)
    except OSError:
        pass
    db = DBHandler(dbfile)
    db.create_db()
    db.fill_db_from_file('token_search_result-test.txt')


if __name__ == '__main__':
    main()
