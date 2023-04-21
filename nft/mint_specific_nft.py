import sys
sys.path.append('../../shitcoin/utils')
sys.path.append('../../shitcoin/web3bsc')
sys.path.append('../../shitcoin/web3bsc/reward_token')

from web3bsc import Web3BSC
from web3 import Web3
from web3.middleware import geth_poa_middleware
from sha3 import keccak_256
from eth_abi.packed import encode_abi_packed
from eth_utils import remove_0x_prefix, to_int, to_checksum_address, to_hex
import time
import multiprocessing as mp
import logging
import datetime
import random

# search and buy legendary NFTs

class LegendaryNFT:
    def __init__(self):
        self._ARMED_ = False
        # web3bsc instance
        self.web3bsc = Web3BSC()
        # local web3 instance
        self.w3 = self.web3bsc.create_w3_connection(node_provider=self.web3bsc.node_provider)
        # check nft contract loaded
        nft_contract_name = self.web3bsc.trading_details['contract_to_listen']
        assert(nft_contract_name == '*_NFT')
        self.nft_contract = self.web3bsc.data_json['contracts'][nft_contract_name]['contract']

    def run(self, nft_id=-1):
        logging.info(datetime.datetime.now().strftime('%H%M%S.%f') + f' start nft hunting for id={nft_id}')
        logging.info(datetime.datetime.now().strftime('%H%M%S.%f') + f' with addr ' + self.web3bsc.data_json['private_data']['private_addresses'][0]['addr'])

        # start block number getter
        th = mp.Process(target=self.web3bsc.poll_block_num)
        th.start()

        b_num = -1                  # target block for nft mint
        b_ts = -1                   # target block timestamp
        lb_dts = []                 # local - block timestamp delta averaging
        lb_dt_avg = 2.5             # initial lb_dts average
        prev_block_num = -1         # process only newer blocks
        mint_done = False           # is mint done

        while 1:
            bs_to_rm = []           # blocks to remove from list
            local_ts = time.time()  # local ts

            # is it time for minting?
            if not mint_done and b_ts > 0:
                # TODO: check minted already, mint price
                # calc current block ts with local time
                trigger_ts = b_ts + lb_dt_avg
                # send mint 2 blocks before actual time
                shift_no_blocks = 2
                trigger_ts -= shift_no_blocks * 3
                if trigger_ts <= local_ts:
                    # lets mint
                    logging.info(datetime.datetime.now().strftime('%H%M%S.%f') + f' lets mint #{b_num} ({b_ts}) nft_id={id_}')

                    nft_to_buy = 1  # max 5
                    mint_price = self.nft_contract.functions.MINT_PRICE().call()
                    min_mint_price = self.nft_contract.functions.price1().call()
                    mint_price = max(mint_price, min_mint_price)

                    logging.info(datetime.datetime.now().strftime('%H%M%S.%f') + f'| mint_price={mint_price}')

                    sender = self.web3bsc.data_json['private_data']['private_addresses'][0]
                    _txn = self.nft_contract.functions.mint(nft_to_buy).buildTransaction({
                        'chainId': self.web3bsc.chain_id,
                        'from': sender['addr'],
                        'gas': random.randint(1000000, 2000000),
                        'gasPrice': self.w3.toWei(5.0, 'Gwei'),
                        'nonce': self.w3.toHex(self.w3.eth.getTransactionCount(sender['addr'])),
                        'value': mint_price * nft_to_buy
                    })
                    signed_txn = self.w3.eth.account.sign_transaction(_txn, private_key=sender['private_key'])
                    if self._ARMED_:
                        tx_token = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
                        tx_hash = self.w3.toHex(tx_token)
                    else:
                        tx_hash = '0x0'
                    logging.info(datetime.datetime.now().strftime('%H%M%S.%f') + '| MINT TX ' + tx_hash)

                    return

            # check for new blocks
            for b in self.web3bsc.block_list:
                # get most recent block number
                block_num = b['block_num']

                if prev_block_num < block_num:
                    # get block with header
                    try:
                        block = self.w3.eth.get_block(block_num)
                        # block timestamp
                        block_ts = block.timestamp
                        # local-block
                        lb_dt = local_ts - block_ts
                        lb_dts.append(lb_dt)
                        lb_dt_avg = sum(lb_dts) / len(lb_dts)

                        new_target_needed = False
                        # remaining blocks
                        block_dt = b_num - block_num
                        if block_dt < 0:
                            # target in da past
                            new_target_needed = True
                        # check expected block ts
                        if 3 * block_dt + block_ts != b_ts:
                            # 3sec block dt messed up
                            new_target_needed = True

                        if new_target_needed:
                            b_num, b_ts, id_ = self.search_for_nft(nft_id, block_num)
                            if self.is_minted(id_):
                                return
                            logging.info(datetime.datetime.now().strftime('%H%M%S.%f') + f' new search done: #{b_num} ({b_ts}) nft_id={id_}')
                        else:
                            dt_str = self.dt_str(block_ts, b_ts)
                            logging.info(datetime.datetime.now().strftime('%H%M%S.%f')
                                         + f' #{block_num} ({block_ts})'
                                         + f', block_dt={block_dt},'
                                         + dt_str
                                         + f', lb_dt={lb_dt:.2f} (avg={lb_dt_avg:.2f})')
                    except:
                        # e = sys.exc_info()[0]
                        # logging.error('worker thread failed ' + e.__name__ + ' ' + e.__doc__.replace('\n', ''))
                        pass
                    # update prev block num
                    prev_block_num = block_num
                # remove from block list
                bs_to_rm.append(b)

            # remove used blocks from list
            with self.web3bsc.block_list_lock:
                for b_to_rm in bs_to_rm:
                    self.web3bsc.block_list.remove(b_to_rm)

            # some sleep
            time.sleep(0.01)

    def is_minted(self, id_):
        is_minted = self.nft_contract.functions.isMint(id_).call()
        if is_minted:
            logging.info(datetime.datetime.now().strftime('%H%M%S.%f') + f' id #{id_} already minted')
        else:
            logging.info(datetime.datetime.now().strftime('%H%M%S.%f') + f' id #{id_} not minted yet, continue')
        return is_minted

    @staticmethod
    def calc_nft_id(block_ts):
        id_ = to_int(Web3.solidityKeccak(['uint256', 'uint256'], (block_ts, 0))) % 1000
        id_ = id_ + 1
        return id_

    @staticmethod
    def dt_str(t0, t1):
        countdown_sec = t1 - t0
        countdown_min = int(countdown_sec / 60)
        countdown_h = int(countdown_min / 60)
        countdown_min -= countdown_h * 60
        countdown_sec -= (countdown_h * 60 * 60 + countdown_min * 60)
        countdown_str = f' {countdown_h:02}h {countdown_min:02}m {countdown_sec:02}s'
        return countdown_str

    def search_for_nft(self, nft_id=-1, start_block_num=None):
        if not start_block_num:
            # get current block
            start_block_num = self.w3.eth.get_block('latest')['number']
        # block timestamp
        block_num = start_block_num
        block_ts = self.w3.eth.get_block(block_num).timestamp
        while 1:
            # expected ts to increment by 3sec
            block_num += 1
            block_ts += 3
            # calc nft id
            id_ = self.calc_nft_id(block_ts)
            # any legendary nft-s or specific id
            if (nft_id < 0) or (id_ == nft_id):
                return block_num, block_ts, id_


def main():
    lnft = LegendaryNFT()
    lnft.run(nft_id=300)
    lnft.web3bsc.mp_exit_main_loop.value = True


if __name__ == '__main__':
    main()
