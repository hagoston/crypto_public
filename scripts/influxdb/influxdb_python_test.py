from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import arctic

def adb():
    a = arctic.Arctic('127.0.0.1')

    # list arctic db container
    for lib in a.list_libraries():
        print(lib)
        for sym in a[lib].list_symbols():
            dat = a[lib].read(sym)
            print(f'\t{sym} size={dat.shape}')
            print(f'\t\t{list(dat)}')

    # lib = a['BINANCE_FUTURES']
    # print(lib.list_symbols())
    # it = lib.iterator('trades-BTC-USDT')

    exit(0)

    for chunk in it:
        # chunk :: dataframe
        print(list(chunk))
        # print(chunk.iloc[-1].side)
        for row in chunk.iterrows():
            timestamp = row[0]
            print(row[1].values)
            ts, side, price, id, size = row[1].values
            print(f'{timestamp} {side} {price} {id} {size}')
            # if size == 0:
            #     del book[side][price]
            # else:
            #     book[side][price] = size
            # if delta:
            #     print(f"Time: {timestamp} L2 Book: {book}")

def main():
    bucket = "crypto"

    client = InfluxDBClient.from_config_file("influx_config.ini")

    write_api = client.write_api(write_options=SYNCHRONOUS)
    query_api = client.query_api()


    # write_api.write(bucket=bucket, record=p)
    # query_txt = 'from(bucket:"'+bucket+'") |> range(start: -10h)'

    query_txt = 'from(bucket: "crypto") \
      |> range(start: 2021-03-14T00:00:00Z, stop: 2021-03-14T01:00:00Z) \
      |> filter(fn: (r) => r["_measurement"] == "ticker-BINANCE_FUTURES")'

    # ## using Table structure
    # tables = query_api.query(query_txt)
    # print(type(tables))
    # for table in tables:
    #     print(table)
    #     for row in table.records:
    #         print (row.values)


    # ## using csv library
    # csv_result = query_api.query_csv(query_txt)
    # val_count = 0
    # for row in csv_result:
    #     for cell in row:
    #         val_count += 1

    pd_result = query_api.query_data_frame(query_txt)
    print(pd_result.head())


if __name__ == '__main__':
    adb()