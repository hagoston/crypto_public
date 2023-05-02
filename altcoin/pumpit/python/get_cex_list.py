import requests
import json
from enum import Enum
 
def create_get_url(base_url: str, params: dict) -> str:
    """
    Create a GET URL with query parameters

    :param base_url: Base URL
    :param params: Dictionary of query parameters
    :return: GET URL with query parameters
    """

    # Encode the query parameters as a string
    query_string = '&'.join([f'{key}={value}' for key, value in params.items()])

    # Append the query string to the base URL
    get_url = f'{base_url}?{query_string}'

    return get_url

class CENTERTYPE(Enum):
    ALL = "all"
    CEX = "cex"
    DEX = "dex"

class CATEGORY(Enum):
    ALL = "all"
    SPOT = "spot"
    PERPETUAL = "perpetual"
    FUTURES = "futures"

class QUOTECURRENCYID(Enum):
    ALL = -1
    USDT = 825
    BTC = 1

def get_markets_with_coin(coin_symbol: str, 
                          center_type : CENTERTYPE = CENTERTYPE.ALL,
                          category: CATEGORY = CATEGORY.SPOT,
                          quote_currency: QUOTECURRENCYID = QUOTECURRENCYID.ALL):
    # "https://api.coinmarketcap.com/data-api/v3/cryptocurrency/market-pairs/latest?slug=arker&
    # start=1&
    # limit=100&
    # category=spot&
    # centerType=cex&
    # sort=cmc_rank_advanced"


    base_url = 'https://api.coinmarketcap.com/data-api/v3/cryptocurrency/market-pairs/latest'

    params = {
        'slug': coin_symbol, 
        'category': category.value,
        "centerType": center_type.value,
        'start': '1',
        'limit': '100'
    }
    if quote_currency != QUOTECURRENCYID.ALL:
        params['quoteCurrencyId'] = quote_currency.value

    get_url = create_get_url(base_url, params)

    response = requests.get(get_url)

    # Check the status code of the response
    if response.status_code != 200:
        print(f'Error: {response.status_code}')
    else:
        # Parse the response as JSON
        json_data = json.loads(response.text)

        if 'data' not in  json_data:
            return None
        # Access the data in the JSON response
        """
        {
        "data":{
            "id":14734,
            "name":"Arker",
            "symbol":"ARKER",
            "numMarketPairs":1,
            "marketPairs":[
                {
                    "exchangeId":311,
                    "exchangeName":"KuCoin",
                    "exchangeSlug":"kucoin",
                    "exchangeNotice":"",
                    "outlierDetected":0,
                    "priceExcluded":0,
                    "volumeExcluded":0,
                    "marketId":529362,
                    "marketPair":"ARKER/USDT",
                    "category":"spot",
                    "marketUrl":"https://www.kucoin.com/trade/ARKER-USDT",
                    "marketScore":"-1.0000",
                    "marketReputation":0.884,
                    "baseSymbol":"ARKER",
                    "baseCurrencyId":14734,
                    "quoteSymbol":"USDT",
                    "quoteCurrencyId":825,
                    "price":0.00123131,
                    "volumeUsd":170266.04674008,
                    "effectiveLiquidity":229.0,
                    "liquidity":0,
                    "lastUpdated":"2023-01-28T15:11:51.000Z",
                    "quote":0.001231,
                    "volumeBase":138280181.1171,
                    "volumeQuote":170222.90295515,
                    "feeType":"percentage",
                    "depthUsdNegativeTwo":700.55936404,
                    "depthUsdPositiveTwo":976.22031593,
                    "reservesAvailable":1
                }
            ]
        },
        "status":{
            "timestamp":"2023-01-28T15:12:39.774Z",
            "error_code":"0",
            "error_message":"SUCCESS",
            "elapsed":"11",
            "credit_count":0
        }
        }
        """
        return json_data["data"]


coin_symbol = "flame"
center_type = CENTERTYPE.CEX
category = CATEGORY.ALL
quote_currency = QUOTECURRENCYID.USDT

result = get_markets_with_coin(coin_symbol, center_type, category, quote_currency)
print(json.dumps(result, indent=1))