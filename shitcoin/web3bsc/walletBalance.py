import time
import sys
import numpy as np
import pandas as pd
import datetime
import requests

from web3bsc import Web3BSC
from web3bsc import Network
from directWeb3 import DirectWeb3
import datetime
from forex_python.converter import CurrencyRates
from binance.client import Client
import ftx
from bokeh.plotting import figure, show
from bokeh.models import DatetimeTickFormatter, Range1d, LinearAxis

from walletFactory import WalletFactory

PRE_PATH = '../../investments/wallet_balances/'

class WalletBalance():
    def __init__(self):
        # main web3bsc class
        self.web3bsc = Web3BSC(barebone_init=True)
        # direct bsc calls for specific functions without web3 overhead
        self.dw3 = DirectWeb3(self.web3bsc.db_handler.get_network_info(Network.BSC))

        log_datetime = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.ofile_name = PRE_PATH + 'wallets_info_log_' + log_datetime + '.csv'
        sys.stdout=open(self.ofile_name, 'w')

    def get_ftx_etimated_balance(self):
        # gone
        return 0
        ftx_api_key = self.web3bsc.data_json['private_data']['ftx']['api_key']
        ftx_secret_key = self.web3bsc.data_json['private_data']['ftx']['secret_key']
        ftx_client = ftx.FtxClient(api_key=ftx_api_key, api_secret=ftx_secret_key)
        ftx_balances = ftx_client.get_balances()
        ftx_balance_usd = 0.0
        for b in ftx_balances:
            ftx_balance_usd += float(b['usdValue'])
        return ftx_balance_usd

    def get_binance_etimated_balance(self):
        binance_api_key = self.web3bsc.data_json['private_data']['binance']['api_key']
        binance_secret_key = self.web3bsc.data_json['private_data']['binance']['secret_key']
        binance_client = Client(binance_api_key, binance_secret_key)
        binance_snapshot = binance_client.get_account_snapshot(type='SPOT')
        binance_estimated_btc_balance = float(binance_snapshot['snapshotVos'][0]['data']['totalAssetOfBtc'])
        btc_price_usd = float(binance_client.get_symbol_ticker(symbol="BTCUSDT")['price'])
        return btc_price_usd*binance_estimated_btc_balance

    def update_wallet_csv(self, csv_file):
        # load csv
        df = pd.read_csv(csv_file)
        df_curr = pd.DataFrame(columns=['value', 'addr', 'name'])

        # add wbnb and sums if not there
        if df.loc[0].addr != '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c':
            bnb_row = pd.DataFrame({'addr': '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c',
                                    'addr_name': 'BNB'}, index=[0])
            sum_usd_row = pd.DataFrame({'addr': '### SUM ###',
                                        'addr_name': '### SUM_USD ###'}, index=[1])
            sum_bnb_row = pd.DataFrame({'addr': '### SUM ###',
                                        'addr_name': '### SUM_BNB ###'}, index=[2])

            df = pd.concat([bnb_row, sum_usd_row, sum_bnb_row, df]).reset_index(drop=True)
        # get date
        datestr = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        # add new column
        df[datestr] = np.NaN
        binance_index = ftx_index = sum_huf_index = -1
        skip_lines = 0
        # go through current df
        for index, row in df.iterrows():
            # skip BNB price
            if index < 3:
                continue
            if row.values[0][0] == '#':
                skip_lines = index
                # get binance, ftx balances
                if 'Binance' in row.values[0]:
                    binance_index = index
                    balance_usd = self.get_binance_etimated_balance()
                    df.at[binance_index, datestr] = float("{:.2f}".format(balance_usd))
                elif 'FTX' in row.values[0]:
                    ftx_index = index
                    balance_usd = self.get_ftx_etimated_balance()
                    df.at[ftx_index, datestr] = float("{:.2f}".format(balance_usd))
                elif 'HUF' in row.values[1]:
                    sum_huf_index = index
                # comment
                continue
            
            addr = self.web3bsc.w3.toChecksumAddress(row.addr)
            print('####', row.addr_name, '####', addr)
            for i in range(5):
                balance_dict = self.web3bsc.get_wallet_balance(addr, force_update=True)
                if not balance_dict['success']:
                    print(f'failed to get balance for {addr} round #{i}')
                else:
                    break
            wallet_balance_in_usd = balance_dict['wallet_balance_usd']
            
            df.at[index, datestr] = float("{:.2f}".format(wallet_balance_in_usd))
            for c in balance_dict['balances']:
                if (df_curr['addr'] == c['currency']['address']).any():
                    df_curr.loc[df_curr['addr'] == c['currency']['address'], 'value'] += c['value']
                else:
                    df_new_row = pd.DataFrame([[c['value'], c['currency']['address'], c['currency']['name']]], columns=df_curr.columns.values.tolist())
                    df_curr = pd.concat([df_curr, df_new_row])

                print('\t\t', c['currency']['address'], c['currency']['name'], c['value'])
            print('\t SUM =', wallet_balance_in_usd)
        
        # scan wallet factory addresses until nonce == 0
        for wf_idx in range(0):     #  skip
            wf = WalletFactory(wf_idx)
            add_idx = 0
            while 1:
                acc_dict = wf.get_address(add_idx)
                nonce = self.web3bsc.w3.eth.getTransactionCount(acc_dict['addr'])
                
                if not nonce:
                    # this address not used yet, stop
                    break

                add_idx += 1
                if not df.addr.str.contains(acc_dict['addr']).any():
                    # not processed
                    addr_name = f'#wf{wf_idx}_{add_idx:02}'
                    addr = acc_dict['addr']

                    print('####', addr_name, '####', addr)
                    balance_dict = self.web3bsc.get_wallet_balance(addr, force_update=True)
                    wallet_balance_in_usd = balance_dict['wallet_balance_usd']
                    wallet_balance_in_usd_str = float("{:.2f}".format(wallet_balance_in_usd))

                    df_ = pd.Series([addr, addr_name, wallet_balance_in_usd_str], index = ['addr', 'addr_name', datestr])     
                    df = df.append(df_, ignore_index=True)
                    for c in balance_dict['balances']:
                        if (df_curr['addr'] == c['currency']['address']).any():
                            df_curr.loc[df_curr['addr'] == c['currency']['address'], 'value'] += c['value']
                        else:
                            df_new_row = pd.DataFrame([[c['value'], c['currency']['address'], c['currency']['name']]], columns=df_curr.columns.values.tolist())
                            df_curr = pd.concat([df_curr, df_new_row])
                            
                        print('\t\t', c['currency']['address'], c['currency']['name'], c['value'])
                    print('\t SUM =', wallet_balance_in_usd)

        # calc sum usd
        sum_usd = np.sum(df.iloc[skip_lines+1:][datestr].dropna().to_numpy())
        # sum with exchanges
        sum_with_exchanged_usd = sum_usd + df.at[binance_index, datestr] + df.at[ftx_index, datestr]
        try:
            usd_huf_conv = CurrencyRates().get_rate('USD', 'HUF')
        except:
            resp = requests.get('https://open.er-api.com/v6/latest/USD')
            data = resp.json()
            usd_huf_conv = data['rates']['HUF']
        sum_with_exchanged_huf = sum_with_exchanged_usd * usd_huf_conv
        df.at[sum_huf_index, datestr] = float("{:.2f}".format(sum_with_exchanged_huf * 1e-6))

        # add bnb price
        bnb_price = self.web3bsc.get_bnb_price()

        df.at[0, datestr] = float("{:.2f}".format(bnb_price))
        df.at[1, datestr] = float("{:.2f}".format(sum_with_exchanged_usd))
        df.at[2, datestr] = float("{:.2f}".format(sum_with_exchanged_usd / bnb_price))

        # write result to file
        df.to_csv(PRE_PATH + 'wallets_info__.csv', index=False, na_rep='0.0')
        sys.stdout.close()

        # sort by address value
        with open(self.ofile_name, 'a') as f:
            f.write('\n\n\n\n')
            f.write('------------------------- sorted by address value --------------------------\n\n')
        df_sorted = df.iloc[skip_lines+1:]
        df_sorted = df_sorted[[datestr,'addr','addr_name']]
        df_sorted = df_sorted.sort_values(by=[datestr], ascending=False)
        df_sorted.to_csv(self.ofile_name, mode='a', header=False, index=False, sep='\t')

        # sort by currency holdings
        with open(self.ofile_name, 'a') as f:
            f.write('\n\n\n\n')
            f.write('------------------------- sorted by currency holdings --------------------------\n\n')
        df_sorted = df_curr.sort_values(by=['value'], ascending=False)
        df_sorted.to_csv(self.ofile_name, mode='a', header=False, index=False, sep='\t')

def main():
    wb = WalletBalance()
    wb.update_wallet_csv(PRE_PATH + 'wallets_info.csv')

def plot():
    df = pd.read_csv(PRE_PATH + 'wallets_info.csv')
    
    BNB_price_idx = df[df['addr_name'].str.contains('BNB') == True].index.tolist()[0]
    SUM_HUF_idx = df[df['addr_name'].str.contains('SUM HUF') == True].index.tolist()[0]
    
    df.drop(['addr', 'addr_name'], axis=1, inplace=True)
    
    dates = [datetime.datetime.strptime(date, '%Y%m%d_%H%M%S') for date in df.columns.tolist()]
    SUM_HUF = np.array(df.iloc[SUM_HUF_idx, :].tolist())
    BNB_USD = np.array(df.iloc[BNB_price_idx, :].tolist())

    
    p = figure(x_axis_type='datetime')
    p.xaxis.formatter=DatetimeTickFormatter(
        years=["%d %B %Y"],
        months=["%d %B %Y"],
        days=["%d %B %Y"],
        # hours=["%d %B %Y"]
    )
    p.xaxis.major_label_orientation = 3.1415/4
    p.line(dates, SUM_HUF, legend_label="MFt")
    p.circle(dates, SUM_HUF, legend_label="MFt")
    p.y_range = Range1d(SUM_HUF.min(), SUM_HUF.max())

    p.extra_y_ranges = {"bnb_y": Range1d(start=BNB_USD.min(), end=BNB_USD.max())}
    p.add_layout(LinearAxis(y_range_name="bnb_y"), 'right')
    p.line(dates, BNB_USD, color='black', legend_label="BNB", y_range_name="bnb_y")
    p.circle(dates, BNB_USD, color='black', legend_label="BNB", y_range_name="bnb_y")

    show(p)

if __name__ == '__main__':
    main()
    # plot()

