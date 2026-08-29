from bip_utils import Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes

# --- Configuration ---
# Use account 0, the default for most wallets (e.g., MetaMask, Trust Wallet)
BIP44_ACCOUNT_INDEX = 0

def get_master_key_from_mnemonic(mnemonic: str, coin: Bip44Coins = Bip44Coins.ETHEREUM):
    """
    Generates a BIP44 master key from a mnemonic phrase for a specified coin.
    """
    seed_bytes = Bip39SeedGenerator(mnemonic).Generate()
    return Bip44.FromSeed(seed_bytes, coin)

def generate_new_address(mnemonic: str, address_index: int, chain: str = "ETH"):
    """
    Generates a new address at a specific index from a given mnemonic.
    
    - For Solana: Derivation path m/44'/501'/0'/0/address_index (Base58 public key)
    - For EVM (ETH, Polygon, Base, Arbitrum, BSC): Derivation path m/44'/60'/0'/0/address_index (0x... hex address)
    """
    if not mnemonic:
        raise ValueError("A valid mnemonic must be provided.")

    coin_type = Bip44Coins.SOLANA if (chain and chain.upper() == "SOLANA") else Bip44Coins.ETHEREUM

    # Create the master key from the mnemonic for the specific coin
    master_key = get_master_key_from_mnemonic(mnemonic, coin_type)

    # Derive the child key for the specific account, change level, and address index
    child_key = master_key.Purpose().Coin().Account(BIP44_ACCOUNT_INDEX).Change(Bip44Changes.CHAIN_EXT).AddressIndex(address_index)

    # Return the public address as a string
    return child_key.PublicKey().ToAddress()

