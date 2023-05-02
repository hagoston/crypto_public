from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_abi.packed import encode_abi_packed
import time


BSC_INFO = {
    'name': 'BSC',
    'router_name': 'PancakeSwapV2',
    'router_address': '0x10ED43C718714eb63d5aA57B78B54704E256024E',
    'factory_address': '0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73',
    'hexadem': '0x00fb7f630766e6a796048ea87d01acd3068e8ff67d078148a3fa3f4a84f69bd5',
    'explorer': 'https://bscscan.com',
    'rpc': 'https://bsc-dataseed.binance.org:443',
    'chain_id': 56,
    'base_token_address': '0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c',
    'usd_token_address': '0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56'
}


class DirectWeb3:
    '''
    This class executes direct function calls without the need of web3.Contract class

    Warning:
        - no check for function existence
        - address arguments should be in Web3.toChecksumAddress() format
    '''
    def __init__(self, network_info=BSC_INFO, w3=None):
        # local RPC
        self.network_info = network_info
        if not w3:
            self.w3 = Web3(Web3.HTTPProvider(self.network_info['rpc']))
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        else:
            self.w3 = w3
        self.factory_addr = self.network_info['factory_address']
        self.hexadem_ = self.network_info['hexadem']
        self.base_token_addr = self.network_info['base_token_address']
        
        self.byteorder = 'big'
        self.swap_trading_fee = 0.25     # [%] https://docs.pancakeswap.finance/products/pancakeswap-exchange/trade
        # keep reserves in memory for some time
        self.reserves_buffer_timeout = 60       # 1 min
        self.reserves_buffer = {}

    def get_swap_amount_out(self, token0_amount_in, reserve_in, reserve_out):
        """
        given an input amount of an asset and pair reserves, returns the maximum output amount of the other asset
        https://github.com/pancakeswap/pancake-swap-periphery/blob/master/contracts/libraries/PancakeLibrary.sol
        """
        token0_amount_in_with_fee = token0_amount_in * (1000 - self.swap_trading_fee * 10)
        numerator = token0_amount_in_with_fee * reserve_out
        denominator = reserve_in * 1000 + token0_amount_in_with_fee
        try:
            return numerator / denominator
        except:
            return 0

    def get_swap_amount_in(self, token1_amount_out, reserve_in, reserve_out):
        """
        given an output amount of an asset and pair reserves, returns a required input amount of the other asset
        https://github.com/pancakeswap/pancake-swap-periphery/blob/master/contracts/libraries/PancakeLibrary.sol
        """
        numerator = reserve_in * 1000
        denominator = (reserve_out - token1_amount_out) * (1000 - self.swap_trading_fee * 10)
        return numerator / (denominator + 1)

    def get_swap_amounts_out(self, token0_amount_in, path_addrs, w3=None):
        """
        performs chained get_swap_amount_out calculations on any number of pairs
        """
        assert len(path_addrs) >= 2, 'INVALID_PATH: minimum 2 addresses needed for swap'
        amounts = [token0_amount_in]
        for i in range(len(path_addrs)-1):
            reserve0, reserve1 = self.getSortedReserves(path_addrs[i], path_addrs[i + 1], w3)
            amounts.append(self.get_swap_amount_out(amounts[i], reserve0, reserve1))
        return amounts

    def get_pancake_pair_address(self, token0, token1=None):
        """
        calculate pancake pair from token addresses
        https://stackoverflow.com/questions/68424735/compute-pancake-pair-address-via-python3
        """
        if not token1:
            # default wbnb
            token1 = self.base_token_addr
        if token0.lower() > token1.lower():
            # https://docs.uniswap.org/protocol/V2/reference/smart-contracts/factory
            # token0 is guaranteed to be strictly less than token1 by sort order
            token0, token1 = token1, token0
        abi_encoded_1 = encode_abi_packed(['address', 'address'], (token0, token1))
        salt_ = self.w3.solidityKeccak(['bytes'], ['0x' + abi_encoded_1.hex()])
        abi_encoded_2 = encode_abi_packed(['address', 'bytes32'], (self.factory_addr, salt_))
        resPair = self.w3.solidityKeccak(['bytes', 'bytes'], ['0xff' + abi_encoded_2.hex(), self.hexadem_])[12:]
        return self.w3.toChecksumAddress(resPair.hex())

    def getReserves(self, contract_addr, w3=None):
        """
        Pancakeswap v2 PancakePair / getReserves()
        Returns:
            [_reserve0, _reserve1, _blockTimestampLast]
        """
        if not w3:
            w3 = self.w3
        resp = w3.eth.call({
            'to': contract_addr,
            'data': '0x0902f1ac'
        })
        return [int.from_bytes(resp[:32], byteorder=self.byteorder, signed=False),
                int.from_bytes(resp[32:64], byteorder=self.byteorder, signed=False),
                int.from_bytes(resp[64:], byteorder=self.byteorder, signed=False)]

    def getSortedReserves(self, tokenA, tokenB, w3=None):
        """
        getReserves in tokenA, B order
        """
        if not w3:
            w3 = self.w3
        # get token pair address
        ppair_addr = self.get_pancake_pair_address(tokenA, tokenB)
        # check in buffer
        ress = None
        if ppair_addr in self.reserves_buffer.keys():
            # check timeout
            if self.reserves_buffer[ppair_addr]['time'] + self.reserves_buffer_timeout > time.time():
                ress = self.reserves_buffer[ppair_addr]['reserves']
        # get reserves from pair contract
        if not ress:
            ress = self.getReserves(ppair_addr)
            self.reserves_buffer[ppair_addr] = {
                'time': time.time(),
                'reserves': ress
            }
        # swap if needed
        if tokenA.lower() > tokenB.lower():
            return ress[1], ress[0]
        return ress[0], ress[1]

    def symbol(self, contract_addr, w3=None):
        """
        Returns contract symbol
        """
        if not w3:
            w3 = self.w3

        try:
            resp = w3.eth.call({
                'to': contract_addr,
                'data': '0x95d89b41'
            })
            symbol_length = 0
            symbol = ''
            for i in range(int(len(resp)/32)):
                resp_crop = resp[i*32:(i+1)*32]
                symbol = resp_crop[:symbol_length].decode('utf-8')
                symbol_length = int.from_bytes(resp_crop, byteorder=self.byteorder, signed=False)
                if symbol_length > len(resp) - (i+1)*32:
                    symbol_length = 0
            if not symbol:
                # exception see 0xb8e3399d81b76362b76453799c95FEE868c728Ea
                symbol = resp.decode('utf-8').replace('\x00', '')
            if not symbol:
                symbol = 'UNKNOWN_SYMBOL'
            return symbol
        except:
            return 'UNKOWN_SYMBOL'

    def name(self, contract_addr, w3=None):
        """
        Returns contract name
        """
        if not w3:
            w3 = self.w3
        try:
            resp = w3.eth.call({
                'to': contract_addr,
                'data': '0x06fdde03'
            })
            name_length = 0
            name = ''
            for i in range(int(len(resp)/32)):
                resp_crop = resp[i*32:(i+1)*32]
                name = resp_crop[:name_length].decode('utf-8')
                name_length = int.from_bytes(resp_crop, byteorder=self.byteorder, signed=False)
                if name_length > len(resp) - (i+1)*32:
                    name_length = 0
            if not name:
                # exception see 0xb8e3399d81b76362b76453799c95FEE868c728Ea
                name = resp.decode('utf-8').replace('\x00', '')
        except:
            name = 'UNKNOWN_NAME'
        return name

    def decimals(self, contract_addr, w3=None):
        """
        Returns contract decimals
        """
        if not w3:
            w3 = self.w3
        resp = w3.eth.call({
            'to': contract_addr,
            'data': '0x313ce567'
        })
        return int.from_bytes(resp, byteorder=self.byteorder, signed=False)

    def balanceOf(self, contract_addr, addr, w3=None):
        """
        Returns:
             contract_addr.balanceOf(addr)
        """
        if not w3:
            w3 = self.w3
        if '-' == contract_addr:
            return self.w3.eth.get_balance(addr)
        resp = w3.eth.call({
            'to': contract_addr,
            'data': '0x70a08231' + addr[2:].lower().zfill(64)
        })
        return int.from_bytes(resp, byteorder=self.byteorder, signed=False)

    def get_custom_address(self, contract_addr, enc_data, w3=None):
        """
        Returns an address
        """
        if not w3:
            w3 = self.w3
        resp = w3.eth.call({
            'to': contract_addr,
            'data': enc_data
        })
        return w3.toChecksumAddress(resp.hex()[-40:])
