import os
import sys
import argparse
import time
from dask import dataframe as dd
from dask.distributed import Client
import shutil
import numpy as np
from icecream import ic
import pyarrow as pa
import requests
import json

class CSV2Parquet(object):
    def __init__(self, args):
        self.filter = args.filter
        self.timer = time.time()
        # set up dask cluster and workers
        # Dashboard: http://localhost:8787/status
        self.client = Client(n_workers = 4, 
                             threads_per_worker = 2,
                             memory_limit='8GB')
        # config log
        ic.configureOutput(prefix=self.log_prefix)
        ic.configureOutput(includeContext=True)
        # ic.disable()

        ## input files, output files
        # expected folder structure sample:
        # args.input_path /
        #    /T_DEPTH/<symbol>_T_DEPTH_2021-01-15_depth_snap.csv
        #    /T_DEPTH/<symbol>_T_DEPTH_2021-01-15_depth_update.csv
        #    /T_TRADE/<symbol>_T_TRADE_20210115.csv
        path_ = os.path.normpath(args.input_path)
        path_split = path_.split(os.sep)
        self.symbol = path_split[-1]
        output_path = path_ + os.sep + ".." + os.sep + ".." + os.sep + 'binance_parquet' + os.sep + self.symbol + os.sep
        # create output dir
        os.makedirs(output_path, exist_ok=True)
        self.date = args.date

        # file list
        self.files = {
            'snap'  : path_ + os.sep + 'T_DEPTH' + os.sep + self.symbol + '_T_DEPTH_' + self.date + '_depth_snap.csv',
            'update': path_ + os.sep + 'T_DEPTH' + os.sep + self.symbol + '_T_DEPTH_' + self.date + '_depth_update.csv',
            'trade' : path_ + os.sep + 'T_TRADE' + os.sep + self.symbol + '_T_TRADE_' + self.date.replace('-', '') + '.csv',
            'output': output_path + self.symbol + '_' + self.date + '.parquet'
        }

        # get symbol precision i.e. quantity precision in csv files
        ic()
        exchange_info = requests.get('https://www.binance.com/fapi/v1/exchangeInfo')
        ic()
        if exchange_info.status_code != 200:
            print('future exchanginfo request failed')
            exit(0)
        self.symbol_decimal_precision = -1
        exchange_info_data = json.loads(exchange_info.text)
        for s in exchange_info_data['symbols']:
            if self.symbol == s['symbol']:
                for f in s['filters']:
                    if f['filterType'] == 'LOT_SIZE':
                        stepsize = f['stepSize']
                        self.symbol_decimal_precision = int(np.abs(np.rint(np.log10(np.float(stepsize)))))
        if self.symbol_decimal_precision < 0:
            print("WARNING:: unable to fetch symbol decimal precision, using default 3 decimal precision")
            self.symbol_decimal_precision = 3
        print("output decimal precision set to", self.symbol_decimal_precision)

    def log_prefix(self):
        curr_time = time.time()
        dt = curr_time - self.timer
        self.timer = time.time()
        return '%s (dt=%.3f) |> ' % (time.strftime("%H:%M:%S", time.localtime(curr_time)), dt)

    def get_size(self, path):
        total_size = 0

        if isinstance(path, dict):
            for k, v in path.items():
                if k != 'output':
                    total_size += os.path.getsize(v)
            return total_size
        
        if os.path.isfile(path):
            return os.path.getsize(path)

        for path, dirs, files in os.walk(path):
            for f in files:
                fp = os.path.join(path, f)
                total_size += os.path.getsize(fp)
        return total_size

    def set_datetime_index(self, df):
        # convert timestamp into datetime
        # dfs = dfs if isinstance(dfs, list) else [dfs] 
        # for df in dfs:
        ic()
        df['timestamp'] = dd.to_datetime(df['timestamp'], unit='ms')
        ic()
        # set as index, not sorted after previous concat
        df = df.set_index('timestamp')
        ic()
        return df

    def df_simplify(self, df):
        # check discontinuity

        ic()
        # get unique pu-s
        ddf_ = df.drop_duplicates('pu')

        ic()    
        if 0:
        ##
        ## else branch is faster 
        ##
            # new column indicating pu != last_update_id_prev
            df['discontinuity'] = False
            
            # skip snap dataframes further completeness check
            # snap has all -1 values in pu column
            if len(ddf_.pu) > 1:                    # 60 sec with 10GB file
                # pu =? last_update_id_prev
                ddf_ = ddf_[ddf_.pu.ne(ddf_.last_update_id.shift())]
                
                # get list of indexes
                pu_list = ddf_.pu.values.compute()  # 60 sec with 10GB file
                
                # skip first coming from shift operation NaN injection
                pu_list = pu_list[1:]

                df['discontinuity'] = df.pu.isin(pu_list)
        else:
            # pu =? last_update_id_prev
            ddf_ = ddf_[ddf_.pu.ne(ddf_.last_update_id.shift())]
            # new column for completeness flag
            # whole block with same timestamp gets True if (pu != last_update_id_prev)
            df['discontinuity'] = df.pu.isin(ddf_.pu.values.compute()[1:])
        ic()
        df['is_ask'] = (df.side == 'a')
        ic()

        # drop unnecessary columns 
        df = df.drop(['symbol',             # parquet folder name contains symbol name 
                      'first_update_id',    # unused
                      'last_update_id',     # last_update_id with pu used for completeness check -> discontinuity column
                      'side',               # converted to is_ask
                      'pu'], axis=1)
        
        # # disable colum type tweak, no size reduction 
        # ic()
        # df.side = (df.side == 'b').astype(np.bool)
        # df.price = (df.price*100).astype(np.uint32)
        # df.qty = (df.qty*1000).astype(np.uint32)
        # print(df.dtypes)

        ic()
        
        return df

    def run(self):
        # get original size
        original_size = self.get_size(self.files)
        
        # read file with dask
        df_update = dd.read_csv(self.files['update'])
        df_snap = dd.read_csv(self.files['snap'])
        df_trade = dd.read_csv(self.files['trade'])

        '''
        ### output dataframe fields ###
        
          datetimeindex   ->   commond timestamp, epoch in [ms]
          update_type     ->   'snap' :  +-1000 price snapshot
                               'set'  :  order book update, set price level to current qty (not delta)
                               'trade':  tick-by-tick trade (https://binance-docs.github.io/apidocs/futures/en/#recent-trades-list)
          is_ask          ->   if update_type == 'trade':
                                    == 'is_buyer_maker'
                                        True: ask, SELL trade
                                            If isBuyerMaker is true for the trade, it means that the order of whoever was on the buy side, 
                                            was sitting as a bid in the orderbook for some time (so that it was making the market) 
                                            and then someone came in and matched it immediately (market taker). 
                                            So, that specific trade will now qualify as SELL and in UI highlight as redish.
                                        False: bid, BUY trade
                                            On the opposite isBuyerMaker=false trade will qualify as BUY and highlight greenish.
                               else:
                                    'is_ask'
                                        True:  ask, SELL order
                                        False:  bid, BUY order

          price
          qty
          discontinuity   ->   completeness check (https://binance-docs.github.io/apidocs/futures/en/#diff-book-depth-streams / 6.)
                                False: everythings ok
                                True: missing data, order book corrupted, start clean order book from snap 
        '''
        
        ## converting trade file dataframe to common  output fields
        # id,symbol,price,qty,quote_qty,time,is_buyer_maker
        df_trade = df_trade.rename(columns={"time": "timestamp"})
        df_trade = df_trade.rename(columns={"is_buyer_maker": "is_ask"})
        df_trade = df_trade.drop(['id', 'symbol', 'quote_qty'], axis=1)
        # sum qty-s with same price, date and is_buyer_maker flag (id was different but hey, who cares)
        df_trade = df_trade.groupby(['timestamp','price','is_ask'])['qty'].sum().reset_index()
        qty_decimal_precision = int(self.symbol_decimal_precision)
        df_trade['qty'] = df_trade['qty'].map(lambda x: np.round(x, qty_decimal_precision))
        df_trade['discontinuity'] = False
        df_trade['update_type'] = 'trade'

        # # Note: debug only
        # print(df_trade.dtypes)
        # df_trade.compute().to_csv(self.files['output'] + '_concat_simp.csv')
        # exit(0)

        # # Note: debug only, keeping one timestamp
        # df_update = df_update.drop_duplicates('timestamp')
        # df_snap = df_snap.drop_duplicates('timestamp')

        ## converting snap and update file dataframes to common output fields
        # symbol,timestamp,first_update_id,last_update_id,side,update_type,price,qty,pu
        df_update = self.df_simplify(df_update)
        df_snap = self.df_simplify(df_snap)

        # merge two dataframe
        # snap file fits in memory, ensure that it is a single partition
        df_snap = df_snap.repartition(npartitions=1)
        
        # concat note: should be sorted after
        df = dd.concat([df_update, df_trade, df_snap])
        # dask cleanup 
        del df_update
        del df_snap
        del df_trade

        # convert timestamp to datetime and set as index
        df = self.set_datetime_index(df)

        # # Note: debug only
        # df.compute().to_csv(self.files['output'] + '_concat_simp.csv')
        # exit(0)

        if not df.known_divisions:
            print('df.known_divisions should be true')
            exit(0)
        
        # remove previous output
        if os.path.exists(self.files['output']):
            if os.path.isdir(self.files['output']):
                shutil.rmtree(self.files['output'])
            else:
                os.remove(self.files['output'])
        # write parquet
        ic()
        df.to_parquet(self.files['output'], engine='pyarrow', compression='gzip', write_index=True)
        ic()
        
        # close workers and cluster
        self.client.close()
        print('%.2f MB converted to %.2f MB parquet' % (original_size / 2**20, self.get_size(self.files['output']) / 2**20))
    
    def data_pipeline_test():
        # compare input output data
        print('TODO')
        

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='csv convert to parquet')
    parser.add_argument('--input_path', 
                            required=False, 
                            default='~/temp/crypto/data/binance_uncompressed/BTCUSDT/', 
                            help='folder or file containing csv')
    parser.add_argument('--date',
                            required=False, 
                            default='2021-04-01', 
                            help='file filter')
    parser.add_argument('--filter', 
                            required=False, 
                            default='', 
                            help='file filter')
    args = parser.parse_args()
    
    CSV2Parquet(args).run()