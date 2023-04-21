from sha3 import keccak_256
import rlp


def get_encoded_function_signature(method_str):
    # https://piyolab.github.io/playground/ethereum/getEncodedFunctionSignature/
    return "0x" + keccak_256(method_str.encode('utf-8')).hexdigest()[:8]


def get_encoded_valueof(value, decimals=0):
    # 64 byte padding with 0-s
    value = int(value) * 10 ** decimals
    return format(value & 0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff, '064x')


def get_contract_address_from_creator_and_nonce(creator_address, nonce):
    # https://swende.se/blog/Ethereum_quirks_and_vulns.html
    # https://medium.com/@codetractio/inside-an-ethereum-transaction-fa94ffca912f
    if '0x' == creator_address[:2]:
        creator_address = creator_address[2:]
    # nonce should be in range(0, 256) TODO
    if nonce > 255:
        nonce = nonce % 256
    rlp_bytes = rlp.encode([bytes.fromhex(creator_address), bytes([nonce])])
    return '0x'+keccak_256(rlp_bytes).hexdigest()[-40:]
