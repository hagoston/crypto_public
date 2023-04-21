import numpy as np
from binance.client import Client
import get_klines as bn
import time
import csv


client = Client("","")

# get time of today midnight
ts = time.time()
today_midnight_ts = int((ts - ts % (24 * 60 * 60)) * 1000)

# set symbol
symbol = 'BNBBTC'

# set file chunk interval to 10 days
file_interval = 10 * 24 * 60 * 60 * 1000

# set start time
# start_time = bn.get_earliest_valid_timestamp(client, symbol, Client.KLINE_INTERVAL_1MINUTE)

# get data backward
download_bw = 1
start_time = today_midnight_ts
end_time = start_time + file_interval
if download_bw:
    end_time = today_midnight_ts
    start_time = end_time - file_interval

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

for i in range(2):
    fname = symbol + '_' + str(start_time) + '-' + str(end_time) + '.csv'

    klines = bn.get_historical_klines(client, symbol, Client.KLINE_INTERVAL_1MINUTE, int(start_time), int(end_time))
    with open(fname, 'w') as output:
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(header)
        writer.writerows(klines)

    if download_bw:
        end_time = start_time
        start_time = end_time - file_interval
    else:
        start_time = end_time
        end_time = end_time + file_interval