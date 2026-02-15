import os
from dotenv import load_dotenv
from bip_utils import Bip39MnemonicGenerator, Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes

# Load environment variables from .env file
load_dotenv()

# Get the mnemonic from environment variables
HD_WALLET_MNEMONIC = os.getenv("HD_WALLET_MNEMONIC")

# --- Configuration ---
# Use account 0, the default for most wallets (e.g., MetaMask, Trust Wallet)
BIP44_ACCOUNT_INDEX = 0

def get_master_key_from_mnemonic(mnemonic):
    """
    Generates a BIP44 master key from a mnemonic phrase.
    """
    seed_bytes = Bip39SeedGenerator(mnemonic).Generate()
    return Bip44.FromSeed(seed_bytes, Bip44Coins.ETHEREUM)

def generate_new_address(address_index):
    """
    Generates a new Ethereum address at a specific index from the master key.
    
    The derivation path used is m/44'/60'/0'/0/address_index, where:
    - 44' is for BIP44
    - 60' is for Ethereum
    - 0' is the default account index
    - 0 is the change level (external chain)
    - address_index is the sequential index for the address
    """
    if not HD_WALLET_MNEMONIC:
        raise ValueError("HD_WALLET_MNEMONIC is not set in the environment variables.")

    # Create the master key from the mnemonic
    master_key = get_master_key_from_mnemonic(HD_WALLET_MNEMONIC)

    # Derive the child key for the specific account, change level, and address index
    child_key = master_key.Purpose().Coin().Account(BIP44_ACCOUNT_INDEX).Change(Bip44Changes.CHAIN_EXT).AddressIndex(address_index)

    # Return the public address as a string
    return child_key.PublicKey().ToAddress()

if __name__ == '__main__':
    # Example of generating the first 5 addresses
    print(f"Using mnemonic: '{HD_WALLET_MNEMONIC[:20]}...'")
    print("-" * 30)
    for i in range(5):
        address = generate_new_address(i)
        print(f"Address at index {i}: {address}")
