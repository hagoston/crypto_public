import json
import os
from eth_account import Account
from eth_utils import remove_0x_prefix


def generate_account():
    acct, mnemonic = Account.create_with_mnemonic()
    return acct, mnemonic


class WalletFactory:
    def __init__(self, mnemonic_idx=0):
        Account.enable_unaudited_hdwallet_features()
        # load mnemonic
        self.curr_path = os.path.dirname(os.path.abspath(__file__))
        with open(self.curr_path + '/wallet_data.json') as json_file:
            self.data_json = json.load(json_file)
        self.mnemonic_idx = mnemonic_idx

    def get_address(self, address_index):
        # some check
        if address_index < 0:
            return None
        # generate account from mnemonic
        mnemonic = self.data_json['mnemonics'][self.mnemonic_idx]
        account_path = f"m/44'/60'/0'/0/{address_index}"
        acct = Account.from_mnemonic(mnemonic, account_path=account_path)
        address = acct.address
        private_key = remove_0x_prefix(acct.key.hex())
        return {
                "addr": address,
                "private_key": private_key,
                "name": f'#{address_index:02}'
        }


def main():
    for wf_idx in range(0, 3):
        wf = WalletFactory(wf_idx)
        print(f'WalletFactory({wf_idx})')
        if 0:
            for i in range(20):
                acct, mnemonic = generate_account()
                print(mnemonic)
            return

        else:
            for address_index in range(0, 10):
                acc_dict = wf.get_address(address_index)
                print(acc_dict['name'], acc_dict['addr'], acc_dict['private_key'])


if __name__ == '__main__':
    main()
