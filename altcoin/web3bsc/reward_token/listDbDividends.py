import time
import datetime
import sys

import numpy as np
import pandas as pd

sys.path.append('../')
from db_handler import DBHandler

class ListDBDiv():
    def __init__(self, dbfile):
        # direct bsc calls for specific functions without web3 overhead
        self.db_handler = DBHandler(dbfile, 1)  # 1 - BSC network

    def get_filtered_dividend_token_ids(self, risk_ids=None, invert=False):
        # get list of failure risk ids
        if risk_ids is None:
            risk_ids = self.db_handler.get_showstopper_ids()
            invert = True
        # get list of dividend token ids and the belonging risk ids
        div_tokens = self.db_handler.get_dividend_token_ids_with_risk_status_ids()
        # make list of usable tokens
        filtered_token_ids = []
        for div_token in div_tokens:
            dividend_token_id = int(div_token[0])
            risk_status_ids = [int(vid) for vid in div_token[1].split(',')]
            # filter out any failure ones
            if invert:
                if not any(ss_id in risk_status_ids for ss_id in risk_ids):
                    # these could be used in theory
                    filtered_token_ids.append(dividend_token_id)
            else:
                if any(ss_id in risk_status_ids for ss_id in risk_ids):
                    # these could be used in theory
                    filtered_token_ids.append(dividend_token_id)
        return filtered_token_ids

    def print_dividend_tokens_from_db(self):
        df = pd.DataFrame(columns=['dividend_token_addr', 'balance', 'reward_token_address', 'distribute_function'])
        filtered_token_ids = self.get_filtered_dividend_token_ids()
        for div_token_id in filtered_token_ids:
            # update
            div_token = self.db_handler.get_dividend_token(div_token_id)
            if not div_token:
                # ?!
                continue
            dividend_token_address = div_token[1]
            reward_token_id = div_token[2]
            distribute_function = div_token[3]
            price_usd = div_token[4]
            currency_id = div_token[5]

            reward_token = self.db_handler.get_reward_token(reward_token_id)
            reward_token_address = reward_token[1]

            if price_usd is not None:
                df = df.append({'dividend_token_addr': 'https://bscscan.com/address/'+dividend_token_address,
                                'balance': price_usd,
                                'reward_token_address': reward_token_address,
                                'distribute_function': distribute_function}, 
                                ignore_index=True)
        df.sort_values(by='balance', ascending=False, inplace=True)
        df.to_csv('./reward_token_from_db.csv', index=False, sep ='\t')

    def move_risk_status(self, risk_ids, db_to_be_updated):
        db_to_be_updated_handler = DBHandler(db_to_be_updated)
        dividend_token_ids = self.get_filtered_dividend_token_ids(risk_ids)
        print(len(dividend_token_ids))

def main():
    dbpath = './BSC.db'
    listDbDiv = ListDBDiv(dbpath)
    listDbDiv.print_dividend_tokens_from_db()

if __name__ == '__main__':
    main()

