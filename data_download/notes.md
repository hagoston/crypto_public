
# data
## download binance future tick data
### create binance_keys.json
```
{
    "api_key": "your_binance_api_key",
    "secret_key": "your_binance_secret_key"
}
```
### downloading data
```
$ cd ./data_download/binance_future/
$ python3 binance_data_grabber.py \
    --symbol BTCUSDT            # e.g.: 'BTCUSDT', 'ADAUSDT', 'DOTUSDT', 'XRPUSDT'
    --start_date 2021-04-01     # inclusive (i.e. from 2021-04-01 00:00:00)
    --end_date 2021-04-05       # exclusive (i.e. until 2021-04-04 23:59:59)
    --interval 1_day            # e.g.: 1_day, 12_days, 1_month, 2_months
```
output folder ../../../data/binance_targz/

## compression
tar.gz files contain csv, should be compressed
### uncompress tar.gz files
```
$ cd ./scripts/binance_future/
$ python3 untar_data.py \
    --input_path ../../data/binance_targz
    --output_path ../../data/binance_uncompressed
    --filter BTCUSDT_T_DEPTH_20210401-20210402      # optional file name filter
```