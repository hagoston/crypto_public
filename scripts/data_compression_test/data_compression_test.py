from dask import dataframe as dd
import pandas as pd
import numpy as np
import time
import os

import pyarrow.parquet as pq
import pyarrow.csv as csv
import pyarrow as pa

def get_size(path):
    if os.path.isfile(path):
        return os.path.getsize(path)
    total_size = 0
    for path, dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(path, f)
            total_size += os.path.getsize(fp)
    return total_size

def write_result(logfile, dt, ofile):
    size = get_size(ofile)
    fname = ofile.split('/')[-1]
    with open(logfile, 'a') as f:
        f.write(fname + ',' + str(dt) + ',' + str(size) + '\n')



symbol = 'BTC'
basepath = '~/temp'
fpath = basepath+'/crypto/data/binance_uncompressed/'+symbol+'USDT/T_DEPTH/'
filebase = symbol+'USDT_T_DEPTH_2021-04-01_depth_update.csv'
update_file = fpath + filebase

outpath = '~/temp/crypto/data/binance_uncompressed/BTCUSDT/T_DEPTH/'
logfile = outpath + filebase.split('.')[0] + '_comparison_result.txt'
with open(logfile, 'w') as f:
    f.write('file,dt,size\n')
    f.write('original_'+filebase + ',0,' + str(get_size(update_file)) + '\n')


# dask, gzip
ofile = outpath+filebase+'.parquet'
start_time = time.time()
df = dd.read_csv(update_file)

df['timestamp'] = dd.to_datetime(df['timestamp'], unit='ms')
df = df.set_index('timestamp', sorted=True)

df.to_parquet(ofile, engine='pyarrow', compression='gzip', write_index=True)
dt = time.time() - start_time
write_result(logfile, dt, ofile)

exit(0)

# pandas
ofile = outpath+'df.parquet.gzip'
start_time = time.time()
df = pd.read_csv(update_file)
df.to_parquet(ofile, compression='gzip', index=False)
dt = time.time() - start_time
write_result(logfile, dt, ofile)

# dask, brotli
ofile = outpath+'dd_brotli.parquet'
start_time = time.time()
df = dd.read_csv(update_file)
df.to_parquet(ofile, engine='pyarrow', compression='brotli', write_index=False)
dt = time.time() - start_time
write_result(logfile, dt, ofile)

# dask, gzip
ofile = outpath+'dd_gzip.parquet'
start_time = time.time()
df = dd.read_csv(update_file)
df.to_parquet(ofile, engine='pyarrow', compression='gzip', write_index=True)
dt = time.time() - start_time
write_result(logfile, dt, ofile)

# dask, snappy
ofile = outpath+'dd_snappy.parquet'
start_time = time.time()
df = dd.read_csv(update_file)
df.to_parquet(ofile, engine='pyarrow', compression='snappy', write_index=False)
dt = time.time() - start_time
write_result(logfile, dt, ofile)

# pyarrow, gzip
ofile = outpath+'pyarrow.v1.0.parquet.gzip'
start_time = time.time()
df = pd.read_csv(update_file)
table = pa.Table.from_pandas(df)
pq.write_table(table, ofile, compression='gzip')
dt = time.time() - start_time
write_result(logfile, dt, ofile)

# pyarrow, snappy
ofile = outpath+'pyarrow.v1.0.parquet.snappy'
start_time = time.time()
df = pd.read_csv(update_file)
table = pa.Table.from_pandas(df)
pq.write_table(table, ofile, compression='snappy')
dt = time.time() - start_time
write_result(logfile, dt, ofile)

# pyarrow v1.0, brotli
ofile = outpath+'pyarrow.v1.0.parquet.brotli'
start_time = time.time()
df = pd.read_csv(update_file)
table = pa.Table.from_pandas(df)
pq.write_table(table, ofile, version='1.0', compression='brotli')
dt = time.time() - start_time
write_result(logfile, dt, ofile)

# pyarrow v1.0, none
ofile = outpath+'pyarrow.v1.0.parquet.none'
start_time = time.time()
df = pd.read_csv(update_file)
table = pa.Table.from_pandas(df)
pq.write_table(table, ofile, version='1.0', compression='none')
dt = time.time() - start_time
write_result(logfile, dt, ofile)

# pyarrow v1.0, lz4
ofile = outpath+'pyarrow.v1.0.parquet.lz4'
start_time = time.time()
df = pd.read_csv(update_file)
table = pa.Table.from_pandas(df)
pq.write_table(table, ofile, version='1.0', compression='lz4')
dt = time.time() - start_time
write_result(logfile, dt, ofile)

# pyarrow v1.0, zstd
ofile = outpath+'pyarrow.v1.0.parquet.zstd'
start_time = time.time()
df = pd.read_csv(update_file)
table = pa.Table.from_pandas(df)
pq.write_table(table, ofile, version='1.0', compression='zstd')
dt = time.time() - start_time
write_result(logfile, dt, ofile)

# pyarrow v2.0, gzip
ofile = outpath+'pyarrow.v2.0.parquet.gzip'
start_time = time.time()
df = pd.read_csv(update_file)
table = pa.Table.from_pandas(df)
pq.write_table(table, ofile, version='2.0', compression='gzip')
dt = time.time() - start_time
write_result(logfile, dt, ofile)

# pyarrow v2.0, snappy
ofile = outpath+'pyarrow.v2.0.parquet.snappy'
start_time = time.time()
df = pd.read_csv(update_file)
table = pa.Table.from_pandas(df)
pq.write_table(table, ofile, version='2.0', compression='snappy')
dt = time.time() - start_time
write_result(logfile, dt, ofile)

# pyarrow v2.0, brotli
ofile = outpath+'pyarrow.v2.0.parquet.brotli'
start_time = time.time()
df = pd.read_csv(update_file)
table = pa.Table.from_pandas(df)
pq.write_table(table, ofile, version='2.0', compression='brotli')
dt = time.time() - start_time
write_result(logfile, dt, ofile)

# pyarrow v2.0, none
ofile = outpath+'pyarrow.v2.0.parquet.none'
start_time = time.time()
df = pd.read_csv(update_file)
table = pa.Table.from_pandas(df)
pq.write_table(table, ofile, version='2.0', compression='none')
dt = time.time() - start_time
write_result(logfile, dt, ofile)

# pyarrow v2.0, lz4
ofile = outpath+'pyarrow.v2.0.parquet.lz4'
start_time = time.time()
df = pd.read_csv(update_file)
table = pa.Table.from_pandas(df)
pq.write_table(table, ofile, version='2.0', compression='lz4')
dt = time.time() - start_time
write_result(logfile, dt, ofile)

# pyarrow v2.0, zstd
ofile = outpath+'pyarrow.v2.0.parquet.zstd'
start_time = time.time()
df = pd.read_csv(update_file)
table = pa.Table.from_pandas(df)
pq.write_table(table, ofile, version='2.0', compression='zstd')
dt = time.time() - start_time
write_result(logfile, dt, ofile)