
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_utils import remove_0x_prefix
import os
import json
from eth_abi import abi


class MagicNumber():
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
        
        # read contract output
        with open('magicNumber_opcode.run', 'r') as f:
            output = f.read()
        # print(f'output={output}')    
        output_bytes = bytes.fromhex(remove_0x_prefix(output))
        # print(f'output_bytes={output_bytes}')
        output_decoded = abi.decode(['uint256'], output_bytes)
        print(f'output_decoded={output_decoded}')

        # deploy smart contract
        with open('magicNumber_opcode_creation.compiled', 'r') as f:
            deploy_code = f.read()
        print(deploy_code)

        # create transaction to transfer allowed tokens
        _txn = {
            'from': self.secret_json['naught_coin_allowed_addr'],
            'nonce': self.w3.eth.get_transaction_count(self.secret_json['naught_coin_allowed_addr']),
            'data': bytes.fromhex(deploy_code),
            'gas': 3000000,
            'gasPrice': self.w3.to_wei('50', 'gwei'),
            'chainId': 80001 #  mumbai-polygon
        }
        #sign the transaction
        signed_tx = self.w3.eth.account.sign_transaction(_txn, self.secret_json['naught_coin_allowed_addr_private_key'])
        #send transaction
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)

        #get transaction hash
        print(f'tx_hash = {self.w3.to_hex(tx_hash)}')


if __name__ == '__main__':
    va = MagicNumber()
