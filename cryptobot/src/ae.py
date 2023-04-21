import sys
sys.path.insert(0, './utils')

from utils.ts_conv import get_str_from_ms, get_ms_from_str
from binance.client import Client

import mplfinance as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tensorflow as tf

from candle_data_generator import CandleDataGenerator, TickDataGenerator
from sklearn.metrics import accuracy_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from tensorflow.keras import layers, losses
from tensorflow.keras.datasets import fashion_mnist
from tensorflow.keras.models import Model
from tensorflow import keras


# try using latent space of an autoencoder trained with candles data

class Autoencoder(Model):
    def __init__(self, latent_dim, data_len=60, data_dim=4):
        super(Autoencoder, self).__init__()
        self.latent_dim = latent_dim

        self.encoder = tf.keras.Sequential([
            layers.Flatten(),
            layers.Dense(int(data_len*data_dim/2), activation='relu'),
            layers.Dense(latent_dim, activation='relu'),
        ])
        self.decoder = tf.keras.Sequential([
            layers.Dense(int(data_len*data_dim/2), activation='relu'),
            layers.Dense(data_len*data_dim, activation='relu'),
            layers.Reshape((data_len, data_dim))
        ])

    def call(self, x):
        encoded = self.encoder(x)
        decoded = self.decoder(encoded)
        return decoded


class O_AEHandler():
    def __init__(self, load=True):
        self.model_files = './o_ae_model'
        data_len = 180
        data_dim = 1
        if load:
            self.ae = keras.models.load_model(self.model_files)
        else:
            self.ae = Autoencoder(32, data_len, data_dim)
        self.batch_size = 64
        split_ms = get_ms_from_str('2022-01-01')
        self.x_train = TickDataGenerator(start_ms=get_ms_from_str('2021-01-01'),
                                         end_ms=split_ms,
                                         batch_size=self.batch_size,
                                         candle_count=data_len)
        self.x_test = TickDataGenerator(start_ms=split_ms,
                                        end_ms=get_ms_from_str('2022-08-01'),
                                        batch_size=self.batch_size,
                                        candle_count=data_len)

        # for idx in range(0, self.x_train.__len__()):
        #     test_batch, tss = self.x_train.__getitem__(idx, True)
        #     print(f'#{idx}')
        #     for i, b in enumerate(test_batch):
        #         if b.min() > 0.0 or b.max() != 1.0:
        #             print(f'#{i}', b.shape, b.min(), b.max())
        # exit()

    def train(self):
        self.ae.compile(optimizer='adam', loss=losses.MeanSquaredError())
        self.ae.fit(self.x_train,
                    epochs=10,
                    shuffle=True,
                    validation_data=self.x_test)
        self.ae.save(self.model_files)

    def test(self):
        test_batch, tss = self.x_test.__getitem__(0, True)
        #for b in test_batch:
        #    print(b.shape, b.min(), b.max())
        #exit()
        encoded_data = self.ae.encoder(test_batch).numpy()
        decoded_data = self.ae.decoder(encoded_data).numpy()

        for batch_index in range(0, len(test_batch)):
            data = test_batch[batch_index]
            data_ts = tss[batch_index]
            df = pd.DataFrame(data=data, columns=['original'])
            df.set_index(data_ts, inplace=True)
            df['reconstructed'] = decoded_data[batch_index]
            df.plot()
            plt.show()
            #exit()


class OHLC_AEHandler():
    def __init__(self, load=True):
        self.model_files = './ae_model'
        if load:
            self.ae = keras.models.load_model(self.model_files)
        else:
            self.ae = Autoencoder(64)
        self.batch_size = 64
        split_ms = get_ms_from_str('2022-01-01')
        self.x_train = CandleDataGenerator(start_ms=get_ms_from_str('2021-01-01'),
                                           end_ms=split_ms,
                                           batch_size=self.batch_size)
        self.x_test = CandleDataGenerator(start_ms=split_ms,
                                          end_ms=get_ms_from_str('2022-08-01'),
                                          batch_size=self.batch_size)

        # for idx in range(0, self.x_train.__len__()):
        #     test_batch, tss = self.x_train.__getitem__(idx, True)
        #     print(f'#{idx}')
        #     for i, b in enumerate(test_batch):
        #         if b.min() > 0.0 or b.max() != 1.0:
        #             print(f'#{i}', b.shape, b.min(), b.max())
        # exit()

    def train(self):
        self.ae.compile(optimizer='adam', loss=losses.MeanSquaredError())
        self.ae.fit(self.x_train,
                    epochs=10,
                    shuffle=True,
                    validation_data=self.x_test)
        self.ae.save(self.model_files)

    def test(self):
        test_batch, tss = self.x_test.__getitem__(0, True)
        #for b in test_batch:
        #    print(b.shape, b.min(), b.max())
        #exit()
        encoded_data = self.ae.encoder(test_batch).numpy()
        decoded_data = self.ae.decoder(encoded_data).numpy()

        for batch_index in range(0, len(test_batch)):
            data = test_batch[batch_index]
            data_ts = tss[batch_index]
            df = pd.DataFrame(data=data, columns=['Open', 'High', 'Low', 'Close'])
            df.set_index(data_ts, inplace=True)

            df_reconstructed = pd.DataFrame(data=decoded_data[batch_index], columns=['Open', 'High', 'Low', 'Close'])
            df_reconstructed.set_index(data_ts, inplace=True)

            additional = [mpl.make_addplot(df_reconstructed, type='candle', title=f'reconstructed', panel=1)]
            mpl.plot(df, type='candle', title=f'original', style='yahoo',
                     addplot=additional,
                     panel_ratios=(1, 1))
            #exit()


if __name__ == "__main__":
    print(f'{__file__} main')

    train = True
    aeh = O_AEHandler(load=not train)
    if train:
        aeh.train()
    aeh.test()

