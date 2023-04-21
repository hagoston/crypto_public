import logging
import json
import ast
import time
import ctypes
import os
import datetime
import asyncio

import gate_ws as gws
import multiprocessing as mp

from enum import IntEnum
from gate_ws.spot import SpotOrderBookUpdateChannel
from gate_api import ApiClient, SpotApi, WalletApi, Configuration, Order
from multiprocessing import Process, Manager
from LocalOrderBook import LocalOrderBook
from gate_api.exceptions import ApiException, GateApiException


class BuyStates(IntEnum):
    INIT = 0,
    PARTIAL_FILL = 1,
    DONE = 2,
    ERROR = 3


class SellStates(IntEnum):
    INIT = 0,
    DONE = 1,
    ERROR = 2


def store_mem(odict):
    symbol = odict['symbol']
    name = odict['name']
    fname = f'{symbol}_{name}.json'
    with open(fname, 'w') as f:
        json.dump(odict, f, indent=4)


def load_mem(name, symbol):
    # fname = f'{symbol}_{name}.json'
    # if os.path.isfile(fname):
    #     with open(fname, 'r+') as f:
    #         try:
    #             return json.load(f)
    #         except:
    #             pass
    return {
        'symbol': symbol,
        'name': name
    }


class GateioTrader:
    def __init__(self):
        # load config from file
        data_json_file = 'data.json'
        with open(data_json_file) as json_file:
            self.data = json.load(json_file)
        # must have param check
        try:
            logging.info(f"trading parameters:"
                         f"\n\tpairing={self.data['trading_params']['gateio']['pairing']}"
                         f"\n\tusd_to_spend={self.data['trading_params']['gateio']['usd_to_spend']}$"
                         f"\n\ttsl={self.data['trading_params']['gateio']['trailing_stop_loss']}%")
        except:
            logging.error('missing config parameter')
            assert False

        # load gateio stuff
        auth_conf = Configuration(key=self.data['private_data']['gateio']['api_key'],
                                  secret=self.data['private_data']['gateio']['secret_key'])
        self.spot_api = SpotApi(ApiClient(auth_conf))
        # self.wallet_api = WalletApi(ApiClient(auth_conf))

        # multiprocessing stuff
        self.manager = Manager()
        # dictionary to hold shared stuff
        self.mp_dict = self.manager.dict()
        self.mp_dict['currency_list'] = self.manager.list()         # supported coins on gate.io
        self.mp_dict['last_trade'] = None                           # latest trade with announcement_coin
        self.mp_dict['listed_coins'] = self.manager.dict()          # newly listed coins

        # thread stopper
        self.mp_exit_loop = mp.Value(ctypes.c_bool, False)

        # initialize default connection, which connects to spot WebSocket V4
        self.gws_conn = gws.Connection(gws.Configuration())

        # start processes
        ths = []
        ths.append(mp.Process(target=self.currencies_thread))
        # ths.append(mp.Process(target=self.handle_new_announcement_trigger, args=('FLUX', )))
        for th in ths:
            th.start()

    def currencies_thread(self):
        """
        get and keep updated a list of all currencies supported on gate io
        """
        update_interval = 5 * 60
        while not self.mp_exit_loop.value:
            logging.info('update supported currency list from gate.io')
            all_currencies = ast.literal_eval(str(self.spot_api.list_currencies()))
            currency_list = self.manager.list()
            for currency in all_currencies:
                if not currency['trade_disabled']:
                    currency_list.append(currency['currency'])
            # store into shared dict
            self.mp_dict['currency_list'] = currency_list
            # also write into file
            with open('currencies.json', 'w') as f:
                json.dump(list(currency_list), f, indent=4)
            logging.info('supported currency list updated')
            time.sleep(update_interval)

    def get_currency_list(self):
        return self.mp_dict['currency_list']

    async def sell_thread(self, coin_symbol, order_book):
        """
        handle all sell related stuff
        """
        logging.info(f'started for {coin_symbol}', extra={'TELEGRAM': 'COIN_ANNOUNCEMENT'})

        update_interval = 0
        while not self.mp_exit_loop.value:
            # loop sleep
            await asyncio.sleep(update_interval)
            if not update_interval:
                update_interval = 0.1

            if coin_symbol not in self.mp_dict['listed_coins']:
                logging.error(f'{coin_symbol} not in listed_coins dict')
                return

            if self.mp_dict['listed_coins'][coin_symbol]['buy']['state'] == BuyStates.ERROR:
                logging.error(f'{coin_symbol} buy failed. exit sell thread')
                self.mp_dict['listed_coins'][coin_symbol]['sell']['state'] == SellStates.ERROR
                return

            if self.mp_dict['listed_coins'][coin_symbol]['buy']['state'] == BuyStates.PARTIAL_FILL or \
               self.mp_dict['listed_coins'][coin_symbol]['buy']['state'] == BuyStates.DONE:
                # calculate average price
                avg_price = self.mp_dict['listed_coins'][coin_symbol]['buy']['total_volume'] / self.mp_dict['listed_coins'][coin_symbol]['buy']['total_amount']
                
                pass
            else:
                # wait for buy
                continue

    async def buy_thread(self, coin_symbol, order_book, order_book_ready_event):
        """
        handle all buying related stuff
        """
        update_interval = 0
        order = load_mem('order', coin_symbol)
        session = load_mem('session', coin_symbol)

        logging.info(f'started for {coin_symbol}', extra={'TELEGRAM': 'COIN_ANNOUNCEMENT'})

        while not self.mp_exit_loop.value:
            # loop sleep
            await asyncio.sleep(update_interval)
            if not update_interval:
                update_interval = 0.1

            # check gateio currency list validity
            if not self.mp_dict['currency_list']:
                logging.error('currency_list not ready')
                continue

            # check coin is supported
            if coin_symbol not in self.mp_dict['currency_list']:
                logging.warning(f'{coin_symbol=} is not supported on gate io, waiting for new trigger..',
                                extra={'TELEGRAM': 'COIN_NOT_SUPPORTED'})
                return

            # wait for order book
            wait_for_order_book = not order_book_ready_event.is_set()
            await order_book_ready_event.wait()
            if wait_for_order_book:
                logging.info(f'order book received for {coin_symbol}')

            # create new session for coin
            if coin_symbol not in session:
                session[coin_symbol] = {}
                session[coin_symbol].update({'total_volume': 0})
                session[coin_symbol].update({'total_amount': 0})
                session[coin_symbol].update({'total_fees': 0})
                session[coin_symbol]['orders'] = []

            # cpy to local variable
            test_mode = self.data['trading_params']['gateio']['test_mode']
            pairing = self.data['trading_params']['gateio']['pairing']
            trailing_stop_loss = self.data['trading_params']['gateio']['trailing_stop_loss']
            usd_to_spend = self.data['trading_params']['gateio']['usd_to_spend']
            usd_to_spend -= session[coin_symbol]['total_volume']  # remaining money to spend

            # list prices to fill usd_to_spend
            order_info = {
                'sum_usd': 0.0,
                'sum_quantity': 0.0,
                'order_book': []
            }
            for a in order_book.asks:
                price, quantity = float(a.price), float(a.amount)
                # print(price, quantity)
                remaining_usd = usd_to_spend - order_info['sum_usd']
                quantity_to_buy = quantity
                if price * quantity >= remaining_usd:
                    quantity_to_buy = remaining_usd / price
                order_info['order_book'].append([price, quantity_to_buy])
                order_info['sum_usd'] += price * quantity_to_buy
                order_info['sum_quantity'] += quantity_to_buy
                if order_info['sum_usd'] >= usd_to_spend:
                    # filled
                    order_info['average_price'] = order_info['sum_usd'] / order_info['sum_quantity']
                    break

            # set price to highest price in order book list + 5%
            price_to_fill = order_info['order_book'][-1][0] * 1.05
            price_avg = order_info['average_price']
            amount = order_info['sum_quantity']         # at average price

            # initialize order data object
            if coin_symbol not in order:
                order[coin_symbol] = {}
                order[coin_symbol]['_amount'] = f'{amount}'
                order[coin_symbol]['_left'] = f'{amount}'
                order[coin_symbol]['_fee'] = f'{0}'
                order[coin_symbol]['_status'] = 'init'
                if test_mode:
                    # for testing
                    if len(session[coin_symbol]['orders']) == 0:
                        order[coin_symbol]['_status'] = 'test_partial_fill_order'
                    else:
                        order[coin_symbol]['_status'] = 'cancelled'

            # to local variable
            left = float(order[coin_symbol]['_left'])
            status = order[coin_symbol]['_status']

            # partial fill
            if left - amount != 0:
                amount = left

            logging.info(f'starting buy place_order with: {coin_symbol}-{pairing} '
                         f'| {usd_to_spend=} '
                         f'| {amount=} x {price_avg=} '
                         f'| side = buy '
                         f'| {status=}', extra={'TELEGRAM': 'BUY_START'})

            try:
                # just in case...stop buying more than our config amount
                assert amount * float(price_avg) <= float(usd_to_spend)
                # todo check balance
                # price_to_fill vs price_avg

                if test_mode:
                    # print('min amount = ', self.get_min_amount(coin_symbol, pairing))
                    # test trade
                    if order[coin_symbol]['_status'] == 'cancelled':
                        status = 'closed'
                        left = 0
                        fee = f'{float(amount) * .002}'
                    else:
                        status = 'cancelled'
                        left = f'{float(amount) * .66}'
                        fee = f'{float(amount - float(left)) * .002}'

                    order[coin_symbol] = {
                        '_fee_currency': coin_symbol,
                        '_price': f'{price_avg}',
                        '_amount': f'{amount}',
                        '_filled_total': f'{price_avg * (float(amount)-float(left))}',
                        '_time': time.time(),
                        '_tsl': trailing_stop_loss,
                        '_id': 'test-order',
                        '_text': 'test-order',
                        '_create_time': time.time(),
                        '_update_time': time.time(),
                        '_currency_pair': f'{coin_symbol}_{pairing}',
                        '_status': status,
                        '_type': 'limit',
                        '_account': 'spot',
                        '_side': 'buy',
                        '_iceberg': '0',
                        '_left': f'{left}',
                        '_fee': fee
                    }
                    order[coin_symbol]["_price_avg"] = price_avg
                    logging.info('PLACING TEST ORDER')
                    logging.info(order[coin_symbol])
                else:
                    # live order
                    order_status = self.place_order(coin_symbol, pairing, amount, 'buy', price_to_fill)
                    order_status_dict = order_status.__dict__
                    order_status_dict.pop("local_vars_configuration")
                    order[coin_symbol] = order_status_dict
                    order[coin_symbol]['_tsl'] = trailing_stop_loss
                    order[coin_symbol]["_price_avg"] = float(order_status.filled_total) / (float(order_status.amount)-float(order_status.left))
                    logging.debug('place_order finished')
            except Exception as e:
                self.mp_dict['listed_coins'][coin_symbol]['buy']['state'] = BuyStates.ERROR
                logging.error(e)
            else:
                # there was no exception
                order_status = order[coin_symbol]['_status']
                logging.info(
                    f'order created on {coin_symbol} at a average price of '
                    f'{order[coin_symbol]["_price_avg"]} each. {order_status=}',
                    extra={'TELEGRAM': 'BUY_ORDER_CREATED'})

                if order_status == "closed":
                    order[coin_symbol]['_amount_filled'] = order[coin_symbol]['_amount']
                    session[coin_symbol]['total_volume'] += float(order[coin_symbol]['_filled_total'])
                    session[coin_symbol]['total_amount'] += float(order[coin_symbol]['_amount'])
                    session[coin_symbol]['total_fees'] += float(order[coin_symbol]['_fee'])
                    session[coin_symbol]['orders'].append(order[coin_symbol])

                    # update order to sum all amounts and all fees
                    # this will set up our sell order for sale of all filled buy orders
                    tf = session[coin_symbol]['total_fees']
                    ta = session[coin_symbol]['total_amount']
                    order[coin_symbol]['_fee'] = f'{tf}'
                    order[coin_symbol]['_amount'] = f'{ta}'

                    # this is what sell thread reads
                    self.mp_dict['listed_coins'][coin_symbol]['buy']['state'] = BuyStates.DONE
                    self.mp_dict['listed_coins'][coin_symbol]['buy']['total_amount'] = session[coin_symbol]['total_amount']
                    self.mp_dict['listed_coins'][coin_symbol]['buy']['total_volume'] = session[coin_symbol]['total_volume']

                    # write out dicts
                    store_mem(session)
                    store_mem(order)

                    logging.info(f'buy order on {coin_symbol} closed', extra={'TELEGRAM': 'BUY_FILLED'})
                    return
                else:
                    if order_status == "cancelled" and \
                       float(order[coin_symbol]['_amount']) > float(order[coin_symbol]['_left']) > 0:

                        # partial order. Change qty and fee_total in order and finish any remaining balance
                        partial_amount = float(order[coin_symbol]['_amount']) - float(order[coin_symbol]['_left'])
                        partial_fee = float(order[coin_symbol]['_fee'])

                        order[coin_symbol]['_amount_filled'] = f'{partial_amount}'
                        session[coin_symbol]['total_volume'] += float(order[coin_symbol]['_filled_total'])
                        session[coin_symbol]['total_amount'] += partial_amount
                        session[coin_symbol]['total_fees'] += partial_fee
                        session[coin_symbol]['orders'].append(order[coin_symbol])

                        self.mp_dict['listed_coins'][coin_symbol]['buy']['state'] = BuyStates.PARTIAL_FILL
                        self.mp_dict['listed_coins'][coin_symbol]['buy']['total_amount'] = session[coin_symbol]['total_amount']
                        self.mp_dict['listed_coins'][coin_symbol]['buy']['total_volume'] = session[coin_symbol]['total_volume']

                        logging.info(f"partial fill order detected. {order_status=} "
                                     f"| {partial_amount=} out of {amount=} "
                                     f"| {partial_fee=} "
                                     f"| {price_avg=}")

                    # order not filled, try again.
                    logging.info(f"clearing order with a status of {order_status}. waiting for 'closed' status")
                    order.pop(coin_symbol)      # reset for next iteration
                    update_interval = 0         # skip sleeping

    def get_min_amount(self, base, quote):
        try:
            min_amount = self.spot_api.get_currency_pair(currency_pair=f'{base}_{quote}').min_quote_amount
        except Exception as e:
            logging.error(e)
        else:
            return min_amount

    def get_order_book(self, base, quote, order_depth=50):
        # .asks[0]['price', 'quantity'] - lowest price to buy
        # .bids[0]['price', 'quantity'] - highest price to sell
        return self.spot_api.list_order_book(currency_pair=f'{base.upper()}_{quote.upper()}',
                                             limit=order_depth)

    def get_last_price(self, base, quote, return_price_only):
        trades = self.spot_api.list_trades(currency_pair=f'{base.upper()}_{quote.upper()}', limit=1)
        assert len(trades) == 1
        trade = trades[0]

        last_trade = self.mp_dict['last_trade']
        if last_trade and last_trade.id > trade.id:
            logging.info(f"trade id mismatch for {base} re-try")
            time.sleep(0.1)
            return self.get_last_price(base=base, quote=quote, return_price_only=return_price_only)
        else:
            self.mp_dict['last_trade'] = trade
        if return_price_only:
            return trade.price

        create_time_ms = datetime.datetime.fromtimestamp(float(trade.create_time_ms) / 1000.0)
        create_time_formatted = create_time_ms.strftime('%Y-%m-%d %H:%M:%S.%f')
        logging.info(f"{trade.currency_pair} | id={trade.id} | create_time={create_time_formatted} | "
                     f"side={trade.side} | amount={trade.amount} | price={trade.price}")
        return trade

    def place_order(self, base, quote, amount, side, price):
        try:
            order = Order(amount=str(amount),
                          price=price,
                          side=side,
                          currency_pair=f'{base}_{quote}',
                          time_in_force='ioc')
            order = self.spot_api.create_order(order)
            logging.info(
                f"PLACE ORDER: {order.side} | {order.id} | {order.account} | {order.type} | {order.currency_pair} | {order.status} | "
                f"amount={order.amount} | price={order.price} | left={order.left} | filled_total={order.filled_total} | "
                f"fill_price={order.fill_price} | fee={order.fee} {order.fee_currency}")
        except Exception as e:
            logging.error(e)
            raise
        else:
            return order

    def get_spot_price_triggered_order(self, order_id):
        try:
            # Get a single order
            api_response = self.spot_api.get_spot_price_triggered_order(order_id)
        except GateApiException as ex:
            logging.error("Gate api exception, label: %s, message: %s\n" % (ex.label, ex.message))
        except ApiException as e:
            logging.error("Exception when calling SpotApi->get_spot_price_triggered_order: %s\n" % e)
        else:
            return api_response
        return None
            
    @staticmethod
    def mp_dict_2_dict(mp_dict):
        normal_dict = {}
        for key, value in mp_dict.items():
            if isinstance(value, mp.managers.DictProxy):
                normal_dict[key] = GateioTrader.mp_dict_2_dict(value)
            elif isinstance(value, mp.managers.ListProxy):
                normal_dict[key] = list(value)
            else:
                normal_dict[key] = value
        return normal_dict

    def dict_2_mp_dict(self, normal_dict):
        mp_dict = self.manager.dict()
        for key, value in normal_dict.items():
            if isinstance(value, dict):
                mp_dict[key] = self.dict_2_mp_dict(value)
            elif isinstance(value, list):
                mp_dict[key] = self.manager.list(value)
            else:
                mp_dict[key] = value
        return mp_dict

    @staticmethod
    def print_dict_types(d, tab_cnt=0):
        for key, value in d.items():
            print('\t' * tab_cnt + key + ' : ' + str(type(value)))
            if isinstance(value, dict) or isinstance(value, mp.managers.DictProxy):
                GateioTrader.print_dict_types(value, tab_cnt+1)

    def handle_new_announcement_trigger(self, coin_symbol):
        time.sleep(5)

        # initialize local order book
        coin_symbol = coin_symbol.upper()
        coin_pair = f"{coin_symbol}_{self.data['trading_params']['gateio']['pairing'].upper()}"
        logging.info(f'initialize local order book with {coin_pair} pair')

        order_book = LocalOrderBook(coin_pair)
        channel = SpotOrderBookUpdateChannel(self.gws_conn, order_book.ws_callback)
        channel.subscribe([coin_pair, "100ms"])

        # events
        order_book_ready_event = asyncio.Event()

        # create new element into shared
        self.mp_dict['listed_coins'][coin_symbol] = self.manager.dict({
            'buy': self.manager.dict({
                'total_amount': 0,
                'total_volume': 0,
                'state': BuyStates.INIT
            }),
            'sell': self.manager.dict({
                'total_amount': 0,
                'total_volume': 0,
                'state': SellStates.INIT
            })
        })

        # start threads
        loop = asyncio.get_event_loop()
        loop.create_task(order_book.run(order_book_ready_event))
        loop.create_task(self.gws_conn.run())
        loop.create_task(self.buy_thread(coin_symbol, order_book, order_book_ready_event))
        loop.create_task(self.sell_thread(coin_symbol, order_book))

        logging.info(f'buy_thread started for {coin_symbol}')

        try:
            loop.run_forever()
        except KeyboardInterrupt:
            for task in asyncio.Task.all_tasks(loop):
                task.cancel()
            loop.close()
