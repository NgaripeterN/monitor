import os
import psycopg2
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# --- Initial Setup ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
ENCRYPTION_KEY = os.getenv("DATA_ENCRYPTION_KEY")
if not ENCRYPTION_KEY:
    raise ValueError("DATA_ENCRYPTION_KEY is not set.")
fernet = Fernet(ENCRYPTION_KEY.encode())

# --- Helper Functions ---
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def encrypt_data(data: str) -> bytes:
    return fernet.encrypt(data.encode())

def decrypt_data(encrypted_data: bytes) -> str:
    # Ensure the input is bytes
    if isinstance(encrypted_data, str):
        if encrypted_data.startswith('\\x'):
            encrypted_data = bytes.fromhex(encrypted_data[2:])
        else:
            # Assuming it's a base64 encoded string if not hex
            encrypted_data = encrypted_data.encode()
            
    return fernet.decrypt(encrypted_data).decode()

# --- Table Creation & Migrations ---
def create_all_tables():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Core tables
    cur.execute("CREATE TABLE IF NOT EXISTS sellers (id SERIAL PRIMARY KEY, telegram_user_id BIGINT UNIQUE NOT NULL, name VARCHAR(255) NOT NULL, created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP);")
    cur.execute("CREATE TABLE IF NOT EXISTS wallets (id SERIAL PRIMARY KEY, seller_id INT UNIQUE NOT NULL REFERENCES sellers(id) ON DELETE CASCADE, encrypted_mnemonic BYTEA NOT NULL, created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP);")
    cur.execute("CREATE TABLE IF NOT EXISTS products (id SERIAL PRIMARY KEY, seller_id INT NOT NULL REFERENCES sellers(id) ON DELETE CASCADE, name VARCHAR(255) NOT NULL, price NUMERIC(10, 2) NOT NULL, currency VARCHAR(10) NOT NULL DEFAULT 'USDT', is_active BOOLEAN DEFAULT TRUE, created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP);")
    cur.execute("CREATE TABLE IF NOT EXISTS product_links (id SERIAL PRIMARY KEY, product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE, invite_link TEXT NOT NULL);")
    
    # Deposits table - ensure it exists with core columns
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            id SERIAL PRIMARY KEY, 
            telegram_user_id BIGINT, 
            address VARCHAR(255) UNIQUE NOT NULL, 
            address_index INT NOT NULL, 
            status VARCHAR(20) NOT NULL DEFAULT 'pending', 
            coin_type VARCHAR(10), 
            tx_hash VARCHAR(255), 
            amount_received NUMERIC(36, 18), 
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
            paid_at TIMESTAMP WITH TIME ZONE
        );
    """)
    
    # List of columns to ensure exist in 'deposits'
    columns_to_check = [
        ("product_id", "INT REFERENCES products(id)"),
        ("wallet_id", "INT REFERENCES wallets(id)"),
        ("seller_id", "INT REFERENCES sellers(id)"),
        ("chain", "VARCHAR(50)"),
        ("user_id", "BIGINT"),
        ("telegram_user_id", "BIGINT")
    ]

    for col_name, col_def in columns_to_check:
        cur.execute("""
            SELECT 1 FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'deposits' 
            AND column_name = %s;
        """, (col_name,))

        if not cur.fetchone():
            print(f"Migration: Adding missing column {col_name} to deposits table...")
            cur.execute(f"ALTER TABLE deposits ADD COLUMN {col_name} {col_def};")

    # Fix the unique constraint to include product_id
    # First, try to drop the old one if it exists
    cur.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'deposits_user_id_chain_status_key') THEN
                ALTER TABLE deposits DROP CONSTRAINT deposits_user_id_chain_status_key;
            END IF;
            
            # Also drop variants if they exist
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'deposits_telegram_user_id_chain_status_key') THEN
                ALTER TABLE deposits DROP CONSTRAINT deposits_telegram_user_id_chain_status_key;
            END IF;
        END $$;
    """)
    
    # Add the new, more flexible unique constraint
    # This allows a user to have one pending deposit per product per chain
    cur.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'deposits_user_product_chain_pending_key') THEN
                ALTER TABLE deposits ADD CONSTRAINT deposits_user_product_chain_pending_key 
                UNIQUE (telegram_user_id, product_id, chain, status);
            END IF;
        END $$;
    """)

    conn.commit()
    cur.close()
    conn.close()

# --- Seller & Wallet Functions ---
def add_seller(name, telegram_user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO sellers (name, telegram_user_id) VALUES (%s, %s) RETURNING id;", (name, int(telegram_user_id)))
        conn.commit()
        return True, "✅ Seller account created successfully."
    except psycopg2.IntegrityError:
        conn.rollback()
        return False, "❌ This Telegram User ID is already registered."
    finally:
        cur.close()
        conn.close()

def update_seller_name(seller_id, new_name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE sellers SET name = %s WHERE id = %s;", (new_name, seller_id))
    updated_rows = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return updated_rows > 0

def get_seller_by_telegram_id(telegram_user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM sellers WHERE telegram_user_id = %s", (telegram_user_id,))
    seller = cur.fetchone()
    cur.close()
    conn.close()
    return seller

def set_seller_wallet(seller_id, mnemonic):
    encrypted_mnemonic = encrypt_data(mnemonic)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO wallets (seller_id, encrypted_mnemonic) VALUES (%s, %s) ON CONFLICT (seller_id) DO UPDATE SET encrypted_mnemonic = EXCLUDED.encrypted_mnemonic;", (seller_id, encrypted_mnemonic))
    conn.commit()
    cur.close()
    conn.close()

def get_wallet_by_seller_id(seller_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, encrypted_mnemonic FROM wallets WHERE seller_id = %s", (seller_id,))
    wallet = cur.fetchone()
    cur.close()
    conn.close()
    if wallet:
        wallet_id, encrypted_mnemonic = wallet
        if encrypted_mnemonic:
            if isinstance(encrypted_mnemonic, str) and encrypted_mnemonic.startswith('\\x'):
                data_to_decrypt = bytes.fromhex(encrypted_mnemonic[2:])
            elif isinstance(encrypted_mnemonic, memoryview):
                data_to_decrypt = encrypted_mnemonic.tobytes()
            else:
                data_to_decrypt = encrypted_mnemonic

            return {"id": wallet_id, "mnemonic": decrypt_data(data_to_decrypt)}
    return None

# --- Product & Link Functions ---
def add_product(seller_id, name, price):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO products (seller_id, name, price) VALUES (%s, %s, %s) RETURNING id;", (seller_id, name, float(price)))
    product_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return product_id

def add_link_to_product(product_id, seller_id, invite_link):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM products WHERE id = %s AND seller_id = %s;", (product_id, seller_id))
    if cur.fetchone() is None: return False
    cur.execute("INSERT INTO product_links (product_id, invite_link) VALUES (%s, %s);", (product_id, invite_link))
    conn.commit()
    cur.close()
    conn.close()
    return True

def get_seller_products_with_links(seller_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, price FROM products WHERE seller_id = %s AND is_active = TRUE ORDER BY created_at DESC", (seller_id,))
    products = cur.fetchall()
    
    product_details = []
    for prod in products:
        product_id, name, price = prod
        cur.execute("SELECT id, invite_link FROM product_links WHERE product_id = %s;", (product_id,))
        links = cur.fetchall()
        product_details.append({"id": product_id, "name": name, "price": price, "links": links})
        
    cur.close()
    conn.close()
    return product_details

def get_product_by_id(product_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, seller_id, name, price, currency, is_active FROM products WHERE id = %s", (product_id,))
    product = cur.fetchone()
    cur.close()
    conn.close()
    return product

def get_product_links(product_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT invite_link FROM product_links WHERE product_id = %s;", (product_id,))
    links = [row[0] for row in cur.fetchall()]
    cur.close()
    conn.close()
    return links
    
def update_product_price(product_id, seller_id, new_price):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE products SET price = %s WHERE id = %s AND seller_id = %s;", (float(new_price), product_id, seller_id))
    updated_rows = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return updated_rows > 0

def delete_product_link(link_id, seller_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM product_links pl
        WHERE pl.id = %s AND EXISTS (
            SELECT 1 FROM products p 
            WHERE p.id = pl.product_id AND p.seller_id = %s
        );
    """, (link_id, seller_id))
    deleted_rows = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return deleted_rows > 0
    
# --- Deposit Functions ---
def get_next_address_index(wallet_id: int) -> int:
    conn = get_db_connection()
    cur = conn.cursor()
    # We use a broad check to find the max index ever used for this wallet
    cur.execute("SELECT MAX(address_index) FROM deposits WHERE wallet_id = %s;", (wallet_id,))
    max_index = cur.fetchone()[0]
    cur.close()
    conn.close()
    return (max_index + 1) if max_index is not None else 0

def create_deposit_address(product_id: int, wallet_id: int, telegram_user_id: int, address: str, address_index: int, seller_id: int, chain: str) -> int:
    conn = get_db_connection()
    cur = conn.cursor()
    # We populate both 'telegram_user_id' and the redundant 'user_id' to satisfy all schema variants
    cur.execute(
        """INSERT INTO deposits (product_id, wallet_id, telegram_user_id, user_id, address, address_index, seller_id, chain) 
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;""",
        (product_id, wallet_id, telegram_user_id, telegram_user_id, address, address_index, seller_id, chain)
    )
    deposit_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return deposit_id

def get_pending_deposit_for_user(telegram_user_id: int, product_id: int, chain: str):
    conn = get_db_connection()
    cur = conn.cursor()
    # Check both potential ID columns and ensure the chain matches
    cur.execute("""
        SELECT id, address FROM deposits 
        WHERE (telegram_user_id = %s OR user_id = %s) 
        AND product_id = %s 
        AND chain = %s
        AND status = 'pending';
    """, (telegram_user_id, telegram_user_id, product_id, chain))
    deposit = cur.fetchone()
    cur.close()
    conn.close()
    return deposit

def get_deposit_by_id(deposit_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    # Explicitly name columns to avoid order issues
    cur.execute("SELECT product_id, seller_id, wallet_id, address FROM deposits WHERE id = %s;", (deposit_id,))
    deposit = cur.fetchone()
    cur.close()
    conn.close()
    return deposit

def confirm_payment(deposit_id: int, tx_hash: str, amount_received: float, coin_type: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE deposits SET status = 'paid', tx_hash = %s, amount_received = %s, coin_type = %s, paid_at = CURRENT_TIMESTAMP WHERE id = %s;", (tx_hash, amount_received, coin_type, deposit_id))
    conn.commit()
    cur.close()
    conn.close()

if __name__ == '__main__':
    print("Running create_all_tables() to set up the database schema.")
    create_all_tables()
    print("Tables created successfully.")
