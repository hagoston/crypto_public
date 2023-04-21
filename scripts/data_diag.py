from dask import dataframe as dd
# import visdom
import numpy as np
import time

symbol = 'BTC'
basepath = '~/temp'
fpath = basepath+'/crypto/data/binance_uncompressed/'+symbol+'USDT/T_DEPTH/'
filebase = symbol+'USDT_T_DEPTH_2021-01-15_depth_'
snap_file = filebase+'snap.csv'
update_file = filebase+'update.csv'

# viz = visdom.Visdom()

start_time = time.time()

snap_df = dd.read_csv(fpath + snap_file)
update_df = dd.read_csv(fpath + update_file)

if 1:
    # snap_interval = np.diff(snap_df.timestamp.unique().compute())

    # viz.bar(
    #     X=snap_interval * 1e-3 / 60,
    #     win='snap_dt'
    # )

    # exit()

    # get unique pu-s
    discont_df_ = update_df.drop_duplicates('pu')
    # insert prev ts
    discont_df_['prev_ts'] = discont_df_.timestamp.shift()
    # pu =? last_update_id_prev
    discont_df_ = discont_df_[discont_df_.pu.ne(discont_df_.last_update_id.shift())]
    # rm nan (first row)
    discont_df_ = discont_df_.dropna()
    discont_df_ = discont_df_.astype({'prev_ts': np.int64})
    discont_df_['dts_min'] = (discont_df_.timestamp - discont_df_.prev_ts) * 1e-3 / 60


# update_df.to_parquet(update_file+'.parquet', compression='BROTLI')

print(discont_df_.compute())
print("--- %s seconds ---" % (time.time() - start_time))
