import os
import json
from web3 import Web3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Standard ERC20 ABI, focusing on the Transfer event
ERC20_ABI = json.loads('[{"anonymous":false,"inputs":[{"indexed":true,"name":"_from","type":"address"},{"indexed":true,"name":"_to","type":"address"},{"indexed":false,"name":"_value","type":"uint256"}],"name":"Transfer","type":"event"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"payable":false,"stateMutability":"view","type": "function"}]')

# --- Configuration ---
CHAINS = {
    "ETH": {
        "rpc": os.getenv("ETH_RPC_URL"),
        "usdt_address": os.getenv("USDT_CONTRACT_ADDRESS_ETH"),
        "scan_blocks": 10000, # Approx. 1.5 days
    },
    "POLYGON": {
        "rpc": os.getenv("POLYGON_RPC_URL"),
        "usdt_address": os.getenv("USDT_CONTRACT_ADDRESS_POLYGON"),
        "scan_blocks": 40000, # Approx. 1 day
    },
    "BASE": {
        "rpc": os.getenv("BASE_RPC_URL"),
        "usdt_address": os.getenv("USDT_CONTRACT_ADDRESS_BASE"),
        "scan_blocks": 40000, # Approx. 1 day
    },
    "ARBITRUM": {
        "rpc": os.getenv("ARBITRUM_RPC_URL"),
        "usdt_address": os.getenv("USDT_CONTRACT_ADDRESS_ARBITRUM"),
        "scan_blocks": 100000, # Approx. 1 day
    },
}

MIN_USDT_AMOUNT = float(os.getenv("MIN_USDT_AMOUNT", "14.5"))

def check_payment_on_address(chain, address):
    """
    Scans recent blocks for a sufficient USDT transfer to a given address.

    Returns a tuple: (transaction_hash, amount_in_usdt) if found, otherwise (None, 0).
    """
    if chain not in CHAINS:
        raise ValueError(f"Unknown chain: {chain}")

    config = CHAINS[chain]
    w3 = Web3(Web3.HTTPProvider(config["rpc"]))

    if not w3.is_connected():
        print(f"Could not connect to {chain} RPC.")
        return None, 0

    try:
        usdt_contract = w3.eth.contract(address=config["usdt_address"], abi=ERC20_ABI)
        
        # Get USDT decimals to correctly calculate the amount
        try:
            usdt_decimals = usdt_contract.functions.decimals().call()
        except Exception:
            usdt_decimals = 6 # Fallback to 6 if call fails

        min_amount_in_smallest_unit = int(MIN_USDT_AMOUNT * (10 ** usdt_decimals))

        # Define the block range to scan
        latest_block = w3.eth.block_number
        from_block = latest_block - config["scan_blocks"]

        # Create a filter for Transfer events to the user's unique address
        transfer_filter = usdt_contract.events.Transfer.create_filter(
            fromBlock=from_block,
            toBlock='latest',
            argument_filters={'_to': address}
        )

        # Iterate through the found events
        for event in transfer_filter.get_all_entries():
            if event['args']['_value'] >= min_amount_in_smallest_unit:
                tx_hash = event['transactionHash'].hex()
                amount_usdt = event['args']['_value'] / (10 ** usdt_decimals)
                print(f"Found payment on {chain}: {amount_usdt} USDT in tx {tx_hash}")
                return tx_hash, amount_usdt

        # If no qualifying event is found
        return None, 0

    except Exception as e:
        print(f"An error occurred while checking payment on {chain} for address {address}: {e}")
        return None, 0

if __name__ == '__main__':
    # --- Example Usage ---
    # To test, you would need a recently used address that received USDT.
    # test_address = "0x..." 
    # test_chain = "POLYGON"
    # print(f"Checking for payments to {test_address} on {test_chain}...")
    # tx_hash, amount = check_payment_on_address(test_chain, test_address)
    # if tx_hash:
    #     print(f"Success! Found transaction: {tx_hash}, Amount: {amount} USDT")
    # else:
    #     print("No sufficient payment found in recent blocks.")
    pass
