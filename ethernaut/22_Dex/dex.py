
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_utils import remove_0x_prefix, to_hex, to_checksum_address
import os
import json
from eth_abi import abi
import numpy as np


class Dex():
    def __init__(self):
        # initial token distribution
        self.sum_tokens = np.array([110, 110], dtype=np.float)
        self.dex_tokens = np.array([100, 100], dtype=np.float)
        self.self_tokens = self.sum_tokens - self.dex_tokens

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

        # approve dex to swap tokens
        self.approve(1000)

        # swap swap back and forth until dex contract fails
        # NOTE: could be done in one transaction from a contract
        while True:
            # get balances
            token_holdings = self.getTokenHoldings(True)

            # end loop if one of dex's tokens has zero balance
            dex_token_balances = list(token_holdings[self.secret_json['20_dex_contract_addr']].values())
            if any(v <= 0 for v in dex_token_balances):
                print('done.. exit')
                break

            # create transaction for swap
            ## swap(address from, address to, uint amount) public
            my_addr = self.secret_json['my_addr']
            encoded_function_signature = self.w3.keccak(text=f'swap(address,address,uint256)').hex()[:10]
            # find token with positive balance
            _from_idx = 0
            if list(token_holdings[my_addr].values())[_from_idx] <= 0:
                _from_idx = 1
            _to_idx = 0 if _from_idx else 1
            encoded_addr_from = remove_0x_prefix(list(token_holdings[my_addr])[_from_idx]).lower().zfill(64)
            encoded_addr_to = remove_0x_prefix(list(token_holdings[my_addr])[_to_idx]).lower().zfill(64)
            _amount = list(token_holdings[my_addr].values())[_from_idx]

            # check swap validity with local swap proce calculation
            _swap_amount = self.getSwapPrice(_from_idx, _amount)
            _dex_swap_to_token_balance = list(token_holdings[self.secret_json['20_dex_contract_addr']].values())[_to_idx]
            if _swap_amount > _dex_swap_to_token_balance:
                print(f'warning:: contract would fail _swap_amount ({_swap_amount:.2f}) > _dex_swap_to_token_balance ({_dex_swap_to_token_balance:.2f})')
                # calc new amount to swap
                _new_swap_amount = self.getSwapPrice(_to_idx, int(_dex_swap_to_token_balance))
                _amount = int(_new_swap_amount)
                print(f'could not swap all the tokens, reduced amount = {_amount:.2f}')
            # encode swap amount
            encoded_amount = str(remove_0x_prefix(hex(_amount))).lower().zfill(64)
            
            data = encoded_function_signature + encoded_addr_from + encoded_addr_to + encoded_amount
            _txn = self.getMumbaiPolygonEmptyTx()
            _txn.update({
                'to': self.secret_json['20_dex_contract_addr'],
                'from': self.secret_json['my_addr'],
                'data': data
            })
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
            else:
                print('tx failed')
                break
    
    def approve(self, _amount):
        # function approve(address spender, uint amount) public {
        encoded_function_signature = self.w3.keccak(text=f'approve(address,uint256)').hex()[:10]
        encoded_addr_from = remove_0x_prefix(self.secret_json['20_dex_contract_addr']).lower().zfill(64)
        encoded_amount = str(remove_0x_prefix(hex(_amount))).lower().zfill(64)

        data = encoded_function_signature + encoded_addr_from + encoded_amount
        _txn = self.getMumbaiPolygonEmptyTx()
        _txn.update({
            'to': self.secret_json['20_dex_contract_addr'],
            'from': self.secret_json['my_addr'],
            'data': data
        })
        # sign the transaction
        signed_tx = self.w3.eth.account.sign_transaction(_txn, self.secret_json['my_addr_private_key'])
        # send transaction
        tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        # get transaction hash
        print(f'tx_hash = {self.w3.to_hex(tx_hash)}')
        # wait for the transaction to be mined and get the transaction receipt
        tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if tx_receipt['status']:
            print('approve succeeded')
        else:
            print('approve failed')

    def getMumbaiPolygonEmptyTx(self):
        _txn = {
            'nonce': self.w3.eth.get_transaction_count(self.secret_json['my_addr']),
            'gas': 3000000,
            'gasPrice': self.w3.to_wei('50', 'gwei'),
            'chainId': 80001    #  mumbai-polygon
        }
        return _txn
    
    def localTest(self):
        # local python test
        self.printTokenHoldingsLocal()
        # swap back and forth
        for _ in range(100):
            from_idx = 0
            if self.self_tokens[from_idx] <= 0:
                from_idx = 1
            self.swap(from_idx, self.self_tokens[from_idx])
            self.printTokenHoldingsLocal()
            if (self.self_tokens < 0).any():
                break

    def getTokenHoldings(self, _print=False):
        # fetch token addresses
        token_addresses = self.getTokenAddresses()
        token_holdings = {
            self.secret_json['20_dex_contract_addr']: {},
            self.secret_json['my_addr']: {}
        }
        
        for key in token_holdings:
            for token_address in token_addresses:
                # function balanceOf(address token, address account) public view returns (uint){..}
                encoded_function_signature = self.w3.keccak(text=f'balanceOf(address,address)').hex()[:10]
                encoded_arg1 = remove_0x_prefix(token_address).lower().zfill(64)
                encoded_arg2 = remove_0x_prefix(key).lower().zfill(64)
                # prepare the call transaction
                transaction = {
                    'to': self.secret_json['20_dex_contract_addr'],
                    'data': encoded_function_signature + encoded_arg1 + encoded_arg2
                }
                # make the call
                result = self.w3.eth.call(transaction).hex()
                token_holdings[key][token_address] = int(result, 16)

        if _print:
            pretty = json.dumps(token_holdings, indent=4)
            print(pretty)
        
        # update local storage
        self.dex_tokens = np.array(list(token_holdings[self.secret_json['20_dex_contract_addr']].values()), dtype=np.float)
        self.self_tokens = np.array(list(token_holdings[self.secret_json['my_addr']].values()), dtype=np.float)

        return token_holdings

    def getTokenAddresses(self):
        # token1(), token2()
        token_addrs = []
        for token_idx in range(1, 3):
            encoded_function_signature = self.w3.keccak(text=f'token{token_idx}()').hex()[:10]
            # Prepare the call transaction
            transaction = {
                'to': self.secret_json['20_dex_contract_addr'],
                'data': encoded_function_signature
            }
            # Make the call
            result_addr_hex = remove_0x_prefix(self.w3.eth.call(transaction).hex())
            # Decode the result
            result_addr_hex = result_addr_hex[(32-20)*2:]
            result_address = self.w3.to_checksum_address(result_addr_hex)
            token_addrs.append(result_address)
        return token_addrs

    def printTokenHoldingsLocal(self):
        print(f'token holdings:')
        print(f'\t dex_tokens: {self.dex_tokens}')
        print(f'\t self_tokens: {self.self_tokens}')
        assert (self.dex_tokens + self.self_tokens == self.sum_tokens).all()

    def getSwapPrice(self, _from_idx, _amount: int):
        _to_idx = 0 if _from_idx else 1
        token_from = self.dex_tokens[_from_idx]
        token_to = self.dex_tokens[_to_idx]
        swap_amount = _amount * token_to / token_from
        return swap_amount

    def swap(self, _from_idx, _amount):
        assert self.self_tokens[_from_idx] >= _amount, "Not enough to swap"
        swapAmount = self.getSwapPrice(_from_idx, _amount)
        
        mod_amounts=np.array([-_amount, swapAmount])
        if _from_idx:
            mod_amounts=np.array([swapAmount, -_amount])

        self.self_tokens += mod_amounts
        self.dex_tokens -= mod_amounts

if __name__ == '__main__':
    va = Dex()
