from bip_utils import Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes

# --- Configuration ---
# Use account 0, the default for most wallets (e.g., MetaMask, Trust Wallet)
BIP44_ACCOUNT_INDEX = 0

def get_master_key_from_mnemonic(mnemonic: str):
    """
    Generates a BIP44 master key from a mnemonic phrase.
    """
    seed_bytes = Bip39SeedGenerator(mnemonic).Generate()
    return Bip44.FromSeed(seed_bytes, Bip44Coins.ETHEREUM)

def generate_new_address(mnemonic: str, address_index: int):
    """
    Generates a new Ethereum address at a specific index from a given mnemonic.
    
    The derivation path used is m/44'/60'/0'/0/address_index.
    """
    if not mnemonic:
        raise ValueError("A valid mnemonic must be provided.")

    # Create the master key from the mnemonic
    master_key = get_master_key_from_mnemonic(mnemonic)

    # Derive the child key for the specific account, change level, and address index
    child_key = master_key.Purpose().Coin().Account(BIP44_ACCOUNT_INDEX).Change(Bip44Changes.CHAIN_EXT).AddressIndex(address_index)

    # Return the public address as a string
    return child_key.PublicKey().ToAddress()
