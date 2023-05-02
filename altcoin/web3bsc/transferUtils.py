import sys
import logging
import datetime
import time
sys.path.append('./utils')
sys.path.append('reward_token')

from walletFactory import WalletFactory
from web3bsc import Web3BSC
from eth_utils import remove_0x_prefix, to_int, to_checksum_address, to_hex
from web3 import exceptions as w3_exceptions

class ChainAccountIterator:
    """ iterator that returns from-to account from account_path """
    def __init__(self, account_path):
        # sanity checks
        if not account_path or len(account_path) < 2:
            raise ValueError('account_path should contain at least 2 addresses')
        for a in account_path:
            if not isinstance(a, dict) and not isinstance(a, int) and not isinstance(a, tuple):
                raise ValueError('invalid account path')
        # local variables
        self.idx = 0
        self.account_path = account_path
        self.wf = WalletFactory(0)

    def __iter__(self):
        return self

    def __next__(self):
        if self.idx + 1 < len(self.account_path):
            account_from = self.get_address_dict(self.account_path[self.idx])
            account_to = self.get_address_dict(self.account_path[self.idx + 1])
            self.idx += 1
            return account_from, account_to
        else:
            raise StopIteration

    def append(self, addr):
        a = self.get_address_dict(addr)
        self.account_path.append(a)
        return a

    def get_address_dict(self, a):
        if isinstance(a, tuple):
            # first element -> index
            # second element wallet factory index
            a = WalletFactory(a[1]).get_address(a[0])
        elif isinstance(a, int):
            a = self.wf.get_address(a)
        if isinstance(a, dict):
            if 'name' not in a or \
               'addr' not in a or \
               'private_key' not in a:
                raise ValueError(f'invalid account dict in account_path {a}')
            return a
        else:
            raise ValueError('get_address_dict() unexpected error')


class TransferUtils:
    def __init__(self, gas_price=5, gas_limit_native=21000, gas_limit_token_max=600000):
        # web3bsc instance
        self.web3bsc = Web3BSC(barebone_init=True)
        # gas settings
        self.gas_limit_native = gas_limit_native
        self.gas_limit_token_max = gas_limit_token_max
        self.gas_price = self.web3bsc.w3.toWei(gas_price, 'Gwei')

    def convert_all_to_bnb(self, account, min_usd_value_to_convert=1.0):

        # get wallet token holdings
        balance_dict = self.web3bsc.get_wallet_balance(account['addr'], force_update=True)
        if not balance_dict['success']:
            logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|failed to get wallet holdings for', account['addr'])
            return

        w3 = self.web3bsc.w3
        # get nonce
        nonce = w3.eth.getTransactionCount(account['addr']) - 1
        pancakeswap_contract = self.web3bsc.data_json['contracts']['PancakeSwap']['contract']
            
        # iterate through tokens
        native_token_balance = None
        for b in balance_dict['balances']:
            if b['currency']['address'] == '-':
                # native token transferred last
                native_token_balance = b
                continue
            if b['value'] < min_usd_value_to_convert:
                logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|\t{b["currency"]["name"]} swap skipped due to low balance = {b["value"]}')
                continue
            logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|\tswap {b["currency"]["name"]} ({b["currency"]["address"]}) ${b["value"]:.2f}')

            # approve
            nonce += 1
            abi_txt = open('./ABIs/minimal_ABI', 'r').read().replace('\n', '')
            token_contract = w3.eth.contract(address=b['currency']['address'], abi=abi_txt)
            _txn = token_contract.functions.approve(
                spender=pancakeswap_contract.address,
                amount=b['balance']
            ).buildTransaction({
                'gas': self.gas_limit_token_max,
                'gasPrice': self.gas_price,
                'nonce': w3.toHex(nonce),
            })
            signed_txn = w3.eth.account.sign_transaction(_txn, private_key=account['private_key'])
            if self.web3bsc._ARMED_:
                tx_token = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
                tx_hash = w3.toHex(tx_token)
                tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                if not tx_receipt or tx_receipt['status'] == 0:
                    logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|\tapprove transaction {tx_hash} failed, exiting...')
                    return
                else:
                    logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|\tapprove successful {tx_hash}')
            else:
                logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'| not armed, transfer skipped')
                return
            
            # swap
            nonce += 1
            _txn = pancakeswap_contract.functions.swapExactTokensForETHSupportingFeeOnTransferTokens(
                # payable amount of input tokens
                amountIn=b['balance'],
                # minimum amount tokens to receive
                # specify slippage with this, 0 would look suspicious
                amountOutMin=0,
                # pay with wbnb
                path=[b['currency']['address'], self.web3bsc.data_json['addrs']['WBNB']],
                # receive address
                to=account['addr'],
                # deadline = now + 5min
                deadline=(int(time.time()) + 1 * 60)
            ).buildTransaction({
                'gas': self.gas_limit_token_max,
                'gasPrice': self.gas_price,
                'nonce': w3.toHex(nonce),
            })
            
            signed_txn = w3.eth.account.sign_transaction(_txn, private_key=account['private_key'])
            if self.web3bsc._ARMED_:
                tx_token = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
                tx_hash = w3.toHex(tx_token)
                tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                if not tx_receipt or tx_receipt['status'] == 0:
                    logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|\ttransaction {tx_hash} failed, exiting...')
                    return
                else:
                    logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|\tsuccessful swap to BNB {tx_hash} of {b["balance"]} (${b["value"]}) {b["currency"]["name"]} token')
            else:
                logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'| not armed, transfer skipped')
                return
            time.sleep(4)

    def transfer_all(self, accounts_from, account_final, min_usd_value_to_transfer=1.0):
        # BNB transferred though all accounts_from in chain
        # other tokens transferred directly to account_final

        # create iterator
        account_iterator = ChainAccountIterator(accounts_from)
        # last address should be final
        account_final = account_iterator.append(account_final)
        # number of pairs
        num_of_address_pairs = len(accounts_from)
        progress = 0

        for account_from, account_to in account_iterator:
            # if from == to nothing to do
            if account_from['addr'] == account_final['addr']:
                continue

            # get wallet token holdings
            balance_dict = self.web3bsc.get_wallet_balance(account_from['addr'], force_update=True)
            if not balance_dict['success']:
                logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|failed to get wallet holdings for', account_from['addr'])
                continue

            logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|#{accounts_from[progress]} transferring tokens {account_from["addr"]} --> {account_final["addr"]}')
            progress += 1

            w3 = self.web3bsc.w3
            # get 'from' address nonce
            nonce = w3.eth.getTransactionCount(account_from['addr']) - 1

            # iterate through tokens
            native_token_balance = None
            for b in balance_dict['balances']:
                if b['currency']['address'] == '-':
                    # native token transferred last
                    native_token_balance = b
                    continue
                if b['value'] < min_usd_value_to_transfer:
                    logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|\t{b["currency"]["name"]} transfer skipped due to low balance = {b["value"]}')
                    continue
                logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|\ttransferring {b["currency"]["name"]} ({b["currency"]["address"]}) ${b["value"]:.2f}')

                swap_to_bnb = False
                # if b['value'] < 10:
                #     swap_to_bnb = True

                if swap_to_bnb:
                    # convert to bnb tokens under $10 value
                    nonce += 1
                    pancakeswap_contract = self.web3bsc.data_json['contracts']['PancakeSwap']['contract']
                    _txn = pancakeswap_contract.functions.swapExactTokensForETHSupportingFeeOnTransferTokens(
                        # payable amount of input tokens
                        amountIn=b['balance'],
                        # minimum amount tokens to receive
                        # specify slippage with this, 0 would look suspicious
                        amountOutMin=0,
                        # pay with wbnb
                        path=[b['currency']['address'], self.web3bsc.data_json['addrs']['WBNB']],
                        # receive address
                        to=account_from['addr'],
                        # deadline = now + 5min
                        deadline=(int(time.time()) + 50 * 60)
                    ).buildTransaction({
                        'gas': self.gas_limit_token_max,
                        'gasPrice': self.gas_price,
                        'nonce': w3.toHex(nonce),
                    })
                else:
                    recipient = remove_0x_prefix(account_final['addr']).lower().zfill(64)
                    amount = remove_0x_prefix(to_hex(b['balance'])).zfill(64)
                    # transfer, 0xa9059cbb == transfer(address,uint256)
                    data = '0xa9059cbb' + recipient + amount
                    nonce += 1
                    _txn = {
                        'to': b['currency']['address'],
                        'data': data,
                        'nonce': w3.toHex(nonce),
                        'chainId': self.web3bsc.chain_id,
                        'gas': self.gas_limit_token_max,
                        'gasPrice': self.gas_price,
                    }
                    # try:
                    #     gas_estimate = w3.eth.estimate_gas(_txn)
                    # except w3_exceptions.ContractLogicError as err:
                    #     logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|ERROR: execution will fail with "{err}"')
                    #     return
                    # if gas_estimate > self.gas_limit_token_max:
                    #     logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|ERROR: overpriced transfer: {gas_estimate} > {self.gas_limit_token_max}')
                    #     return
                    # # set gas
                    # _txn['gas'] = gas_estimate
                    # _txn['gasPrice'] = self.gas_price

                signed_txn = w3.eth.account.sign_transaction(_txn, private_key=account_from['private_key'])
                if self.web3bsc._ARMED_:
                    tx_token = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
                    tx_hash = w3.toHex(tx_token)
                    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                    if not tx_receipt or tx_receipt['status'] == 0:
                        logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|\ttransaction {tx_hash} failed, exiting...')
                        return
                    else:
                        if swap_to_bnb:
                            logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|\tsuccessful swap to BNB {tx_hash} of {b["balance"]} (${b["value"]}) {b["currency"]["name"]} token')
                        else:
                            logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|\tsuccessful transaction {tx_hash} of {b["balance"]} (${b["value"]}) {b["currency"]["name"]} token')
                else:
                    logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|not armed, transfer skipped')
                    return

            # transfer native token
            time.sleep(7)  # wait for native bnb update..
            logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|transferring native token {account_from["addr"]} --> {account_to["addr"]}')
            native_token_updated_balance = w3.eth.get_balance(account_from["addr"])
            value = native_token_updated_balance - self.gas_limit_native * self.gas_price
            if value < 0.0:
                logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|\tno native token to transfer')
                continue
            nonce += 1
            # print('balance =', b['balance'])
            # print('max gas =', self.gas_limit_native * self.gas_price)
            # print('value   =', value)

            _txn = {
                'to': account_to['addr'],
                'value': value,
                'gas': self.gas_limit_native,
                'gasPrice': self.gas_price,
                'nonce': w3.toHex(nonce),
                'chainId': self.web3bsc.chain_id
            }
            signed_txn = w3.eth.account.sign_transaction(_txn, private_key=account_from['private_key'])
            if self.web3bsc._ARMED_:
                tx_token = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
                tx_hash = w3.toHex(tx_token)
                tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                if not tx_receipt or tx_receipt['status'] == 0:
                    logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|transaction {tx_hash} failed, exiting...')
                    return
                else:
                    logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|\tsuccessful transaction {tx_hash} of {native_token_updated_balance} native token')
            else:
                logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'not armed, transfer skipped')
                return


def main():
    tu = TransferUtils()

    account = WalletFactory(2).get_address(40)
    tu.convert_all_to_bnb(account)
    exit()

    # accounts_from = list(reversed(range(3)))
    account_final = (0, 2)  # tuple(<account index>, <wallet factory index>)
    # accounts_from = list(range(13, 14))
    accounts_from = [0, account_final]
    logging.info(datetime.datetime.now().strftime("%H%M%S.%f") + f'|accounts_from={accounts_from}, account_final={account_final}')
    tu.transfer_all(accounts_from, account_final)


if __name__ == '__main__':
    main()
