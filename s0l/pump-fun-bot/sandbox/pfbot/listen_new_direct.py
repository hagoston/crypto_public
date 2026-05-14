import asyncio
import json
import websockets
import base58
import base64
import struct
import sys
import os
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import WSS_ENDPOINT, PUMP_PROGRAM

# Load the IDL JSON file
with open('../idl/pump_fun_idl.json', 'r') as f:
    idl = json.load(f)

# Extract the "create" instruction definition
create_instruction = next(instr for instr in idl['instructions'] if instr['name'] == 'create')

def parse_create_instruction(data):
    if len(data) < 8:
        return None
    offset = 8
    parsed_data = {}

    # Parse fields based on CreateEvent structure
    fields = [
        ('name', 'string'),
        ('symbol', 'string'),
        ('uri', 'string'),
        ('mint', 'publicKey'),
        ('bondingCurve', 'publicKey'),
        ('user', 'publicKey'),
    ]

    try:
        for field_name, field_type in fields:
            if field_type == 'string':
                length = struct.unpack('<I', data[offset:offset+4])[0]
                offset += 4
                value = data[offset:offset+length].decode('utf-8')
                offset += length
            elif field_type == 'publicKey':
                value = base58.b58encode(data[offset:offset+32]).decode('utf-8')
                offset += 32

            parsed_data[field_name] = value

        return parsed_data
    except:
        return None

def parse_buysell_instruction(data):
    if len(data) < 8:
        return None
    offset = 8
    parsed_data = {}

    '''
    https://solscan.io/tx/3ynsJyhcLTj2WHFsSToYmo2GKtxebaqBQwu7dNeWXm4dJMPe7gUAGy4Z3ZPYY6C8R86oaUN4WZ73x7cUUEGMHscm
    {
        "mint": {
            "type": "publicKey",
            "data": "VXRfww2H7ek5cM6DesUVrNb8f7ccMPcKsfTXqR7pump"
        },
        "solAmount": {
            "type": "u64",
            "data": "90367186"
        },
        "tokenAmount": {
            "type": "u64",
            "data": "3222426289866"
        },
        "isBuy": {
            "type": "bool",
            "data": false
        },
        "user": {
            "type": "publicKey",
            "data": "Dq7hScUgkufcunYYCUyh92SghDv5Q7nbHXF5V1EBriVs"
        },
        "timestamp": {
            "type": "i64",
            "data": "1736337529"
        },
        "virtualSolReserves": {
            "type": "u64",
            "data": "30000000105"
        },
        "virtualTokenReserves": {
            "type": "u64",
            "data": "1072999999601594"
        }
    }
    '''
    fields = [
        ('mint', 'publicKey'),
        ('solAmount', 'u64'),
        ('tokenAmount', 'u64'),
        ('isBuy', 'bool'),
        ('user', 'publicKey'),
        ('timestamp', 'i64'),
        ('virtualSolReserves', 'u64'),
        ('virtualTokenReserves', 'u64')
    ]
    try:
        for field_name, field_type in fields:
            if field_type == 'u64':
                value = struct.unpack_from('<Q', data, offset)[0]
                offset += 8
            elif field_type == 'i64':
                value = struct.unpack_from('<q', data, offset)[0]
                offset += 8
            elif field_type == 'bool':
                value = struct.unpack_from('<?', data, offset)[0]
                offset += 1
            elif field_type == 'publicKey':
                value = base58.b58encode(data[offset:offset+32]).decode('utf-8')
                offset += 32

            parsed_data[field_name] = value


        # Extract values
        virtual_sol_reserves = parsed_data['virtualSolReserves']
        virtual_token_reserves = parsed_data['virtualTokenReserves']
        sol_amount = parsed_data['solAmount']
        token_amount = parsed_data['tokenAmount']
        is_buy = parsed_data['isBuy']

        if virtual_token_reserves > 0:
            # Calculate MC before the transaction
            current_price = virtual_sol_reserves / virtual_token_reserves
            market_cap_before = current_price * 1e9  # Total supply is 1 billion

            # Update reserves based on the transaction
            if is_buy:
                new_virtual_sol_reserves = virtual_sol_reserves + sol_amount
                new_virtual_token_reserves = virtual_token_reserves - token_amount
            else:
                new_virtual_sol_reserves = virtual_sol_reserves - sol_amount
                new_virtual_token_reserves = virtual_token_reserves + token_amount

            # Calculate MC after the transaction
            new_price = new_virtual_sol_reserves / new_virtual_token_reserves
            market_cap_after = new_price * 1e9

            # Add results to parsed_data
            parsed_data['marketCapSolBefore'] = market_cap_before
            parsed_data['marketCapSol'] = market_cap_after

        return parsed_data
    except:
        return None


def print_transaction_details(log_data):
    print(f"Signature: {log_data.get('signature')}")
    
    for log in log_data.get('logs', []):
        if log.startswith("Program data:"):
            try:
                data = base58.b58decode(log.split(": ")[1]).decode('utf-8')
                print(f"Data: {data}")
            except:
                pass

async def listen_for_new_tokens():
    while True:
        try:
            async with websockets.connect(WSS_ENDPOINT) as websocket:
                subscription_message = json.dumps({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "logsSubscribe",
                    "params": [
                        {"mentions": [str(PUMP_PROGRAM)]},
                        {"commitment": "processed"}
                    ]
                })
                await websocket.send(subscription_message)
                print(f"Listening for new token creations from program: {PUMP_PROGRAM}")

                # Wait for subscription confirmation
                response = await websocket.recv()
                print(f"Subscription response: {response}")

                while True:
                    try:
                        response = await websocket.recv()
                        data = json.loads(response)
                        
                        if 'method' in data and data['method'] == 'logsNotification':
                            log_data = data['params']['result']['value']
                            if log_data["err"]:
                                continue

                            pretty_log_data = json.dumps(log_data, indent=4)
                            logs = log_data.get('logs', [])
                            print(pretty_log_data)
                            print("-" * 20)

                            itypes = ['Create', 'Buy', 'Sell']
                            if any(("Program log: Instruction: "+t in log for log in logs) for t in itypes):
                                itype = None
                                for log in logs:
                                    if log.split("Program log: Instruction: ")[-1] in itypes:
                                        itype = log.split("Program log: Instruction: ")[-1]
                                    
                                    if "Program data:" in log:
                                        try:
                                            encoded_data = log.split(": ")[1]
                                            decoded_data = base64.b64decode(encoded_data)
                                            if "Create" == itype:
                                                parsed_data = parse_create_instruction(decoded_data)
                                            elif itype in ["Buy", "Sell"]:
                                                parsed_data = parse_buysell_instruction(decoded_data)
                                            else:
                                                continue
                                            if parsed_data:
                                                print("Signature:", log_data.get('signature'))
                                                for key, value in parsed_data.items():
                                                    print(f"{key}: {value}", time.time() if key == "timestamp" else "")
                                                print("##########################################################################################")
                                        except Exception as e:
                                            print(f"Failed to decode: {log}")
                                            print(f"Error: {str(e)}")
                                
                    except Exception as e:
                        print(f"An error occurred while processing message: {e}")
                        break

        except Exception as e:
            print(f"Connection error: {e}")
            print("Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":

    if 0:
        encoded_data = "vdt/007mYe5X/UKK2E79RSPmCX9owr8N1dV9mY6K5SldGxkJQlU8v3+5fQcAAAAAqA1SPhIEAAAB58UUkIq8K8nXCRdfvDdlH2XjxPQgo1BsDpFYcieF1/N5aH5nAAAAAJVloQMHAAAAm8t8CdHLAwCVuX0HAAAAAJszar0/zQIA"
        decoded_data = base64.b64decode(encoded_data)
        parsed_data = parse_buysell_instruction(decoded_data)
        for key, value in parsed_data.items():
            print(f"{key}: {value}")
        exit()

    asyncio.run(listen_for_new_tokens())