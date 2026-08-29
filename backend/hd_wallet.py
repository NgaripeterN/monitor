from bip_utils import (
    Bip39SeedGenerator,
    Bip44,
    Bip44Coins,
    Bip44Changes,
    Bip32Slip10Ed25519,
    SolAddr,
    Base58Encoder
)

# --- Configuration ---
# Use account 0, the default for most wallets (e.g., MetaMask, Trust Wallet)
BIP44_ACCOUNT_INDEX = 0

def get_master_key_from_mnemonic(mnemonic: str, coin: Bip44Coins = Bip44Coins.ETHEREUM):
    """
    Generates a BIP44 master key from a mnemonic phrase for a specified coin.
    """
    seed_bytes = Bip39SeedGenerator(mnemonic).Generate()
    return Bip44.FromSeed(seed_bytes, coin)

def generate_solana_address(mnemonic: str, address_index: int):
    """
    Derives a Solana address matching the standard Phantom / Solflare derivation path:
    m/44'/501'/address_index'/0'
    """
    if not mnemonic:
        raise ValueError("A valid mnemonic must be provided.")
    seed_bytes = Bip39SeedGenerator(mnemonic).Generate()
    bip32_ctx = Bip32Slip10Ed25519.FromSeed(seed_bytes)
    derived = bip32_ctx.DerivePath(f"m/44'/501'/{address_index}'/0'")
    return SolAddr.EncodeKey(derived.PublicKey().KeyObject())

def generate_solana_keypair(mnemonic: str, address_index: int):
    """
    Derives the public address and exportable Base58 private key (Phantom format)
    for a given address index.
    """
    if not mnemonic:
        raise ValueError("A valid mnemonic must be provided.")
    seed_bytes = Bip39SeedGenerator(mnemonic).Generate()
    bip32_ctx = Bip32Slip10Ed25519.FromSeed(seed_bytes)
    derived = bip32_ctx.DerivePath(f"m/44'/501'/{address_index}'/0'")
    pub_addr = SolAddr.EncodeKey(derived.PublicKey().KeyObject())
    priv_raw = derived.PrivateKey().Raw().ToBytes()
    pub_raw = derived.PublicKey().RawCompressed().ToBytes()[1:]
    priv_b58 = Base58Encoder.Encode(priv_raw + pub_raw)
    return pub_addr, priv_b58

def generate_new_address(mnemonic: str, address_index: int, chain: str = "ETH"):
    """
    Generates a new address at a specific index from a given mnemonic.
    
    - For Solana: Derivation path m/44'/501'/address_index'/0' (Base58 public key, matches Phantom/Solflare)
    - For EVM (ETH, Polygon, Base, Arbitrum, BSC): Derivation path m/44'/60'/0'/0/address_index (0x... hex address)
    """
    if not mnemonic:
        raise ValueError("A valid mnemonic must be provided.")

    if chain and chain.upper() == "SOLANA":
        return generate_solana_address(mnemonic, address_index)

    # EVM derivation
    master_key = get_master_key_from_mnemonic(mnemonic, Bip44Coins.ETHEREUM)
    child_key = master_key.Purpose().Coin().Account(BIP44_ACCOUNT_INDEX).Change(Bip44Changes.CHAIN_EXT).AddressIndex(address_index)
    return child_key.PublicKey().ToAddress()


