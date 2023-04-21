
from web3 import Web3
import os
import json

class PrivacyAttack():
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
        
        # https://medium.com/aigang-network/how-to-read-ethereum-contract-storage-44252c8af925
        privacy_contract = self.secret_json['privacy_contract_addr']
        
        for index in range(10):
            contract_storage_data = self.w3.eth.getStorageAt(privacy_contract, index)

            #print(contract_storage_data)
            print(f'#{index}', self.w3.toHex(contract_storage_data))
        
        '''
        bool public locked = true;
        uint256 public ID = block.timestamp;
        uint8 private flattening = 10; 
        uint8 private denomination = 255; 
        uint16 private awkwardness = uint16(block.timestamp);
        bytes32[3] private data;
            #0 0x0000000000000000000000000000000000000000000000000000000000000001   bool public locked = true;
            #1 0x0000000000000000000000000000000000000000000000000000000064306959   uint256 public ID = block.timestamp;
            #2 0x000000000000000000000000000000000000000000000000000000006959ff0a   uint8 private flattening = 10; uint8 private denomination = 255; uint16 private awkwardness = uint16(block.timestamp);
            #3 0xfc0a78a1f04567f7c8fcd3af5a5802866d39ec094575e40ec074721a936abd36
            #4 0x365a916f6fadaa8f2e1dbd25742fd7be87bd1be254d0acdda3331a3da61419d1
            #5 0x1d6f7e00eab14b879ddea34320b70f32 0x2f8a9797435321184abf1366fb9fb786
            #6 0x0000000000000000000000000000000000000000000000000000000000000000
            #7 0x0000000000000000000000000000000000000000000000000000000000000000
            #8 0x0000000000000000000000000000000000000000000000000000000000000000
            #9 0x0000000000000000000000000000000000000000000000000000000000000000
        '''
        
        '''
        Note:
        Nothing in the ethereum blockchain is private. The keyword private is merely an artificial construct of the Solidity language. Web3's getStorageAt(...) can be used to read anything from storage. It can be tricky to read what you want though, since several optimization rules and techniques are used to compact the storage as much as possible.

        It can't get much more complicated than what was exposed in this level. For more, check out this excellent article by "Darius": How to read Ethereum contract storage
        '''

if __name__ == '__main__':
    va = PrivacyAttack()