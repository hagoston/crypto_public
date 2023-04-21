import pandas as pd


df = pd.read_csv('lppair_list_proc.txt', delimiter=';', skipinitialspace=True)

for exp in range(0,3):
   min_bnb = 1 / 10**exp
   df_filtered = df.loc[df.swap_profit_bnb > min_bnb]

   print('swaps with >{0:.2}BNB profit:'.format(min_bnb))
   print(df_filtered[['swap_profit_bnb','initial_investment_bnb','swap_chain']].to_string(index=False))
   
   sum_filtered = df_filtered.swap_profit_bnb.sum()
   print('\t ######### sum = {0:.2}'.format(sum_filtered))
   
   df.drop(df.loc[df.swap_profit_bnb > min_bnb].index, inplace=True)
   
sum = df.swap_profit_bnb.sum()
print('all other = ', sum)
