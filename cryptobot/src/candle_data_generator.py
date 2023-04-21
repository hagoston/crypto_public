import sys
sys.path.insert(0, './utils')

# Imports
import numpy as np
import pandas as pd
import tensorflow as tf

from utils.ts_conv import get_str_from_ms, get_ms_from_str
from binance.client import Client
from utils.klines import BinanceKlines, kline_interval_to_ms
from binance.client import Client


class CandleDataGenerator(tf.keras.utils.Sequence):
    """
    Custom data generator class for klines
    https://www.kaggle.com/code/heyytanay/tensorflow-model-custom-keras-data-generators/notebook
    """
    def __init__(self,
                 batch_size: int = 10,
                 candle_interval: str = Client.KLINE_INTERVAL_1MINUTE,  # candle type
                 candle_count: int = 60,                                # number of candles per data
                 start_ms: int = get_ms_from_str('2021-01-01'),
                 end_ms: int = get_ms_from_str('2022-08-01')):
        # TODO: different kline intervals from 1M candle
        self.batch_size = batch_size
        self.candle_count = candle_count
        self.candle_interval = candle_interval
        data_path = '../../../data/binance_uncompressed/'
        self.bk = BinanceKlines(data_path)
        self.symbol = 'ADAUSDT'
        # TODO: read available data range
        self.data_start_ms = start_ms
        self.data_end_ms = end_ms
        self.ms_per_data = kline_interval_to_ms(candle_interval) * candle_count
        self.data_len = np.math.floor((self.data_end_ms - self.data_start_ms) / self.ms_per_data)

    def __len__(self):
        return np.math.floor(self.data_len / self.batch_size)

    def __getitem__(self, index, return_timestamps=None):
        """
        Returns a batch of data
        """
        start_ms = self.data_start_ms + index * self.batch_size * self.ms_per_data
        end_ms = start_ms + self.batch_size * self.ms_per_data
        df = self.bk.get_ohlc_df(self.symbol, start_ms, end_ms, self.candle_interval)

        # data validation
        while len(df.values) < self.candle_count * self.batch_size:
            # dirty skip..
            return self.__getitem__(index + 1, return_timestamps)
            # TODO: must be a simple way..
            # fill missing data with previous row
            df_idx = df.index.to_series()
            dt = df_idx - df_idx.shift()
            dt_bool = dt > pd.Timedelta(kline_interval_to_ms(self.candle_interval), 'milliseconds')
            gap_end_index = df[dt_bool].index[0]
            gap_end_index_loc = df.index.get_loc(gap_end_index)
            gap_begin_index = df.iloc[gap_end_index_loc-1].name
            gap_next_index = gap_begin_index + pd.Timedelta(kline_interval_to_ms(self.candle_interval), 'milliseconds')
            new_row = df.iloc[gap_end_index_loc-1].to_frame().T
            df = pd.concat([df, pd.DataFrame(new_row, index=[gap_next_index.to_pydatetime()])])
            df.iloc[-1] = new_row
            df = df.sort_index()
        try:
            batch_data = df.values.reshape(self.batch_size, -1, len(df.columns))      # 4 == open, high, low, close
            # scale to {0, 1}
            for i, b in enumerate(batch_data):
                batch_data[i] = (b - np.min(b)) / np.ptp(b)
        except:
            print('\n', self.__len__(), index, len(df.values), self.data_len)
            print(self.data_start_ms, self.data_end_ms)
            print(start_ms, end_ms)
            exit(0)

        if return_timestamps:
            return batch_data, df.index.to_numpy().reshape(self.batch_size, -1)
        else:
            return batch_data, batch_data       # y == X for autoencoders


class TickDataGenerator(tf.keras.utils.Sequence):
    def __init__(self,
                 batch_size: int = 10,
                 candle_interval: str = Client.KLINE_INTERVAL_1MINUTE,  # candle type
                 candle_count: int = 60,                                # number of candles per data
                 start_ms: int = get_ms_from_str('2021-01-01'),
                 end_ms: int = get_ms_from_str('2022-08-01')):
        # TODO: different kline intervals from 1M candle
        self.batch_size = batch_size
        self.candle_count = candle_count
        self.candle_interval = candle_interval
        data_path = '../../../data/binance_uncompressed/'
        self.bk = BinanceKlines(data_path)
        self.symbol = 'ADAUSDT'
        # TODO: read available data range
        self.data_start_ms = start_ms
        self.data_end_ms = end_ms
        self.ms_per_data = kline_interval_to_ms(candle_interval) * candle_count
        self.data_len = np.math.floor((self.data_end_ms - self.data_start_ms) / self.ms_per_data)

    def __len__(self):
        return np.math.floor(self.data_len / self.batch_size)

    def __getitem__(self, index, return_timestamps=None):
        """
        Returns a batch of data
        """
        start_ms = self.data_start_ms + index * self.batch_size * self.ms_per_data
        end_ms = start_ms + self.batch_size * self.ms_per_data
        df = self.bk.get_o_df(self.symbol, start_ms, end_ms, self.candle_interval)

        # data validation
        while len(df.values) < self.candle_count * self.batch_size:
            # dirty skip..
            return self.__getitem__(index + 1, return_timestamps)
        try:
            batch_data = df.values.reshape(self.batch_size, -1, len(df.columns))      # 4 == open, high, low, close
            # scale to {0, 1}
            for i, b in enumerate(batch_data):
                batch_data[i] = (b - np.min(b)) / np.ptp(b)
        except:
            print('ERRO:: \n', self.__len__(), index, len(df.values), self.data_len)
            print(self.data_start_ms, self.data_end_ms)
            print(start_ms, end_ms)
            exit(0)

        if return_timestamps:
            return batch_data, df.index.to_numpy().reshape(self.batch_size, -1)
        else:
            return batch_data, batch_data       # y == X for autoencoders


if __name__ == "__main__":
    print(f'{__file__} main')
    cdg = CandleDataGenerator(start_ms=get_ms_from_str('2021-01-01'),
                              end_ms=get_ms_from_str('2022-01-01'))
    print(f'len = {cdg.__len__()}')
    print(f'len = {cdg.data_start_ms} - {cdg.data_end_ms}')

    for idx in range(0, cdg.__len__()):
        print(f'#{idx} {[d.shape for d in cdg.__getitem__(idx)]}')


