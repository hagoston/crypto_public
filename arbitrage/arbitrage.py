import time
import requests
from pyvis.network import Network
from web3 import Web3
from web3.middleware import geth_poa_middleware
import networkx as nx
import pandas as pd
import numpy as np
import sys
from scipy.optimize import minimize_scalar
sys.path.append('../shitcoin/MysTrader/src')
from web3bsc import Web3BSC
from directWeb3 import DirectWeb3
import logging


class ArbOpt():
    def __init__(self):
        self.dw3 = DirectWeb3()
        self.swap_list = []

    def objective(self, initial_investment):
        # call swap calculation
        amounts = self.dw3.get_swap_amounts_out(initial_investment, self.swap_list)
        # get profit
        profit = amounts[-1] - amounts[0]
        # maximize profit == minimize loss
        return -profit


class BSCArb():
    def __init__(self):
        # main web3bsc class
        self.web3bsc = Web3BSC(barebone_init=True)
        # direct bsc calls for specific functions without web3 overhead
        self.dw3 = DirectWeb3()
        # arbitrage with optimization - find out maximum profit for a given arbitrage chain
        self.arbopt = ArbOpt()

        # lp pairs from input file, file created with web3bsc / lppair_search_process()
        self.lp_df = pd.read_csv('lppair_list.txt',
                                 delimiter=';',
                                 names=['block', 'tx', 'token0', 'token1', 'lp_addr', 'pair_symbol'],
                                 skipinitialspace=True)
        # preprocess loaded pair (remove duplicates, filter, sort..)
        self.df_preprocess()

        # self.arb_test()
        # exit()

    def arb_test(self):
        swap_list = ['0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c',  # BNB
                     '0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56',  # BUSD
                     '0x8D78C2ff1fB4FBA08c7691Dfeac7bB425a91c81A',  # LATTE
                     '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c']  # BNB
        swap_list = swap_list[::-1]

        self.arbopt.swap_list = swap_list
        res = minimize_scalar(self.arbopt.objective, bounds=(0, 1e20), method='bounded')
        print('max profit=', -res.fun/1e18, 'wbnb')
        """
                 fun: 7.612501796519448e-08
             message: 'Solution found.'
                nfev: 121
              status: 0
             success: True
                   x: 5.012758587438169e-06
        """
        # initinv = 1e18
        # amounts = self.dw3.get_swap_amounts_out(initinv, swap_list)
        # print([a/1e18 for a in amounts], 'profit = ', 100 * (amounts[-1] - amounts[0]) / amounts[0])
        # exit()
        pass

    def df_preprocess(self):
        # remove lp_addr duplicates
        self.lp_df.drop_duplicates(inplace=True, subset=['lp_addr'], ignore_index=True)

        # separate token names
        pair_symbols = self.lp_df['pair_symbol'].str.strip().tolist()
        symnames = [ps.split('-') for ps in pair_symbols]
        token0_symbol = [i[0] for i in symnames]
        token1_symbol = [i[1] for i in symnames]
        self.lp_df['token0_symbol'] = token0_symbol
        self.lp_df['token1_symbol'] = token1_symbol

        # identify base tokens
        # self.base_tokens = self.get_base_token_list()
        self.base_tokens = ['0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56',   # Binance-Peg BUSD Token (BUSD) 
                            '0x55d398326f99059fF775485246999027B3197955',   # Binance-Peg BSC-USD (BSC-USD)
                            '0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82',   # PancakeSwap Token (Cake) 
                            '0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c',   # Binance-Peg BTCB Token (BTCB)
                            '0x2170Ed0880ac9A755fd29B2688956BD959F933F8',   # Binance-Peg Ethereum Token (ETH)
                            '0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d']   # Binance-Peg USD Coin (USDC) 
        # drop all rows not containing base token
        # # TODO - is this necessary?
        # self.lp_df = self.lp_df[self.lp_df['token0'].isin(self.base_tokens) | self.lp_df['token1'].isin(self.base_tokens)]

        # create column with base symbol name
        self.lp_df['base_symbol'] = np.where(self.lp_df['token0'].isin(self.base_tokens),
                                             self.lp_df['token0_symbol'],
                                             self.lp_df['token1_symbol'])

        # token0 should be the base asset
        swap_selector = self.lp_df['token1'].isin(self.base_tokens)
        self.lp_df.loc[swap_selector, ['token0', 'token1']] = self.lp_df.loc[swap_selector, ['token1', 'token0']].values
        # TODO - both token are base token?! remove for now
        drop_selector = self.lp_df['token0'].isin(self.base_tokens) & self.lp_df['token1'].isin(self.base_tokens)
        self.lp_df.drop(self.lp_df.index[drop_selector], inplace=True)
        # rename token columns
        self.lp_df.rename({'token0': 'base_token', 'token1': 'quote_token'}, axis='columns', inplace=True)
        # drop symbol names
        self.lp_df.drop(columns=['token0_symbol', 'token1_symbol'], inplace=True)
        # processed flag
        self.lp_df['processed'] = False

        self.lp_df.to_csv('lppair_list_proc.txt', sep=';', index=False)
        # pd.set_option('display.max_columns', None)
        print(len(self.lp_df), 'lp pair loaded')

    def search_for_arbitrage(self):
        df = self.lp_df
        df['swap_profit_bnb'] = 0.0
        df['reverse_profit'] = False
        df['initial_investment_bnb'] = 0.0
        df['swap_chain'] = np.nan

        max_lines = len(self.lp_df)
        fwrite_time = time.time()
        for df_row_idx in df.index:
            # skip processed
            if df.at[df_row_idx, 'processed']:
                continue
            # get token address
            quote_token_addr = df.at[df_row_idx, 'quote_token']
            # get all occurrences
            occ_idxs = df.loc[df.quote_token == quote_token_addr].index
            # create separate df
            curr_df = df.loc[occ_idxs, ['base_token', 'lp_addr', 'base_symbol']]

            for idx, bt_row in curr_df.iterrows():
                # check arbitrage through 3 swaps, TODO: deeper
                swap_chain = [self.dw3.wbnb_addr,
                              quote_token_addr,
                              bt_row.base_token,
                              self.dw3.wbnb_addr]

                amounts = self.dw3.get_swap_amounts_out(1, swap_chain)
                profit_percentage = 100 * (amounts[-1] - amounts[0]) / amounts[0]
                amounts = self.dw3.get_swap_amounts_out(1, swap_chain[::-1])
                reverse_profit_percentage = 100 * (amounts[-1] - amounts[0]) / amounts[0]

                # min profit percentage
                min_profit_percentage = 3
                if profit_percentage < min_profit_percentage and reverse_profit_percentage < min_profit_percentage:
                    continue

                # get higher profit
                reverse = reverse_profit_percentage > profit_percentage
                # run optimization
                self.arbopt.swap_list = swap_chain[::-1] if reverse else swap_chain
                res = minimize_scalar(self.arbopt.objective, bounds=(0, 1e20), method='bounded')
                profit_in_bnb = -res.fun / 1e18

                # remove swap transaction fee
                profit_in_bnb -= 0.0015 * (len(swap_chain)-1)
                if profit_in_bnb < 0:
                    continue
                # initial investment
                initial_investment_bnb = res.x / 1e18

                # update dataframe
                df.loc[idx, 'swap_profit_bnb'] = profit_in_bnb
                df.loc[idx, 'reverse_profit'] = reverse
                df.loc[idx, 'initial_investment_bnb'] = '{:.2}'.format(initial_investment_bnb)
                df.loc[idx, 'swap_chain'] = '-'.join(swap_chain[1:-1]) if not reverse else '-'.join(swap_chain[::-1][1:-1])

                log_str = 'profit_in_bnb={:.2}'.format(profit_in_bnb) + \
                          ' , reverse=' + str(reverse) + \
                          ' , ' + quote_token_addr + \
                          ' , ' + bt_row.base_token + \
                          ' , progress= {:.2%}'.format(df_row_idx/max_lines) + \
                          ' , initial_investment={:.2}'.format(initial_investment_bnb)
                logging.info(log_str)
                print(log_str)

            # write modified df into file
            df.loc[occ_idxs, 'processed'] = True
            # sometimes update file
            if time.time() - fwrite_time > 10:
                self.lp_df.to_csv('lppair_list_proc.txt', sep=';', index=False)
                fwrite_time = time.time()
        self.lp_df.to_csv('lppair_list_proc.txt', sep=';', index=False)

    def get_base_token_list(self, occurrence_percentage_limit=0.01):
        # count token occurrence to get base tokens (unknown token0/token1 order)
        token_addr_df = pd.concat([self.lp_df['token0'], self.lp_df['token1']])
        all_token_addr_cnt = token_addr_df.value_counts(normalize=True)
        # get tokens with > occurrence_percentage_limit occurrence
        base_tokens = all_token_addr_cnt[all_token_addr_cnt > occurrence_percentage_limit].index.str.strip().tolist()
        return base_tokens


class Arbi():
    def __init__(self):
        self.net = Network(height='750px', width='100%', bgcolor='#222222', font_color='white')
        self.net.barnes_hut()
        self.graph = nx.DiGraph()

    def get_current_prices(self):
        exchange_info = requests.get('https://www.binance.com/api/v3/exchangeInfo').json()
        book_ticker = requests.get('https://www.binance.com/api/v3/ticker/bookTicker').json()
        assets = []
        for t in book_ticker:
            symbol = t['symbol']
            # find relevant exchange info
            for s in exchange_info['symbols']:
                if s['symbol'] == symbol:
                    base_asset = s['baseAsset']
                    quote_asset = s['quoteAsset']

                    # add asset as node
                    if base_asset not in assets:
                        assets.append(base_asset)
                        self.net.add_node(base_asset, base_asset, title=base_asset)
                    if quote_asset not in assets:
                        assets.append(quote_asset)
                        self.net.add_node(quote_asset, quote_asset, title=quote_asset)

                    # symbol = edges
                    self.net.add_edge(base_asset, quote_asset, value=t['bidPrice'])

                    self.graph.add_weighted_edges_from([(base_asset, quote_asset, t['askPrice']),
                                                        (quote_asset, base_asset, t['bidPrice'])])

    def show_graph(self):
        self.net.show('binance_pairs.html')


def main():
    bsca = BSCArb()
    bsca.search_for_arbitrage()

    exit()

    arb = Arbi()
    arb.get_current_prices()

    # print(list(nx.simple_cycles(arb.graph)))

    arb.show_graph()


if __name__ == '__main__':
    main()

