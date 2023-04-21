#!/usr/bin/python3

import os
import sys
import json
import datetime
import logging
import time
import telegram_send
import requests
import re
import multiprocessing as mp
import cloudscraper
import random
import string
from threading import Thread
from bs4 import BeautifulSoup
from eth_utils import remove_0x_prefix, to_checksum_address

from GateioTrader import GateioTrader


class LogHandler(logging.Handler):
    def emit(self, record):
        ts = record.asctime
        msg = record.msg
        try:
            if hasattr(record, 'TELEGRAM'):
                key = getattr(record, 'TELEGRAM')
                telegram_send.send(messages=[msg], parse_mode='markdown', disable_web_page_preview='True')
        except KeyError:
            pass
        # if 'TG|' in msg:
        #     msg = msg.replace('TG|', '')
        #     telegram_send.send(messages=[msg], parse_mode='markdown', disable_web_page_preview='True')


class BinanceListingBot:
    def __init__(self):
        # load config from file
        data_json_file = 'data.json'
        with open(data_json_file) as json_file:
            self.data = json.load(json_file)
            self.config_armed = self.data['config']['armed']
            self.config_telegram_enabled = self.data['config']['enable_telegram']
            self.poll_interval = self.data['config']['binance_announcement_poll_interval']
            try:
                self.proxy = self.data['private_data']['proxy']['brightdata']
            except:
                self.proxy = None

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
                    "./log/binance_listing_bot" + "_" + logdate + ".log", mode='w',
                    encoding=None, delay=False),
                logging.StreamHandler()
            ]
        )

        # trader instance
        self.trader = GateioTrader()

        # main web3bsc class
        try:
            copy_trading_enabled = self.data['trading_params']['copy_trading']['enabled']
        except:
            copy_trading_enabled = False
        if copy_trading_enabled:
            sys.path.append('../shitcoin/utils')
            sys.path.append('../shitcoin/web3bsc/reward_token')
            sys.path.append('../shitcoin/web3bsc')
            from web3bsc import Web3BSC
            self.web3bsc = Web3BSC(data_json=data_json_file)
            # start BSC block listener
            ths = []
            ths.append(Thread(target=self.web3bsc.poll_transactions))
            for th in ths:
                th.start()

        # direct web3
        self.dw3 = {
            'bsc': None,
            'eth': None
        }
        try:
            sys.path.append('../shitcoin/web3bsc')
            sys.path.append('../shitcoin/web3bsc/reward_token')
            from directWeb3 import DirectWeb3
            from db_handler import DBHandler
            for network_id in range(1, 3):
                if network_id == 1:
                    db_file = 'dividend_token_BSC.db'
                else:
                    db_file = 'dividend_token_ETH.db'
                db_handler = DBHandler(db_file, network_id)
                dex_info = db_handler.get_dex_info(network_id)[0]
                dex_info['rpc'] = db_handler.get_network_rpc(network_id)
                dex_info['base_token_addr'] = db_handler.get_network_base_token_address(network_id)
                dex_info['usd_token_addr'] = db_handler.get_network_usd_token_address(network_id)
                if network_id == 1:
                    self.dw3['bsc'] = DirectWeb3(dex_info)
                else:
                    self.dw3['eth'] = DirectWeb3(dex_info)
        except:
            logging.info('dw3 failed to load')

        # fw to telegram if enabled
        if self.config_telegram_enabled:
            logging.root.addHandler(LogHandler())

        # container to hold listing articles
        self.article_dict = {}
        # is first poll done
        self.initialized = False
        # queue for new article findings; any results from threads
        self.poll_result_queue = mp.Queue()
        # statistic
        self.stat = {
            'meas_start_time': time.time(),
            'meas_poll_cnt': 0,
            'poll_cnt': 0,
            'article': {
                'cnt': 0,
                'eth_cnt': 0,
                'bsc_cnt': 0,
                'unknown_network_cnt': 0
            }
        }
        # webpage scraper to bypass Cloudflare's anti-bot page
        self.scraper = cloudscraper.create_scraper()

        # create proxy pool
        logging.info(f'binance new listing listener bot started..', extra={'TELEGRAM': 'INFO'})

        # call poll to be initialized
        initial_article_cnt = 0
        if self.data['config']['dump_old_listings']:
            for i in range(1, 50):
                print(i)
                request_url = self.generate_random_poll_url(page_no=i, force_max_page_size=True)
                initial_article_cnt += self.poll(request_url, self.poll_result_queue)
        else:
            # binance site to poll
            request_url = self.generate_random_poll_url(force_max_page_size=True)
            initial_article_cnt = self.poll(request_url, self.poll_result_queue)
        while initial_article_cnt:
            article = self.poll_result_queue.get()
            if article:
                self.process_new_article(article)
                initial_article_cnt -= 1
            time.sleep(0.1)
        if self.stat['article']['cnt']:
            acnt = self.stat['article']['cnt']
            bsc_cnt = self.stat['article']['bsc_cnt']
            eth_cnt = self.stat['article']['eth_cnt']
            unknown_network_cnt = self.stat['article']['unknown_network_cnt']
            logging.info(f'{acnt} article processed, '
                         f'{100*bsc_cnt/acnt:.2f}% ({bsc_cnt}) BSC, '
                         f'{100*eth_cnt/acnt:.2f}% ({eth_cnt}) ETH, '
                         f'{100*unknown_network_cnt/acnt:.2f}% ({unknown_network_cnt}) unknown network')
        self.initialized = True

    @staticmethod
    def generate_random_poll_url(page_no=1, force_max_page_size=False):
        # generate random query/params to help prevent caching
        try:
            max_page_size = 20
            rand_page_size = random.randint(5, max_page_size)
            if force_max_page_size:
                rand_page_size = max_page_size
            letters = string.ascii_letters
            random_string = ''.join(random.choice(letters) for i in range(random.randint(10, 20)))
            random_number = random.randint(1, 99999999999999999999)
            curr_time = time.time()
            queries = ["type=1", "catalogId=48", f"pageNo={page_no}", f"pageSize={str(rand_page_size)}",
                       f"rnd={str(curr_time)}",
                       f"{random_string}={str(random_number)}"]
            random.shuffle(queries)
            base_url = 'https://www.binancezh.com/gateway-api/v1/public/cms/article/list/query'
            if int(str(int(curr_time * 10))[-1]) < 5:
                base_url = 'https://www.binance.com/bapi/composite/v1/public/cms/article/list/query'
            request_url = base_url + f"?{'&'.join(q for q in queries)}"
        except:
            request_url = 'https://www.binance.com/bapi/composite/v1/public/cms/article/list/query?type=1&pageNo=1&pageSize=10'

        return request_url

    @staticmethod
    def poll(url, result_queue, known_article_ids=[], proxy=None):
        article_cnt = 0
        try:
            response = requests.get(url, proxies={"http": proxy, "https": proxy})
            if not response.ok:
                logging.warning(f'request failed with {response.status_code} {response.reason}')
                return
            response = response.json()
            if response['success']:
                for catalog in response['data']['catalogs']:
                    # catalogId == 48 == New Cryptocurrency Listing
                    if catalog['catalogId'] == 48:
                        # print(len(catalog['articles']))
                        for article in catalog['articles']:
                            if 'will list' in article['title'].lower():
                                # assuming unique id
                                article_id = int(article['id'])
                                if article_id not in known_article_ids:
                                    # NEW LISTING FOUND
                                    result_queue.put(article)
                                    logging.info(f'new listing article found:: {article["title"]}')
                                    article_cnt += 1
            else:
                logging.warning('get request failed')
        except:
            e = sys.exc_info()[0]
            logging.error('get request exception::' + e.__name__ + ', ' + e.__doc__.replace('\n', ''))
        return article_cnt

    def poll_loop(self):
        loop_sleep_time = 0.01              # 10ms sleep
        prev_poll_time = 0                  # for measuring poll_interval
        prev_info_log_time = time.time()    # for measuring logging period

        while True:
            # read all message from result queue
            while not self.poll_result_queue.empty():
                # get one element from queue
                article = self.poll_result_queue.get()
                # process new article
                self.process_new_article(article)

            # start new poll
            if time.time() - prev_poll_time + loop_sleep_time > self.poll_interval:
                # send known article ids to be able to ignore them
                known_article_ids = list(self.article_dict.keys())
                # start thread
                request_url = self.generate_random_poll_url()
                th = mp.Process(target=self.poll,
                                args=(request_url, self.poll_result_queue, known_article_ids, self.proxy, ))
                th.start()
                # count polls
                self.stat['poll_cnt'] += 1
                prev_poll_time = time.time()

            # logging
            log_interval = 30   # sec
            if time.time() - prev_info_log_time > log_interval:
                logging.info(f'binance announcement poll cnt sum = {self.stat["poll_cnt"]}, '
                             f'freq = {(self.stat["poll_cnt"]-self.stat["meas_poll_cnt"]) / (time.time()-self.stat["meas_start_time"]):.2f} Hz')
                # reset statistic measurement
                self.stat['meas_poll_cnt'] = self.stat["poll_cnt"]
                self.stat['meas_start_time'] = time.time()
                prev_info_log_time = time.time()

            # loop sleep
            time.sleep(loop_sleep_time)

    def process_new_article(self, article):
        # get current timestamp
        current_epoch_ms = time.time() * 1000
        # parse article info
        article_id = int(article['id'])
        article_code = article['code']
        article_title = article['title']
        article_release_date = article['releaseDate']

        # create url
        article_url = f'https://www.binance.com/en/support/announcement/{article_code}'

        # save this article into dict
        self.article_dict[article_id] = article

        # parse article content
        token_info = self.article_parser(article_title, article_url)
        if not token_info['symbol']:
            logging.error(f'process new article():: missing symbol, exiting..'
                          f'\n\t{article_title}'
                          f'\n\t{article_url}')
            return

        # update statistic
        self.stat['article']['cnt'] += 1
        self.stat['article']['eth_cnt'] += 1 if token_info['eth_addr'] else 0
        self.stat['article']['bsc_cnt'] += 1 if token_info['bsc_addr'] else 0
        if not token_info['eth_addr'] and not token_info['bsc_addr']:
            self.stat['article']['unknown_network_cnt'] += 1

        if self.initialized:
            # NEW LISTING FOUND!!
            # TODO: do something
            logging.info(f'new listing found:: {article_title} '
                         f'{article_release_date} vs {current_epoch_ms}, '
                         f'dt={current_epoch_ms - article_release_date:.2f} ms', extra={'TELEGRAM': 'INFO'})
            logging.info(article_url)
        else:
            # initial articles
            logging.info(f'initial article: {article_title}'
                         f'\n\t\t{article_url}'
                         f'\n\t\t{article_release_date}'
                         f'\n\t\t{token_info}')
            if self.data['config']['dump_old_listings']:
                with open('listing_list.txt', 'a') as f:
                    f.write(f"{article_release_date},{token_info['symbol']},{token_info['name']},{article_url}\n")

    def article_parser(self, article_title, article_url, force_scraping=False):
        # article page parser
        result = {
            'symbol': None,
            'name': None,
            'eth_addr': None,
            'bsc_addr': None
        }

        # get symbol from title
        try:
            result['symbol'] = re.findall(r'(?<=\().+?(?=\))', article_title)[0]
        except:
            force_scraping = True
            logging.error('article parser():: failed to get token symbol from title')
        # get name from title
        try:
            result['name'] = article_title.split('Binance Will List')[1].split('(')[0].strip()
        except:
            logging.error('article parser():: failed to get token name from title')

        # return if article page scraping not necessary
        if not force_scraping:
            return result

        try:
            webpage = self.scraper.get(article_url)
            wpage = BeautifulSoup(webpage.content, 'html5lib')

            for a in wpage.find_all('a', href=True):
                if 'etherscan' in  a['href']:
                    # ETH address
                    result['eth_addr'] = to_checksum_address(re.findall(r'(?:[0][x][a-fA-F0-9]{40})', a['href'])[0])
                if 'bscscan' in a['href']:
                    # BSC address
                    result['bsc_addr'] = to_checksum_address(re.findall(r'(?:[0][x][a-fA-F0-9]{40})', a['href'])[0])

            # try to get token symbol and name
            if result['eth_addr'] and self.dw3['eth']:
                result['symbol'] = self.dw3['eth'].symbol(result['eth_addr'])
                result['name'] = self.dw3['eth'].name(result['eth_addr'])
            elif result['bsc_addr'] and self.dw3['bsc']:
                result['symbol'] = self.dw3['bsc'].symbol(result['bsc_addr'])
                result['name'] = self.dw3['bsc'].name(result['bsc_addr'])
        except:
            e = sys.exc_info()[0]
            logging.error(f'article_parser({article_url}) exception::' + e.__name__ + ', ' + e.__doc__.replace('\n', ''))

        return result

    @staticmethod
    def get_proxies():
        # get proxy list to avoid hitting binance poll limit
        # TODO: pay for proxy
        response = requests.get('https://proxylist.geonode.com/api/proxy-list?limit=50&page=1&sort_by=speed&sort_type=asc')
        proxies = set()
        if response.ok:
            response = response.json()
            for proxy in response['data']:
                proxies.add(f'{proxy["ip"]}:{proxy["port"]}')
        else:
            logging.error('failed to get proxy list')
            assert False
        return proxies

def main():
    blb = BinanceListingBot()
    th = Thread(target=blb.poll_loop())
    th.start()
    th.join()


if __name__ == '__main__':
    main()
