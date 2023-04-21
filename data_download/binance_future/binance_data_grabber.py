import pandas as pd
import time
import hashlib
import requests
import hmac
from urllib.parse import urlencode
import datetime
import os
import json
import threading
from icecream import ic
from dateutil.relativedelta import relativedelta
import random
import requests
import shutil

class BinanceDataGrabber:
    def __init__(self, symbol, data_types, start_date, end_date, download_interval = '1_month'):
        self.symbol = symbol
        self.data_types = data_types
        self.start_date = start_date
        self.end_date = end_date
        self.lock = threading.Lock()
        self.ofolder = '../../../data/binance_targz/'
        
        if (not 'month' in download_interval) and (not 'day' in download_interval):
            print('download_interval parameter overwrite to month')
            self.download_interval = 'month'
        else:
            self.download_interval = download_interval
        self.max_ongoing_downloads = 2  # TODO tune

        # log file
        self.log_file = 'bdg_' + self.symbol + '_log.txt'
        # file for request history
        self.progress_file = 'bdg_' + self.symbol + '_progress.csv'
        if os.path.isfile(self.progress_file) and not os.stat(self.progress_file).st_size == 0:
            self.df = pd.read_csv(self.progress_file)
            # clear ongoing column
            self.df = self.df.assign(ongoing=False)
        else:
            # create
            # log_time,symbol,startTime,endTime,dataType,id,downloaded
            self.df = pd.DataFrame(columns = [  'log_time',
                                                'start_time_str',
                                                'end_time_str',
                                                'symbol',
                                                'start_time',
                                                'end_time',
                                                'data_type',
                                                'id',
                                                'ongoing',
                                                'file_path',
                                                'file_size'])

        # binance sapi url
        self.S_URL_V1 = "https://api.binance.com/sapi/v1"
        # load binance api keay
        with open('binance_keys.json') as json_file:
            data = json.load(json_file)
            self.api_key = data['api_key']
            self.secret_key = data['secret_key']
    
    def _sign(self, params={}):
        data = params.copy()
        ts = str(int(1000 * time.time()))
        data.update({"timestamp": ts})     
        h = urlencode(data)
        # hh = h.replace("%40", "@")
        # print(hh)
        b = bytearray()
        b.extend(self.secret_key.encode())
        signature = hmac.new(b, msg=h.encode('utf-8'), digestmod=hashlib.sha256).hexdigest()
        sig = {"signature": signature}
        # print(signature)
        return data, sig

    def post(self, path, params={}):
        sign = self._sign(params)
        query = urlencode(sign[0]) + "&" + urlencode(sign[1])
        url = "%s?%s" % (path, query)
        # print(url)
        header = {"X-MBX-APIKEY": self.api_key}
        # print(header)
        p = requests.post(url, headers=header, \
            timeout=30, verify=True)
        return p

    def get(self, path, params):
        sign = self._sign(params)
        query = urlencode(sign[0]) + "&" + urlencode(sign[1])
        url = "%s?%s" % (path, query)
        # print(url)
        header = {"X-MBX-APIKEY": self.api_key}
        p = requests.get(url, headers=header, \
            timeout=30, verify=True)
        return p

    def get_ms_from_str(self, date_time, str_format='%Y-%m-%d %H:%M:%S'):
        # print(int(datetime.datetime.now().timestamp() * 1000))
        return int(datetime.datetime.strptime(date_time, str_format).timestamp() * 1000 + 2*3.6e6)
        
    def get_str_from_ms(self, date_time, str_format='%Y-%m-%d %H:%M:%S'):
        return datetime.datetime.fromtimestamp((date_time - 2*3.6e6)/1000).strftime(str_format)
    
    def get_datetime_from_ms(self, ms):
        return datetime.datetime.fromtimestamp(ms/1000)

    def get_str_from_datetime(self, dt):
        return self.get_str_from_ms(dt.timestamp() * 1000)
    
    def new_request(self):
        # request new link based on ongoing progresses

        for data_type in self.data_types:
            
            # count not downloaded e.g. active requests
            ongoing_downloads = len(self.df[(self.df.data_type == data_type) & (self.df.file_path == '-')])
            for _ in range(self.max_ongoing_downloads - ongoing_downloads):
                df_ = self.df[self.df.data_type==data_type]
                
                # new request
                # NOTE: df request expected to be in order and with the same download_interval

                # get start date from init config
                start_time = self.get_ms_from_str(self.start_date, '%Y-%m-%d')
                # if df contains prev lines get end_time of the last one
                if len(df_) > 0:
                    start_time = int(df_.iloc[-1]['end_time'])

                # add download interval
                start_time_datetime = self.get_datetime_from_ms(start_time)

                # find multiplier
                multiplier = 1
                if '_' in self.download_interval:
                    mpl = self.download_interval.split('_')[0]
                    if mpl.isnumeric():
                        multiplier = int(mpl)
                
                end_time_datetime = start_time_datetime + relativedelta(days=multiplier)
                if 'month' in self.download_interval:
                    end_time_datetime = start_time_datetime + relativedelta(months=multiplier)

                # check end date
                if end_time_datetime > self.get_datetime_from_ms(self.get_ms_from_str(self.end_date, '%Y-%m-%d')):
                    break

                # request new download link
                self.request_link(data_type, 
                                 self.get_str_from_datetime(start_time_datetime),
                                 self.get_str_from_datetime(end_time_datetime))
            
    def request_link(self, data_type, start_time_str, end_time_str):
        ## data_type:
        # T_TRADE  tick-by-tick trade
        # T_DEPTH  tick-by-tick order book (level 2); under development.
        # S_DEPTH  order book snapshot (level 2); temp data solution only for BTCUSDT at the moment.

        start_time = self.get_ms_from_str(start_time_str)
        end_time = self.get_ms_from_str(end_time_str)

        ic(data_type, start_time_str, end_time_str, start_time, end_time)

        path = "%s/futuresHistDataId" % self.S_URL_V1   
        params = {"symbol": self.symbol,
                "startTime": start_time,
                "endTime": end_time - 1,        # NOTE: -1ms to skip next day data
                "dataType": data_type,
                }

        result = self.post(path, params)

        id = -1
        file_path = '-'
        if 'id' not in result.json():
            print('request link failed with error: ' + result.text)
            result_text_json = json.loads(result.text)
            file_path = result_text_json['msg'].replace(',','_')
        else:
            id = result.json()['id']

        new_df_row = {
            'log_time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'start_time_str': start_time_str,
            'end_time_str': end_time_str,
            'symbol': self.symbol,
            'start_time': start_time,
            'end_time': end_time,
            'data_type': data_type,
            'id': id,
            'ongoing': False,
            'file_path': file_path,
            'file_size': '-'
        }
        #append row to the dataframe
        with self.lock:
            self.df = self.df.append(new_df_row, ignore_index=True)

    def write_to_csv(self):
        # write current dataframe state to file
        with self.lock:
            self.df.to_csv(self.progress_file, index=False)

    def download_th(self, id, df_index):
        # this function iterates until download link available with id argument
        ic(df_index, id)

        path = "%s/downloadLink" % self.S_URL_V1   
        params = {"downloadId": id}

        while 1:
            # request
            result = self.get(path, params)
            
            if 'link' in result.json():
                if 'Link is preparing' in result.json()['link']:
                    time.sleep(30)
                else:
                    # download link is ready
                    local_filename = str(self.symbol + "_" + self.df.loc[df_index, 'data_type']
                                    + '_' + self.df.loc[df_index, 'start_time_str'].split(' ')[0].replace("-", "")
                                    + '-' + self.df.loc[df_index, 'end_time_str'].split(' ')[0].replace("-", "")
                                    + '.tar.gz')
                    ofpath = self.ofolder + local_filename

                    print('download begins for ', id)
                    with requests.get(result.json()['link'], stream=True) as r:
                        with open(ofpath, 'wb') as f:
                            shutil.copyfileobj(r.raw, f) #, length=16*1024*1024)

                    with self.lock:
                        if self.df.loc[df_index, 'id'] != id:
                            # sanity check
                            ic('ERROR')
                        else:
                            # fill download info into dataframe
                            self.df.loc[df_index, 'file_path'] = local_filename
                            self.df.loc[df_index, 'file_size'] = format(os.path.getsize(ofpath) / (1024*1024), '.2f')
                            self.df.loc[df_index, 'ongoing'] = False
                    break
            else:
                # TODO
                ic('ERROR', result.text)
                break
        print('download ready for ', id)

    def run(self):
        # main loop
        # iterate dataframe for not downloaded ids, add new requests

        # add new thread for every download id 
        download_threads = []

        while 1:
            # start new requests if needed
            self.new_request()

            # check for ongoing downloads
            if not len(self.df[self.df.file_path=='-']):
                # all thread finised
                self.write_to_csv()
                break

            # call download thread for unfinised df lines
            for index, req in self.df[(self.df.file_path=='-') & (self.df.ongoing == False)].iterrows():
                time.sleep(random.randint(1, 10))
                # add new download thread is not ongoing and no file path set
                th = threading.Thread(target=self.download_th, args=(req.id, index))
                download_threads.append(th)
                # set ongoing flag
                with self.lock:
                    self.df.loc[index, 'ongoing'] = True
                th.start()

            threads_alive = []
            for t in download_threads:
                if t.is_alive() == False:
                    t.join()
                else:
                    threads_alive.append(t)
            download_threads = threads_alive

            # main loop sleep
            ic()
            self.write_to_csv()
            time.sleep(30)

if __name__=='__main__':
    # config logger
    ic.configureOutput(includeContext=True)

    bdg = BinanceDataGrabber('BTCUSDT', ['T_TRADE', 'T_DEPTH'], '2020-01-01', '2020-07-01', '1_month')
    bdg.run()
    exit(0)

    import argparse

    parser = argparse.ArgumentParser(description='binance downloader')
    parser.add_argument('--symbol', required=True, help='symbol to download')
    parser.add_argument('--interval', required=False, default='2_months', help='download chunk interval')
    parser.add_argument('--start_date', required=False, default='2020-07-01', help='request data from this date')
    parser.add_argument('--end_date', required=False, default='2021-03-01', help='request data till this date')
    args = parser.parse_args()
    ic(args)

    # ['BTCUSDT', 'ADAUSDT', 'DOTUSDT', 'XRPUSDT']
    # python3 binance_data_grabber.py --symbol BTCUSDT --start_date 2021-04-01 --end_date 2021-04-05 --interval 1_day
    # python3 binance_data_grabber.py --symbol BTCUSDT --start_date 2021-03-01 --end_date 2021-05-01 --interval 1_month &
    
    bdg = BinanceDataGrabber(args.symbol, ['T_TRADE', 'T_DEPTH'], args.start_date, args.end_date, args.interval)
    bdg.run()
