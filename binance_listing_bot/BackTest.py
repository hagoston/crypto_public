#!/usr/bin/python3
import logging
import time
import datetime
import os
import sys
import wget
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import gzip
from GateioTrader import GateioTrader
from bokeh.plotting import figure, output_file, show
from bokeh.models import Span, LabelSet, Label


def progress_bar(current, total, width=80):
    progress_message = "Downloading: %d%% [%d / %d] bytes" % (current / total * 100, current, total)
    sys.stdout.write("\r" + progress_message)
    sys.stdout.flush()


class BackTest:
    def __init__(self):
        # setup logger
        logdate = datetime.datetime.now().strftime("%Y%m%d_%H%M%S.%f")
        if not os.path.exists('./log'):
            os.makedirs('./log')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s.%(msecs)03d|%(levelname)s|%(filename)s:%(lineno)s %(funcName)s()|%(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.FileHandler(
                    "./log/back_test" + "_" + logdate + ".log", mode='w',
                    encoding=None, delay=False),
                logging.StreamHandler()
            ]
        )

        self.bt_folder = 'backtest/'
        self.data_folder = self.bt_folder + 'csvs/'
        # load list of previous coin listings
        self.listings_df = pd.read_csv(self.bt_folder + 'listing_list.txt')
        # cast release_date to int
        self.listings_df['release_date'] = self.listings_df['release_date'].apply(pd.to_numeric)
        self.listings_df['release_datetime'] = pd.to_datetime(self.listings_df['release_date'], unit='ms')

        # trader instance
        self.trader = GateioTrader()

    def listing_date_stat(self):
        dt = np.diff(self.listings_df['release_date'].to_numpy())
        dt_day = -dt / 1000 / 60 / 60 / 24

        # plot:
        fig, ax = plt.subplots()
        ax.hist(dt_day, bins=range(0, 30), edgecolor="white")
        plt.show()

    def load_spot_deals(self, symbol):
        for filename in os.listdir(self.data_folder):
            if symbol in filename:
                # parse release date
                release_date_epoch = int(filename.split('_')[0])/1000
                print(self.data_folder + filename)
                df = pd.read_csv(self.data_folder + filename,
                                 compression='gzip',
                                 names=['timestamp', 'dealid', 'price', 'amount', 'side'])
                df['side_str'] = np.where(df['side'] == 1, 'sell', 'buy')

                return {
                    'df': df,
                    'release_date': release_date_epoch
                }
        logging.error('could not find file with given symbol')
        return None

    def plot_listing(self, symbol):
        coin_dict = self.load_spot_deals(symbol)
        if not coin_dict:
            return

        # crop around release date
        listing_date = coin_dict['release_date']
        df = coin_dict['df']
        # get closest element to timestamp
        crop_end_date = listing_date + 5*60
        crop_end_idx = df.iloc[(df.timestamp - crop_end_date).abs().argsort()[:2]].index.tolist()[0]
        listing_idx = df.iloc[(df.timestamp - listing_date).abs().argsort()[:2]].index.tolist()[0]
        crop_start_idx = listing_idx + 10

        print(crop_start_idx, listing_idx, crop_end_idx)
        df = df[crop_end_idx:crop_start_idx]        # note: reverse order
        df.timestamp = df.timestamp - listing_date  # listing date to 0

        # print(np.sum(df.amount * df.price * np.where(df.side_str == 'sell', 1, -1)))
        max_price_index = df.price.idxmax()
        listing_price = df.price[listing_idx+1]

        p = figure(width=1600, height=800)
        p.title.text = symbol
        p.title.align = "center"
        p.title.text_font_size = "20px"
        p.circle(df.timestamp, df.price,
                 #size=5,
                 size=500 * df.amount / df.amount.max(),
                 color=np.where(df.side_str == 'sell', 'green', 'red'),     # Note: flip?!
                 alpha=0.5)
        # add vertical line to listing date
        vline = Span(location=0,
                     dimension='height', line_color='black',
                     line_dash='dashed', line_width=3)
        p.add_layout(vline)

        # add max price label
        labels = Label(x=df.timestamp[max_price_index], y=df.price[max_price_index],
                       text=f"{df.timestamp[max_price_index]:.2f}s {df.price[max_price_index]/listing_price:.2f}x")
        p.add_layout(labels)

        # get first point after listing

        txs_after_listing = df[df.timestamp > 0].sort_values(by=['timestamp'])
        first_after_listing = txs_after_listing.iloc[0]
        labels = Label(x=first_after_listing.timestamp, y=first_after_listing.price,
                       text=f"first tx after listing {first_after_listing.timestamp:.4f}s")
        p.add_layout(labels)

        for index, row in txs_after_listing.iterrows():

            print(row)
            order_id = row.dealid
            order_id = '105344462878'
            order_info = self.trader.get_spot_price_triggered_order(order_id)
            print(order_info)

            return
        #show(p)

    def download_gateio_historical_data(self, dl_limit=-1, extract=False):
        dl_cnt = 0

        for index, row in self.listings_df.iterrows():
            release_date = row['release_date']
            release_datetime = row['release_datetime']
            symbol = row['symbol']
            year = release_datetime.year
            month = release_datetime.month
            market = symbol+'_'+'USDT'

            if month == datetime.date.today().month:
                logging.error(f'no data for current month. {symbol} skipping')
                continue

            # wait for currency list
            while not self.trader.get_currency_list():
                time.sleep(0.5)

            if symbol not in self.trader.mp_dict['currency_list']:
                logging.error(f'{symbol} not listed in gate.io')
                continue

            biz = 'spot'
            dtypes = ['deals', 'orderbooks']
            odir = self.data_folder
            if not os.path.exists(odir):
                os.makedirs(odir)

            for dtype in dtypes:
                url = f'https://download.gatedata.org/{biz}/{dtype}/{year}{month}/{market}-{year}{month}.csv.gz'
                fname = f'{release_date}_{biz}_{dtype}_{market}_{year}{month}.csv.gz'
                gz_file = odir + '/' + fname

                logging.info(f'downloading {url}')
                try:
                    wget.download(url=url, out=gz_file, bar=progress_bar)
                except Exception as e:
                    logging.error(f'could not download file {url} :: {e}')
                else:
                    if extract:
                        # extract gzip
                        ofile = f"{odir}/{release_date}_{biz}_{dtype}_{market}_{year}{month}.csv"
                        with gzip.open(gz_file, 'rb') as file:
                            with open(ofile, 'wb') as output_file:
                                output_file.write(file.read())
                        os.remove(gz_file)

                    dl_cnt += 1
                    if 0 < dl_limit < dl_cnt/len(dtypes):
                        logging.info(f'download limit reached, exit')
                        return
                    logging.info(f'download finished')


if __name__ == '__main__':
    bt = BackTest()
    #bt.listing_date_stat()
    #bt.download_gateio_historical_data()
    bt.plot_listing('CVX')
