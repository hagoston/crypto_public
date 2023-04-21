import sys
import numpy as np
sys.path.insert(0, './utils')

from utils.ts_conv import get_str_from_ms, get_ms_from_str
from binance.client import Client
from utils.klines import BinanceKlines
from sklearn.preprocessing import minmax_scale
from bokeh.plotting import figure, output_file, show, save
import scipy.fft


class FFT:
    def __init__(self):
        pass

    def fft(self, data):
        #TODO:
        #   - reduce dimension
        #   - high / low in different fft
        norm = minmax_scale(data)*2 - 1.0
        #norm = data
        fft_commponents = scipy.fft.rfft(norm)
        fft_inverse = scipy.fft.irfft(fft_commponents)

        print(len(norm), len(fft_commponents), len(fft_inverse))

        p = figure(width=400, height=400)
        # p.line(range(0, len(data)), data, line_width=2)
        p.line(range(0, len(norm)), norm, line_width=2, color='blue')
        p.line(np.linspace(0, len(norm)-1, num=len(fft_inverse)), fft_inverse, line_width=2, color='red')
        save(p)

if __name__ == "__main__":
    print('fft.py main')

    bk = BinanceKlines('../../../data/binance_uncompressed/')
    fft = FFT()

    symbol = 'ADAUSDT'
    start_ms = get_ms_from_str('2022-04-01')
    end_ms = get_ms_from_str('2022-05-01')

    plot = True
    day_ms = 1 * 24 * 60 * 60 * 1000
    min_ms = 60 * 1000
    candle_df = bk.get_df(symbol, start_ms, start_ms + 1 * day_ms, Client.KLINE_INTERVAL_1MINUTE)

    fft.fft(candle_df.open.to_numpy())
