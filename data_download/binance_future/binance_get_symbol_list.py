import json
import requests
import pandas as pd

# binance future symbol list
# https://binance-docs.github.io/apidocs/futures/en/#exchange-information
fsymbols = requests.get('https://www.binance.com/fapi/v1/exchangeInfo')
if fsymbols.status_code != 200:
    print('future exchanginfo request failed')
    exit(0)
fsymbols = fsymbols.text

# 24hr ticker list
# https://binance-docs.github.io/apidocs/spot/en/#24hr-ticker-price-change-statistics
ticker_24h = requests.get('https://www.binance.com/api/v3/ticker/24hr')
if ticker_24h.status_code != 200:
    print('24h ticker request failed')
    exit(0)
ticker_24h = ticker_24h.text

# extract PERPETUAL USDT pairs
df_symbol = pd.DataFrame()
data = json.loads(fsymbols)
for s in data['symbols']:
    if s['contractType'] == 'PERPETUAL':
        if 'USDT' in s['symbol']:
            df_symbol = df_symbol.append({'symbol'      : s['symbol'],
                                          'onboardDate' : s['onboardDate']}, ignore_index=True)

# get corresponding 24hr volume
df_out = pd.DataFrame()
data = json.loads(ticker_24h)
for d in data:
    ## list key - value pairs
    # for (k, v) in d.items():
    #     print(k,": ", str(v))
    if d['symbol'] in df_symbol['symbol'].to_numpy():
        df_out = df_out.append({ 'symbol'        : d['symbol'], 
                                 'quoteVolume'   : float(d['quoteVolume']),
                                 'lastPrice'     : float(d['lastPrice']),
                                 'onboardDate'   : df_symbol.loc[df_symbol['symbol'] == d['symbol'], 'onboardDate'].iloc[0]
                                }, ignore_index=True)

# sort with volume
df_out.sort_values('quoteVolume', ascending=False, inplace=True)
df_out.to_csv("symbol_list.csv", index=False)