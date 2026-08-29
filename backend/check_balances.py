import os
import sys
import getpass
from web3 import Web3
from eth_account import Account
from dotenv import load_dotenv

load_dotenv()

# Enable HD wallet derivation in eth_account
Account.enable_unaudited_hdwallet_features()

# RPC URLs per chain
RPC_URLS = {
    "ETH": os.getenv("ETH_RPC_URL", "https://ethereum-rpc.publicnode.com"),
    "POLYGON": os.getenv("POLYGON_RPC_URL", "https://polygon-bor-rpc.publicnode.com"),
    "BASE": os.getenv("BASE_RPC_URL", "https://base-rpc.publicnode.com"),
    "ARBITRUM": os.getenv("ARBITRUM_RPC_URL", "https://arbitrum-one-rpc.publicnode.com"),
    "BSC": os.getenv("BSC_RPC_URL", "https://bsc-rpc.publicnode.com")
}

# Token contract addresses per chain
TOKEN_CONTRACTS = {
    "USDT": {
        "ETH": "0xdac17f958d2ee523a2206206994597c13d831ec7",
        "POLYGON": "0xc2132d05d31c914a87c6611c10748aeb04b58e8f",
        "BASE": "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2",
        "ARBITRUM": "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9",
        "BSC": "0x55d398326f99059ff775485246999027b3197955"
    },
    "USDC": {
        "ETH": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "POLYGON": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
        "BASE": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "ARBITRUM": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "BSC": "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d"
    }
}

ERC20_ABI = '[{"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]'

def derive_addresses(mnemonic: str, count: int) -> list:
    """Pre-derives Ethereum addresses at m/44'/60'/0'/0/i for i from 0 to count-1."""
    addresses = []
    for i in range(count):
        path = f"m/44'/60'/0'/0/{i}"
        acc = Account.from_mnemonic(mnemonic, account_path=path)
        addresses.append((i, acc.address))
    return addresses

def init_web3_clients(chains: list) -> dict:
    """Initializes reusable Web3 connections with a 4-second timeout to prevent hanging."""
    clients = {}
    for chain in chains:
        url = RPC_URLS.get(chain)
        if not url:
            continue
        try:
            w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 4}))
            if w3.is_connected():
                clients[chain] = w3
            else:
                print(f"⚠️ Warning: Could not connect to {chain} RPC ({url}). Skipping {chain}.")
        except Exception as e:
            print(f"⚠️ Error initializing {chain} RPC ({url}): {e}")
    return clients

def main():
    print("====================================================")
    print(" 🔐 SEED PHRASE HD WALLET BALANCE SCANNER ")
    print("====================================================\n")

    mnemonic = getpass.getpass("Enter your 12 or 24-word seed phrase (hidden as you type): ").strip()
    if not mnemonic:
        mnemonic = input("Or paste your seed phrase visibly here: ").strip()

    if not mnemonic:
        print("❌ Seed phrase cannot be empty.")
        return

    count_str = input("\nHow many derived addresses to scan? (default 20): ").strip()
    scan_count = int(count_str) if count_str.isdigit() else 20

    print("\nSelect Chain to scan:")
    print("1. ETH (Ethereum Mainnet)")
    print("2. POLYGON")
    print("3. BASE")
    print("4. ARBITRUM")
    print("5. BSC")
    print("6. ALL Chains")
    chain_choice = input("Enter choice (1-6, default 1): ").strip()

    chain_map = {
        "1": ["ETH"],
        "2": ["POLYGON"],
        "3": ["BASE"],
        "4": ["ARBITRUM"],
        "5": ["BSC"],
        "6": ["ETH", "POLYGON", "BASE", "ARBITRUM", "BSC"]
    }
    chains_to_scan = chain_map.get(chain_choice, ["ETH"])

    print("\n⚡ Connecting to RPC nodes...")
    w3_clients = init_web3_clients(chains_to_scan)
    if not w3_clients:
        print("❌ Could not connect to any RPC nodes. Please check your internet connection or .env RPC URLs.")
        return

    print("⚡ Deriving HD addresses...")
    try:
        derived = derive_addresses(mnemonic, scan_count)
    except Exception as err:
        print(f"❌ Error deriving addresses: {err}")
        return

    print(f"\n🔍 Scanning {len(derived)} addresses across {', '.join(w3_clients.keys())}...\n")

    found_count = 0

    for idx, addr in derived:
        print(f"[{idx+1}/{scan_count}] Checking Index #{idx}: {addr}...", end="", flush=True)
        checksum_addr = Web3.to_checksum_address(addr)
        addr_has_funds = False
        summary_lines = []

        for chain, w3 in w3_clients.items():
            try:
                # Check Native Coin Balance
                raw_native = w3.eth.get_balance(checksum_addr)
                native_bal = raw_native / 10**18
                if native_bal > 0:
                    addr_has_funds = True
                    summary_lines.append(f"      - {chain} Native Coin: {native_bal:.6f}")

                # Check Tokens (USDT / USDC)
                for token_symbol, contracts in TOKEN_CONTRACTS.items():
                    token_addr = contracts.get(chain)
                    if not token_addr:
                        continue
                    contract = w3.eth.contract(address=Web3.to_checksum_address(token_addr), abi=ERC20_ABI)
                    raw_bal = contract.functions.balanceOf(checksum_addr).call()
                    decimals = 6 if (token_symbol in ["USDT", "USDC"] and chain in ["ETH", "POLYGON", "BASE", "ARBITRUM"]) else 18
                    bal = raw_bal / (10 ** decimals)
                    if bal > 0:
                        addr_has_funds = True
                        summary_lines.append(f"      - {chain} {token_symbol}: {bal:.2f} {token_symbol}")
            except Exception:
                pass  # Skip RPC timeouts/errors silently for speed

        if addr_has_funds:
            found_count += 1
            print(" 💰 [FUNDS FOUND!]")
            for line in summary_lines:
                print(line)
        else:
            print(" (0 balance)")

    print("\n====================================================")
    if found_count == 0:
        print("✅ Scan complete. No non-zero balances found across derived addresses.")
    else:
        print(f"🎉 Scan complete! Found non-zero balances in {found_count} address(es).")
    print("====================================================")

if __name__ == "__main__":
    main()
