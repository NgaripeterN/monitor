import os
import sys
from dotenv import load_dotenv

# Load .env first
load_dotenv()

# Provide a fallback encryption key if not present so database.py import won't crash
if not os.getenv("DATA_ENCRYPTION_KEY"):
    from cryptography.fernet import Fernet
    os.environ["DATA_ENCRYPTION_KEY"] = Fernet.generate_key().decode()

# Ensure backend module can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database import get_db_connection, confirm_payment
from backend.blockchain import check_payment_on_address

# Reliable RPC URLs per chain (reads environment variables first, falls back to stable RPC endpoints)
RPC_URLS = {
    "ETH": os.getenv("ETH_RPC_URL", "https://rpc.ankr.com/eth"),
    "POLYGON": os.getenv("POLYGON_RPC_URL", "https://rpc.ankr.com/polygon"),
    "BASE": os.getenv("BASE_RPC_URL", "https://mainnet.base.org"),
    "ARBITRUM": os.getenv("ARBITRUM_RPC_URL", "https://rpc.ankr.com/arbitrum"),
    "BSC": os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org"),
    "SOLANA": os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
}

# Token contract addresses per chain
TOKEN_CONTRACTS = {
    "USDT": {
        "ETH": "0xdac17f958d2ee523a2206206994597c13d831ec7",
        "POLYGON": "0xc2132d05d31c914a87c6611c10748aeb04b58e8f",
        "BASE": "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2",
        "ARBITRUM": "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9",
        "BSC": "0x55d398326f99059ff775485246999027b3197955",
        "SOLANA": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
    },
    "USDC": {
        "ETH": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "POLYGON": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
        "BASE": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "ARBITRUM": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "BSC": "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",
        "SOLANA": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    }
}

def scan_and_confirm_database_deposits():
    print("====================================================")
    print(" 🗄️ DATABASE PENDING DEPOSITS SCANNER & VERIFIER ")
    print("====================================================\n")

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL is not set in your environment or .env file.")
        print("   Please pass DATABASE_URL='postgresql://...' before python3.")
        return

    # 1. Connect to Database (Neon / PostgreSQL)
    try:
        conn = get_db_connection()
        cur = conn.cursor()
    except Exception as err:
        print(f"❌ Failed to connect to Database: {err}")
        return

    # 2. Fetch all 'pending' deposits
    query = """
        SELECT d.id, d.telegram_user_id, d.address, d.chain, p.price, p.name
        FROM deposits d
        JOIN products p ON d.product_id = p.id
        WHERE d.status = 'pending';
    """
    try:
        cur.execute(query)
        pending_deposits = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as err:
        print(f"❌ Database query error: {err}")
        return

    if not pending_deposits:
        print("✅ No pending deposits found in database. All deposits are up to date!")
        return

    print(f"🔍 Found {len(pending_deposits)} pending deposit(s) in database.\n")

    confirmed_count = 0

    for dep_id, user_id, deposit_address, chain, price, product_name in pending_deposits:
        chain_name = chain.upper() if chain else "ETH"
        rpc_url = RPC_URLS.get(chain_name)

        if not rpc_url:
            print(f"⚠️  RPC URL for {chain_name} not configured. Skipping Deposit #{dep_id}.")
            continue

        tokens_to_check = {
            token: contracts.get(chain_name)
            for token, contracts in TOKEN_CONTRACTS.items()
            if contracts.get(chain_name)
        }

        print(f"Checking Deposit #{dep_id} | User {user_id} | Product: '{product_name}' (${price})")
        print(f"   Chain: {chain_name} | Address: {deposit_address}")

        coin_type, tx_hash, amount_paid = check_payment_on_address(
            chain=chain_name,
            rpc_url=rpc_url,
            deposit_address=deposit_address,
            required_price=float(price),
            token_contracts=tokens_to_check
        )

        if tx_hash:
            print(f"   ✅ PAYMENT CONFIRMED ON-CHAIN!")
            print(f"      Amount: {amount_paid:.2f} {coin_type}")
            print(f"      Tx Hash: {tx_hash}")
            
            # Confirm and update database
            confirm_payment(dep_id, tx_hash, amount_paid, coin_type)
            print(f"      🎉 Database row for Deposit #{dep_id} updated from 'pending' -> 'paid'!")
            confirmed_count += 1
        else:
            print(f"   ⏳ Payment not detected on-chain yet.")

        print("-" * 60)

    print("\n====================================================")
    print(f"✨ Scan complete! {confirmed_count} deposit(s) were verified and updated in the database.")
    print("====================================================")

if __name__ == "__main__":
    scan_and_confirm_database_deposits()
