from binance.helpers import date_to_milliseconds, interval_to_milliseconds
from binance.client import Client
import csv
import json
from pathlib import Path

from ts_conv import get_ms_from_str, get_str_from_ms
import pandas as pd
import mplfinance as mpl
import math
import numpy as np


def kline_interval_to_ms(kline_interval: str):
    if Client.KLINE_INTERVAL_1MINUTE == kline_interval:
        return 1 * 60 * 1e3
    elif Client.KLINE_INTERVAL_5MINUTE == kline_interval:
        return 5 * 60 * 1e3
    elif Client.KLINE_INTERVAL_1HOUR == kline_interval:
        return 60 * 60 * 1e3
    elif Client.KLINE_INTERVAL_1DAY == kline_interval:
        return 24 * 60 * 60 * 1e3
    else:
        assert True


def plot_klines(symbol, df):
    # drop unnecessary columns
    df.drop(['close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'], axis=1, inplace=True)
    # make datetime as index
    df.open_time = pd.to_datetime(df.open_time, unit='ms')
    df = df.set_index('open_time')
    # some rename
    df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)

    mpl.plot(df, type='candle', title=f'{symbol}', style='yahoo')
    # mav=(3, 6, 9) moving average


class BinanceKlines:
    def __init__(self, ofolder):
        # load binance api keys
        with open(str(Path(__file__).parent.absolute()) + '/../secret/binance_keys.json') as json_file:
            data = json.load(json_file)
            self.api_key = data['api_key']
            self.secret_key = data['secret_key']

        self.client = Client(self.api_key, self.secret_key)
        self.ofolder = ofolder
        self.csv_interval_ms = 1 * 24 * 60 * 60 * 1000  # all csv contains this amount of data

    def get_df(self, symbol, start_ms, end_ms, kline_interval):
        # how many files needs to be loaded
        start_ms_midnight = get_ms_from_str(get_str_from_ms(start_ms))
        end_ms_midnight = get_ms_from_str(get_str_from_ms(end_ms))
        if end_ms > end_ms_midnight:
            end_ms_midnight += 1    # add one file
        number_of_files = math.ceil((end_ms_midnight - start_ms_midnight) / self.csv_interval_ms)

        #print(get_str_from_ms(start_ms, '%Y-%m-%d %H:%M:%S'), '-', get_str_from_ms(end_ms, '%Y-%m-%d %H:%M:%S'),
        #      f'number of files = {number_of_files}')
        # create file names
        file_list = []
        t0 = start_ms
        for i in range(number_of_files):
            file_name = self.get_fname(symbol, t0, t0+self.csv_interval_ms, kline_interval)
            file_list.append(file_name)
            t0 += self.csv_interval_ms
        # read files from file list into dataframe
        df = pd.concat((pd.read_csv(f) for f in file_list))
        # TODO ddf = dd.read_csv(f"{path}/*.csv")
        # drop unnecessary data?
        return df

    def get_ohlc_df(self, symbol, start_ms, end_ms, kline_interval):
        # print(start_ms, '-' , end_ms)
        df = self.get_df(symbol, start_ms, end_ms, kline_interval)
        df.drop(['close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume',
                 'taker_buy_quote_asset_volume', 'ignore', 'volume'], axis=1, inplace=True)
        # drop based on ts
        df = df[df.open_time >= start_ms]
        df = df[df.open_time < end_ms]
        # make datetime as index
        df.open_time = pd.to_datetime(df.open_time, unit='ms')
        df = df.set_index('open_time')
        return df

    def get_o_df(self, symbol, start_ms, end_ms, kline_interval):
        df = self.get_ohlc_df(symbol, start_ms, end_ms, kline_interval)
        df.drop(['high', 'low', 'close'], axis=1, inplace=True)
        return df

    def get_fname(self, symbol, t0, t1, kline_interval):
        return self.ofolder + symbol + '/KLINES/' \
        + symbol + '_KLINES' \
        + '_' + get_str_from_ms(t0) + '-' + get_str_from_ms(t1) \
        + '_' + f'{kline_interval}' + '.csv'

    def download_klines(self, symbol, start_ms, end_ms, kline_interval):
        # klines header
        header = ['open_time',
                  'open',
                  'high',
                  'low',
                  'close',
                  'volume',
                  'close_time',
                  'quote_asset_volume',
                  'number_of_trades',
                  'taker_buy_base_asset_volume',
                  'taker_buy_quote_asset_volume',
                  'ignore']

        for s in range(start_ms, end_ms, self.csv_interval_ms):
            t0 = s
            t1 = s + self.csv_interval_ms
            klines = self.get_historical_klines(symbol, kline_interval, int(t0), int(t1))
            fname = self.get_fname(symbol, t0, t1, kline_interval)

            with open(fname, 'w') as output:
                writer = csv.writer(output, lineterminator='\n')
                writer.writerow(header)
                writer.writerows(klines)
            print(f'downloading done for {fname}')

    def get_earliest_valid_timestamp(self, symbol, interval):
        kline = self.client.get_klines(
            symbol=symbol,
            interval=interval,
            limit=1,
            startTime=0,
            endTime=None
        )
        return kline[0][0]

    def get_historical_klines(self, symbol, interval, start_str, end_str=None):
        """
        binance client mod
        """
        # init our list
        output_data = []

        # setup the max limit
        limit = 500

        # convert interval to useful value in seconds
        timeframe = interval_to_milliseconds(interval)

        # convert our date strings to milliseconds
        if type(start_str) == int:
            start_ts = start_str
        else:
            start_ts = date_to_milliseconds(start_str)

        # establish first available start timestamp
        first_valid_ts = self.get_earliest_valid_timestamp(symbol, interval)
        start_ts = max(start_ts, first_valid_ts)

        # if an end time was passed convert it
        end_ts = None
        if end_str:
            if type(end_str) == int:
                end_ts = end_str
            else:
                end_ts = self.client.date_to_milliseconds(end_str)
            end_ts = end_ts - timeframe

        idx = 0
        while True:
            # fetch the klines from start_ts up to max 500 entries or the end_ts if set
            temp_data = self.client.get_klines(
                symbol=symbol,
                interval=interval,
                limit=limit,
                startTime=start_ts,
                endTime=end_ts
            )

            # handle the case where exactly the limit amount of data was returned last loop
            if not len(temp_data):
                break

            # append this loops data to our output data
            output_data += temp_data

            # set our start timestamp using the last value in the array
            start_ts = temp_data[-1][0]

            # idx += 1
            # check if we received less than the required limit and exit the loop
            if len(temp_data) < limit:
                # exit the while loop
                break

            # increment next call by our timeframe
            start_ts += timeframe

            # # sleep after every 3rd call to be kind to the API
            # if idx % 3 == 0:
            #     time.sleep(1)

        return output_data


if __name__ == "__main__":
    print('klines.py main')
    bk = BinanceKlines('../../../../data/binance_uncompressed/')

    symbol = 'ADAUSDT'
    start_ms = get_ms_from_str('2021-02-10')
    end_ms = get_ms_from_str('2021-02-12')

    plot = False
    download = True

    if plot:
        dayms = 1 * 24 * 60 * 60 * 1000
        candle_df = bk.get_df(symbol, start_ms, start_ms + 5 * dayms, Client.KLINE_INTERVAL_1HOUR)
        plot_klines(symbol, candle_df)

    if download:
        kline_intervals = [Client.KLINE_INTERVAL_5MINUTE]
        # kline_intervals = [Client.KLINE_INTERVAL_1MINUTE,
        #                    Client.KLINE_INTERVAL_5MINUTE,
        #                    Client.KLINE_INTERVAL_1HOUR,
        #                    Client.KLINE_INTERVAL_1DAY]
        for ki in kline_intervals:
            bk.download_klines(symbol, start_ms, end_ms, ki)
