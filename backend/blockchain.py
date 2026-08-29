import os
import json
import requests
from web3 import Web3

# Standard ERC20 ABI, focusing on the Transfer event and decimals function
ERC20_ABI = json.loads('[{"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Transfer","type":"event"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"payable":false,"stateMutability":"view","type": "function"}]')

# This margin allows for small discrepancies in payment amount (e.g. from exchange withdrawal fees)
MARGIN_OF_ERROR = 0.1 

def check_solana_payment(rpc_url: str, deposit_address: str, required_price: float, token_contracts: dict):
    """
    Checks Solana blockchain for SPL token transfers (USDC / USDT) to the deposit address.

    Args:
        rpc_url (str): The Solana RPC URL.
        deposit_address (str): The Base58 deposit address.
        required_price (float): Target price.
        token_contracts (dict): Token mint addresses, e.g. {'USDC': 'EPjFW...', 'USDT': 'Es9vM...'}.

    Returns:
        (coin_type, tx_hash, amount_paid) or (None, None, 0)
    """
    if not rpc_url:
        rpc_url = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

    # Smart margin: Allows up to $0.50 tolerance (or 5% for smaller orders) to absorb CEX withdrawal fees
    margin = min(0.50, required_price * 0.05) if required_price > 5.0 else min(0.10, required_price * 0.10)
    required_amount = max(0.01, required_price - margin)

    # 1. Direct Token Account Balance Check (Fastest & most direct)
    for coin_type, mint_address in token_contracts.items():
        if not mint_address:
            continue
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountsByOwner",
                "params": [
                    deposit_address,
                    {"mint": mint_address},
                    {"encoding": "jsonParsed"}
                ]
            }
            res = requests.post(rpc_url, json=payload, timeout=8).json()
            accounts = res.get("result", {}).get("value", [])
            total_balance = 0.0
            for acc in accounts:
                info = acc.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                token_amount = info.get("tokenAmount", {})
                ui_amount = token_amount.get("uiAmount")
                if ui_amount is None and token_amount.get("uiAmountString"):
                    try:
                        ui_amount = float(token_amount.get("uiAmountString"))
                    except ValueError:
                        ui_amount = 0.0
                if ui_amount:
                    total_balance += float(ui_amount)

            if total_balance >= required_amount:
                # Fetch recent signature for transaction reference
                sig_payload = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "getSignaturesForAddress",
                    "params": [deposit_address, {"limit": 5}]
                }
                sig_res = requests.post(rpc_url, json=sig_payload, timeout=8).json()
                sigs = sig_res.get("result", [])
                tx_hash = sigs[0].get("signature") if sigs else f"sol_{deposit_address}"
                return coin_type, tx_hash, total_balance

        except Exception as e:
            print(f"Solana getTokenAccountsByOwner error ({coin_type}): {e}")

    # 2. Detailed Transaction Scanning
    try:
        sig_payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "getSignaturesForAddress",
            "params": [deposit_address, {"limit": 10}]
        }
        sig_res = requests.post(rpc_url, json=sig_payload, timeout=8).json()
        signatures = sig_res.get("result", [])

        for sig_item in signatures:
            if sig_item.get("err") is not None:
                continue
            sig = sig_item.get("signature")
            if not sig:
                continue

            tx_payload = {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "getTransaction",
                "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
            }
            tx_res = requests.post(rpc_url, json=tx_payload, timeout=8).json()
            tx_result = tx_res.get("result")
            if not tx_result:
                continue

            meta = tx_result.get("meta", {})
            if meta.get("err") is not None:
                continue

            post_balances = meta.get("postTokenBalances", []) or []
            pre_balances = meta.get("preTokenBalances", []) or []

            for coin_type, mint_address in token_contracts.items():
                if not mint_address:
                    continue

                for post_b in post_balances:
                    if post_b.get("owner") == deposit_address and post_b.get("mint") == mint_address:
                        acc_idx = post_b.get("accountIndex")
                        post_ui = post_b.get("uiTokenAmount", {}).get("uiAmount")
                        if post_ui is None and post_b.get("uiTokenAmount", {}).get("uiAmountString"):
                            post_ui = float(post_b.get("uiTokenAmount", {}).get("uiAmountString"))
                        post_ui = float(post_ui or 0.0)

                        pre_b = next((b for b in pre_balances if b.get("accountIndex") == acc_idx), None)
                        pre_ui = 0.0
                        if pre_b:
                            pre_ui = pre_b.get("uiTokenAmount", {}).get("uiAmount")
                            if pre_ui is None and pre_b.get("uiTokenAmount", {}).get("uiAmountString"):
                                pre_ui = float(pre_b.get("uiTokenAmount", {}).get("uiAmountString"))
                            pre_ui = float(pre_ui or 0.0)

                        delta = post_ui - pre_ui
                        if delta >= required_amount:
                            return coin_type, sig, delta

    except Exception as e:
        print(f"Solana transaction scan error for address {deposit_address}: {e}")

    return None, None, 0

def check_payment_on_address(chain: str, rpc_url: str, deposit_address: str, required_price: float, token_contracts: dict):
    """
    Scans recent blocks / transactions for a sufficient token transfer to a given address.
    Supports EVM chains (ETH, POLYGON, BASE, ARBITRUM, BSC) and SOLANA.

    Args:
        chain (str): The name of the chain (e.g., 'ETH', 'BASE', 'SOLANA').
        rpc_url (str): The RPC URL for the chain.
        deposit_address (str): The unique address to check for payments.
        required_price (float): The target price of the product.
        token_contracts (dict): A dictionary of tokens to check, e.g., {'USDT': '...', 'USDC': '...'}.

    Returns:
        A tuple: (coin_type, transaction_hash, amount_in_token) if found, otherwise (None, None, 0).
    """
    if chain and chain.upper() == "SOLANA":
        return check_solana_payment(rpc_url, deposit_address, required_price, token_contracts)

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
            scan_blocks = 5000

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

            # Smart margin: Allows up to $0.50 tolerance (or 5% for smaller orders) to absorb CEX withdrawal fees
            margin = min(0.50, required_price * 0.05) if required_price > 5.0 else min(0.10, required_price * 0.10)
            required_amount = max(0.01, required_price - margin)
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

