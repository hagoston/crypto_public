import sys
sys.path.insert(0, './utils')

from utils.ts_conv import get_str_from_ms, get_ms_from_str
from binance.client import Client
from utils.klines import BinanceKlines

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tensorflow as tf

from sklearn.metrics import accuracy_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from tensorflow.keras import layers, losses
from tensorflow.keras.datasets import fashion_mnist
from tensorflow.keras.models import Model
from tensorflow import keras


# try using latent space of an autoencoder trained with candles data

class Autoencoder(Model):
    def __init__(self, latent_dim):
        super(Autoencoder, self).__init__()
        self.latent_dim = latent_dim
        self.encoder = tf.keras.Sequential([
            layers.Flatten(),
            layers.Dense(latent_dim, activation='relu'),
        ])
        self.decoder = tf.keras.Sequential([
            layers.Dense(784, activation='sigmoid'),
            layers.Reshape((28, 28))
        ])

    def call(self, x):
        encoded = self.encoder(x)
        decoded = self.decoder(encoded)
        return decoded


class AEHandler():
    def __init__(self, load=True):
        self.model_files = './ae_model'
        if load:
            self.ae = keras.models.load_model(self.model_files)
        else:
            self.ae = Autoencoder(64)

        self.x_train, self.x_test = self.load_data()

    def load_data(self):
        (x_train, _), (x_test, _) = fashion_mnist.load_data()
        x_train = x_train.astype('float32') / 255.
        x_test = x_test.astype('float32') / 255.
        return x_train, x_test

    def train(self):
        self.ae.compile(optimizer='adam', loss=losses.MeanSquaredError())
        self.ae.fit(self.x_train, self.x_train,
                    epochs=10,
                    shuffle=True,
                    validation_data=(self.x_test, self.x_test))
        self.ae.save(self.model_files)

    def test(self):
        encoded_imgs = self.ae.encoder(self.x_test).numpy()
        decoded_imgs = self.ae.decoder(encoded_imgs).numpy()

        n = 10
        plt.figure(figsize=(20, 4))
        for i in range(n):
            # display original
            ax = plt.subplot(2, n, i + 1)
            plt.imshow(self.x_test[i])
            plt.title("original")
            plt.gray()
            ax.get_xaxis().set_visible(False)
            ax.get_yaxis().set_visible(False)

            # display reconstruction
            ax = plt.subplot(2, n, i + 1 + n)
            plt.imshow(decoded_imgs[i])
            plt.title("reconstructed")
            plt.gray()
            ax.get_xaxis().set_visible(False)
            ax.get_yaxis().set_visible(False)
        plt.show()


if __name__ == "__main__":
    print(f'{__file__} main')

    aeh = AEHandler(load=True)
    # aeh.train()
    aeh.test()

    bk = BinanceKlines('../../../data/binance_uncompressed/')

    symbol = 'ADAUSDT'
    start_ms = get_ms_from_str('2022-04-01')
    end_ms = get_ms_from_str('2022-05-01')

    plot = True
    day_ms = 1 * 24 * 60 * 60 * 1000
    min_ms = 60 * 1000
    candle_df = bk.get_df(symbol, start_ms, start_ms + 1 * day_ms, Client.KLINE_INTERVAL_1MINUTE)

