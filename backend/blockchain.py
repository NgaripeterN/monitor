import os
import json
from web3 import Web3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Standard ERC20 ABI, focusing on the Transfer event and decimals function
ERC20_ABI = json.loads('[{"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Transfer","type":"event"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"payable":false,"stateMutability":"view","type": "function"}]')

# --- Configuration ---
# Load contract addresses from environment variables
CHAINS = {
    "ETH": {
        "rpc": os.getenv("ETH_RPC_URL"),
        "scan_blocks": 10000,
        "tokens": {
            "USDT": os.getenv("USDT_CONTRACT_ADDRESS_ETH"),
            "USDC": os.getenv("USDC_CONTRACT_ADDRESS_ETH"),
        }
    },
    "POLYGON": {
        "rpc": os.getenv("POLYGON_RPC_URL"),
        "scan_blocks": 40000,
        "tokens": {
            "USDT": os.getenv("USDT_CONTRACT_ADDRESS_POLYGON"),
            "USDC": os.getenv("USDC_CONTRACT_ADDRESS_POLYGON"),
        }
    },
    "BASE": {
        "rpc": os.getenv("BASE_RPC_URL"),
        "scan_blocks": 40000,
        "tokens": {
            "USDT": os.getenv("USDT_CONTRACT_ADDRESS_BASE"),
            "USDC": os.getenv("USDC_CONTRACT_ADDRESS_BASE"),
        }
    },
    "ARBITRUM": {
        "rpc": os.getenv("ARBITRUM_RPC_URL"),
        "scan_blocks": 100000,
        "tokens": {
            "USDT": os.getenv("USDT_CONTRACT_ADDRESS_ARBITRUM"),
            "USDC": os.getenv("USDC_CONTRACT_ADDRESS_ARBITRUM"),
        }
    },
}

MIN_STABLECOIN_AMOUNT = float(os.getenv("MIN_STABLECOIN_AMOUNT", "14.5"))

def check_payment_on_address(chain, address):
    """
    Scans recent blocks for a sufficient USDT or USDC transfer to a given address.

    Returns a tuple: (coin_type, transaction_hash, amount_in_token) if found, otherwise (None, None, 0).
    """
    if chain not in CHAINS:
        raise ValueError(f"Unknown chain: {chain}")

    config = CHAINS[chain]
    w3 = Web3(Web3.HTTPProvider(config["rpc"]))

    if not w3.is_connected():
        print(f"Could not connect to {chain} RPC.")
        return None, None, 0

    try:
        # Define the block range to scan
        latest_block = w3.eth.block_number
        from_block = latest_block - config["scan_blocks"]

        # Iterate over each token (USDT, USDC) for the given chain
        for coin_type, token_address in config["tokens"].items():
            if not token_address:
                continue # Skip if the token address is not configured

            token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
            
            try:
                token_decimals = token_contract.functions.decimals().call()
            except Exception:
                token_decimals = 6 # Default to 6 if the call fails

            min_amount_in_smallest_unit = int(MIN_STABLECOIN_AMOUNT * (10 ** token_decimals))

            # Create a filter for Transfer events to the user's unique address
            transfer_filter = token_contract.events.Transfer.create_filter(
                fromBlock=from_block,
                toBlock='latest',
                argument_filters={'to': address}
            )

            # Check all found transfer events for a sufficient amount
            for event in transfer_filter.get_all_entries():
                if event['args']['value'] >= min_amount_in_smallest_unit:
                    tx_hash = event['transactionHash'].hex()
                    amount_token = event['args']['value'] / (10 ** token_decimals)
                    print(f"Found payment on {chain}: {amount_token} {coin_type} in tx {tx_hash}")
                    return coin_type, tx_hash, amount_token

    except Exception as e:
        print(f"An error occurred while checking payment on {chain} for address {address}: {e}")
        return None, None, 0

    # If no qualifying payment is found for any token
    return None, None, 0

if __name__ == '__main__':
    # Example Usage:
    # Set up environment variables locally to test this script
    # test_address = "0x..." 
    # test_chain = "POLYGON" 
    # print(f"Checking for payments to {test_address} on {test_chain}...")
    # coin, tx, amt = check_payment_on_address(test_chain, test_address)
    # if coin:
    #     print(f"Success! Found {amt} {coin} in transaction: {tx}")
    # else:
    #     print("No sufficient USDT or USDC payment found in recent blocks.")
    pass
