import mplfinance as mpf
import pandas as pd

files = [
    ('ARKER-USDT_1min_klines.csv', '2022-11-06T17:00:00'),
    ('LAVAX-USDT_1min_klines.csv', '2022-10-23T16:00:00'),
    ('FLAME-USDT_1min_klines.csv', '2022-10-16T16:00:00')
]

input = files[1]

df = pd.read_csv(input[0])
df = df.set_index(pd.to_datetime(df['Time'],unit='s'))
df.sort_index(inplace=True)

# date_to_compare = pd.to_datetime(input[1])
# df = df[df.index < date_to_compare]

mpf.plot(df, type='candle', volume=True, title=input[0])
