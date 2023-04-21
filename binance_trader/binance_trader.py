import json
import os
import datetime
import time
import multiprocessing as mp
from binance.client import Client
from icecream import ic
import ctypes
import threading
from threading import Thread
from binance import ThreadedWebsocketManager
import logging
from random import randint
import telegram_send


class LogHandler(logging.Handler):
    def emit(self, record):
        ts = record.asctime
        msg = record.msg
        if 'DBGLOG' not in msg and \
           'WS_TICKER' not in msg:
            telegram_send.send(messages=[msg], parse_mode='markdown', disable_web_page_preview='True')
            print(f'{ts} {msg}')


class BinanceTrader():
    def __init__(self):
        # global switches
        self._ARMED_ = True
        self.percentage = 100.0

        # logger
        logdate = datetime.datetime.now().strftime("%Y%m%d_%H%M%S.%f")
        if not os.path.exists('./log'):
            os.makedirs('./log')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s.%(msecs)03d|%(levelname)s|%(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.FileHandler(
                    "./log/binance_trader" + "_" + logdate + ".log", mode='w',
                    encoding=None, delay=False),
                logging.StreamHandler()
            ]
        )
        # logging.root.addHandler(LogHandler())

        # load binance api key
        with open('data.json') as json_file:
            data = json.load(json_file)
            self.api_key = data['private_data']['binance']['api_key']
            self.secret_key = data['private_data']['binance']['secret_key']

        # start websocket
        self.twm_stream_name = None
        self.twm = ThreadedWebsocketManager(api_key=self.api_key, api_secret=self.secret_key)
        self.twm.start()

        # instantiate client
        self.client = Client(self.api_key, self.secret_key)
        # get binance rate limits
        #   https://python-binance.readthedocs.io/en/latest/overview.html?highlight=API%20Rate%20Limit#api-rate-limit
        try:
            self.exchange_info = self.client.get_exchange_info()
            rate_limits_resp = self.exchange_info['rateLimits']
            rate_limits = {}
            for lim in rate_limits_resp:
                if 'MINUTE' == lim['interval']:
                    tmp = lim['limit'] / (lim['intervalNum'] * 60)
                    if not 'minute' in rate_limits or tmp < rate_limits['minute']:
                        rate_limits['minute'] = tmp
                elif 'SECOND' == lim['interval']:
                    rate_limits['second'] = lim['limit'] / lim['intervalNum']
                elif 'DAY' == lim['interval']:
                    rate_limits['day'] = lim['limit'] / (lim['intervalNum'] * 60 * 60 * 24)

            self.max_rate = min(rate_limits['minute'], rate_limits['second'])
        except:
            self.max_rate = 5.0

        # token trade stuff
        self.step_size = 0.01

        # log
        ic.configureOutput(prefix=self.log_prefix)
        ic.configureOutput(includeContext=True)
        ic.enable()
        # multiprocess variables
        self.exit_loop = mp.Value(ctypes.c_bool, False)
        self.free_token_balance = mp.Value('f', -1.0)
        # events
        self._action_trigger_event_ = threading.Event()
        self._balance_trigger_event_ = threading.Event()

    def start_instant_sell_process(self, token_symbol, base_token_symbol):
        symbol = (token_symbol+base_token_symbol).upper()
        symbol_info = self.client.get_symbol_info(symbol)

        logging.info(f'LOG|get_symbol_info({symbol})')
        try:
            for key, value in symbol_info.items():
                logging.info(f'LOG|\t{key}: {value})')
                print(key, value)
            for key, value in symbol_info['filters'][2].items():
                logging.info(f'LOG|\t{key}: {value})')
                print(key, value)
        except:
            logging.info(f'LOG|get_symbol_info({symbol}) failed')
            pass

        trade_th = Thread(target=self.process_action_trigger, args=(token_symbol, base_token_symbol,))
        trade_th.start()

        isell_th = Thread(target=self.get_balance_th, args=(token_symbol, base_token_symbol,))
        isell_th.start()

        ws_th = Thread(target=self.start_websocket, args=(token_symbol.lower()+base_token_symbol.lower(),))
        ws_th.start()

        isell_th.join()
        ws_th.join()

    def process_action_trigger(self, token_symbol, base_token_symbol):
        logging.info('starting process_action_trigger with token_symbol=' + token_symbol + ', base_token_symbol=' + base_token_symbol)

        # wait for my balance available
        self._balance_trigger_event_.wait()

        logging.info('LOG|###### balance trigger set')

        # wait for available token pair
        self._action_trigger_event_.wait()
        # symbol
        symbol = (token_symbol+base_token_symbol).upper()

        logging.info('LOG|###### ALL TRIGGER SET FOR SELLING ' + symbol)
        logging.info('LOG|######\tfree_token_balance=' + str(self.free_token_balance.value))

        # reduce quantity by percentage
        quantity = self.free_token_balance.value * self.percentage / 100.0
        # set precision
        precision = 2
        # get quantity in str with specified precision
        quantity_str = "{:0.0{}f}".format(quantity, precision)
        logging.info('ORDER|quantity_str=' + quantity_str)

        # MARKET SELL
        if self._ARMED_:
            if 1:
                order = self.client.order_limit_sell(
                    symbol=symbol,
                    quantity=quantity_str,
                    price='47.32')
            else:
                order = self.client.order_market_sell(
                    symbol=symbol,
                    quantity=quantity_str)
            logging.info('ORDER|placed: ' + str(order))
        else:
            logging.info('ORDER|skip order self._ARMED_==False')

        my_trades = []
        while not len(my_trades):
            my_trades = self.client.get_my_trades(symbol=symbol)
            for t in my_trades:
                logging.info('MY_TRADES|'+str(t))
            time.sleep(1)

        # keep alive for logging
        logging.info('LOG|all done - keep alive for logging')
        time.sleep(120)
        logging.info('LOG|shutting down')

        # stop all
        self.exit_loop.value = True
        if self.twm_stream_name:
            self.twm.stop_socket(self.twm_stream_name)
            self.twm.stop()

    def get_balance_th(self, token_symbol, base_token_symbol='USDT'):
        logging.info('LOG|starting get_balance_th with token_symbol=' + token_symbol + ', base_token_symbol=' + base_token_symbol)
        prev_loop_time_ = 0
        # loop_interval_ = 1.0 / self.max_rate
        loop_interval_ = 5.0
        telegram_send.send(messages=['get_balance_th() started'])

        while not self.exit_loop.value:
            logging.info('DBGLOG|get_balance_th loop')

            # get balance for symbol
            if not self._balance_trigger_event_.is_set():
                try:
                    balance = self.client.get_asset_balance(asset=token_symbol)
                    free_token_balance_ = float(balance['free'])
                    if free_token_balance_ > 0:
                        self.free_token_balance.value = free_token_balance_
                        self._balance_trigger_event_.set()
                        logging.info('LOG|got free_token_balance for ' + token_symbol + ' (' + str(self.free_token_balance.value) + ')')
                        # exit
                        telegram_send.send(messages=[f'got free_token_balance for {token_symbol} ({self.free_token_balance.value})'])
                        return
                except:
                    pass

            # keep max rate
            rand_sleep = randint(90, 110) * loop_interval_ / 100
            time.sleep(rand_sleep)

    def websocket_handle_msg(self, msg):
        if 'e' in msg:  # error
            try:
                print('websocket ERROR: ', msg)
            except:
                pass
            return
        if 'data' in msg and 's' in msg['data']:
            stream = 'unknown'
            if 'stream' in msg:
                stream = msg['stream']
            if not self._action_trigger_event_.is_set():
                self._action_trigger_event_.set()
                logging.info('LOG|websocket message received for ' + stream + ':: quantity_str')
            logging.info('WS_TICKER|' + str(msg))

    def start_websocket(self, ticker_pair='bnbusdt'):
        logging.info('LOG|start_websocket() with ticker_pair=' + ticker_pair)
        # streams = ['!bookTicker']
        streams = [ticker_pair.lower()+'@bookTicker']
        self.twm_stream_name = self.twm.start_multiplex_socket(callback=self.websocket_handle_msg, streams=streams)

    def on_log(record):
        print(record.levelname, ":", record.getMessage())
        return True

    def log_prefix(self):
        return datetime.datetime.now().strftime("%H%M%S.%f ")

def main():
    bt = BinanceTrader()
    # bt.start_instant_sell_process('BAR', 'USDT')
    # bt.start_instant_sell_process('BNB', 'USDT')
    # bt.start_instant_sell_process('BTC', 'USDT')
    # bt.start_instant_sell_process('LAZIO', 'USDT')
    # bt.start_instant_sell_process('DAR', 'USDT')
    bt.start_instant_sell_process('PORTO', 'USDT')

if __name__ == '__main__':
    main()

