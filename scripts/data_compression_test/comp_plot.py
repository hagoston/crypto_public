import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

ipath = '~/temp/crypto/crypto_github/scripts/data_compression/'
flist = ['BTCUSDT_T_DEPTH_2021-01-15_depth_update_comparison_result.txt',
         'BTCUSDT_T_DEPTH_2021-01-15_depth_update_5M_comparison_result.txt',
         'BTCUSDT_T_DEPTH_2021-01-15_depth_update_2M_comparison_result.txt'  ]
flist = [ipath + s for s in flist]


df_merge = pd.DataFrame()

for i, ifile in enumerate(flist):
    df = pd.read_csv(ifile)
    uncompressed_size = df.iloc[0]['size']
    df['comp_ratio'] = uncompressed_size / df['size']

    df_merge['file'] = df.iloc[1:]['file']
    df_merge["%.0f MB input file comp_ratio" % (uncompressed_size/(2**20))] = df.iloc[1:]['comp_ratio']
    df_merge["%.0f MB input file dt" % (uncompressed_size/(2**20))] = df.iloc[1:]['dt']

df_merge.sort_values(df_merge.columns[1], inplace = True)

comp_ratio_list = list(filter(lambda k: 'comp_ratio' in k, df_merge.columns))
comp_ratio_list.append('file')

dt_list = list(filter(lambda k: 'dt' in k, df_merge.columns))
dt_list.append('file')

fig, axes = plt.subplots(nrows=2, ncols=1)

df_merge[comp_ratio_list].plot(ax=axes[0], kind='bar', stacked=False, x='file')
df_merge[dt_list].plot(ax=axes[1], kind='bar', stacked=False, x='file')

fig.axes[0].xaxis.set_visible(False)
axes[0].set_ylabel('compression ratio')
axes[1].set_ylabel('compression exec time [s]')

plt.xticks(rotation=90)
plt.tight_layout()
plt.show()
    
# show(p)