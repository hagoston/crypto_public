from binance.helpers import date_to_milliseconds, interval_to_milliseconds

def get_earliest_valid_timestamp(client, symbol, interval):
    kline = client.get_klines(
        symbol=symbol,
        interval=interval,
        limit=1,
        startTime=0,
        endTime=None
    )
    return kline[0][0]

def get_historical_klines(client, symbol, interval, start_str, end_str=None):
    """
    binance client mod
    """
    # init our list
    output_data = []

    # setup the max limit
    limit = 500

    # convert interval to useful value in seconds
    timeframe = interval_to_milliseconds(interval)

    # convert our date strings to milliseconds
    if type(start_str) == int:
        start_ts = start_str
    else:
        start_ts = date_to_milliseconds(start_str)

    # establish first available start timestamp
    first_valid_ts = get_earliest_valid_timestamp(client, symbol, interval)
    start_ts = max(start_ts, first_valid_ts)

    # if an end time was passed convert it
    end_ts = None
    if end_str:
        if type(end_str) == int:
            end_ts = end_str
        else:
            end_ts = client.date_to_milliseconds(end_str)
        end_ts = end_ts - timeframe

    idx = 0
    while True:
        # fetch the klines from start_ts up to max 500 entries or the end_ts if set
        temp_data = client.get_klines(
            symbol=symbol,
            interval=interval,
            limit=limit,
            startTime=start_ts,
            endTime=end_ts
        )

        # handle the case where exactly the limit amount of data was returned last loop
        if not len(temp_data):
            break

        # append this loops data to our output data
        output_data += temp_data

        # set our start timestamp using the last value in the array
        start_ts = temp_data[-1][0]

        # idx += 1
        # check if we received less than the required limit and exit the loop
        if len(temp_data) < limit:
            # exit the while loop
            break

        # increment next call by our timeframe
        start_ts += timeframe

        # # sleep after every 3rd call to be kind to the API
        # if idx % 3 == 0:
        #     time.sleep(1)

    return output_data