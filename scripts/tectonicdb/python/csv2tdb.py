from tdb.tectonic import TectonicDB
from asyncio import get_event_loop

import time
import pandas as pd

class csv2tdb:
    def __init__(self, csv_file):
        self.csv_file = csv_file    # csv file path
        self.tdb = TectonicDB()     # tectonic db client
        self.dbname = 'test1'
        self.tmp = 0

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.tdb.destroy()

    async def insert_from_csv(self):

        # create db
        ret = await self.tdb.create(self.dbname)
        print(self.dbname, 'db creation ret=', ret)

        chunksize = 10 ** 7

        with pd.read_csv(self.csv_file, chunksize=chunksize) as reader:
            for chunk in reader:
                await self.insert_2_db(chunk)
                # return

    async def insert_2_db(self, chunk):
        # ts, seq, is_trade, is_bid, price, size, dbname
        # print(chunk)

        if 1:
            self.tmp += len(chunk.index)
            curr_cnt = self.tmp
        else:
            for index, row in chunk.iterrows():
                # ts, seq, is_trade, is_bid, price, size, dbname
                ret = await self.tdb.insert(row.timestamp,
                                            row.last_update_id,
                                            False,
                                            row.side == 'b',
                                            row.price,
                                            row.qty,
                                            self.dbname)
            curr_cnt = (await self.tdb.countall())[1]

        print('curr cnt:', curr_cnt, ' / ', 132707679, '=', curr_cnt/132707679*100)

    async def read_all(self):
        ret = await self.tdb.use(self.dbname)
        print(await self.tdb.getall())

# async def measure_latency():
#     dts = []
#
#     db = TectonicDB()
#
#     t = time.time()
#     for i in range(100):
#         # print(i)
#         ret = await db.insert(0,0,True, True, 0., 0., 'default')
#         # print(ret)
#         t_ = time.time()
#         dt = t_ - t
#         t = t_
#         dts.append(dt)
#     print("AVG:", sum(dts) / len(dts))
#     print(await db.countall())
#     db.destroy()


if __name__ == "__main__":
    symbol = 'BTC'
    fpath = '~/crypto/data/binance_uncompressed/' + symbol + 'USDT/T_DEPTH/'
    filebase = symbol + 'USDT_T_DEPTH_2021-01-15_depth_'
    snap_file = filebase + 'snap.csv'
    update_file = filebase + 'update.csv'

    csv2tdb_ = csv2tdb(fpath + update_file)
    loop = get_event_loop()
    func = csv2tdb_.insert_from_csv()
    # func = csv2tdb_.read_all()
    loop.run_until_complete(func)

    # loop = get_event_loop()
    # measure = measure_latency()
    # loop.run_until_complete(measure)
