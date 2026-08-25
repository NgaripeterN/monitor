import os
import json
from web3 import Web3

# Standard ERC20 ABI, focusing on the Transfer event and decimals function
ERC20_ABI = json.loads('[{"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Transfer","type":"event"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"payable":false,"stateMutability":"view","type": "function"}]')

# This margin allows for small discrepancies in payment amount (e.g. from exchange withdrawal fees)
MARGIN_OF_ERROR = 0.1 

def check_payment_on_address(chain: str, rpc_url: str, deposit_address: str, required_price: float, token_contracts: dict):
    """
    Scans recent blocks for a sufficient token transfer to a given address.

    Args:
        chain (str): The name of the chain (e.g., 'ETH').
        rpc_url (str): The RPC URL for the chain.
        deposit_address (str): The unique address to check for payments.
        required_price (float): The target price of the product.
        token_contracts (dict): A dictionary of tokens to check, e.g., {'USDT': '0x...', 'USDC': '0x...'}.

    Returns:
        A tuple: (coin_type, transaction_hash, amount_in_token) if found, otherwise (None, None, 0).
    """
    if not rpc_url:
        print(f"ERROR: RPC URL for {chain} is not configured.")
        return None, None, 0

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print(f"ERROR: Could not connect to {chain} RPC at {rpc_url}.")
        return None, None, 0

    try:
        checksum_user_address = Web3.to_checksum_address(deposit_address)
        
        # Define reasonable block scan ranges per chain to prevent RPC rate limits/timeouts
        scan_blocks = 3000
        if chain == "ETH":
            scan_blocks = 1000
        elif chain == "POLYGON":
            scan_blocks = 3000
        elif chain == "ARBITRUM":
            scan_blocks = 10000

        latest_block = w3.eth.block_number
        from_block = max(0, latest_block - scan_blocks)

        transfer_topic = w3.to_hex(w3.keccak(text="Transfer(address,address,uint256)"))
        padded_to_address = "0x" + checksum_user_address[2:].lower().rjust(64, '0')

        for coin_type, token_address in token_contracts.items():
            if not token_address:
                continue

            checksum_token_address = Web3.to_checksum_address(token_address)
            token_contract = w3.eth.contract(address=checksum_token_address, abi=ERC20_ABI)
            
            try:
                token_decimals = token_contract.functions.decimals().call()
            except Exception:
                token_decimals = 6 if coin_type == 'USDC' else 18 # Educated guess

            required_amount = required_price - MARGIN_OF_ERROR
            min_amount_in_smallest_unit = int(required_amount * (10 ** token_decimals))

            filter_params = {
                'fromBlock': from_block,
                'toBlock': 'latest',
                'address': checksum_token_address,
                'topics': [transfer_topic, None, padded_to_address]
            }

            try:
                logs = w3.eth.get_logs(filter_params)
            except Exception as rpc_err:
                print(f"RPC get_logs warning for {chain} ({coin_type}): {rpc_err}")
                continue

            for log in logs:
                data_hex = log['data'].hex() if isinstance(log['data'], bytes) else log['data']
                value = int(data_hex, 16)
                if value >= min_amount_in_smallest_unit:
                    tx_hash = log['transactionHash'].hex() if isinstance(log['transactionHash'], bytes) else log['transactionHash']
                    amount_token = value / (10 ** token_decimals)
                    return coin_type, tx_hash, amount_token

    except Exception as e:
        print(f"An error occurred while checking payment on {chain} for address {deposit_address}: {e}")
        return None, None, 0

    return None, None, 0
