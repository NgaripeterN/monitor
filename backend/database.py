import psycopg2
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    """Establishes a connection to the database."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def create_deposits_table():
    """
    Creates the deposits table if it does not exist.
    This table will store information about user deposits.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            chain VARCHAR(20) NOT NULL,
            address VARCHAR(255) UNIQUE NOT NULL,
            address_index INT NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            coin_type VARCHAR(10),
            tx_hash VARCHAR(255),
            amount_received NUMERIC(36, 18),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            paid_at TIMESTAMP WITH TIME ZONE,
            UNIQUE(user_id, chain, status)
        );
    """)
    # Add an index on status for faster queries of pending deposits
    cur.execute("CREATE INDEX IF NOT EXISTS idx_deposits_status ON deposits (status);")
    conn.commit()
    cur.close()
    conn.close()

def get_next_address_index():
    """Gets the next available index for address derivation."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT MAX(address_index) FROM deposits;")
    max_index = cur.fetchone()[0]
    cur.close()
    conn.close()
    return (max_index + 1) if max_index is not None else 0

def create_deposit_address(user_id, chain, address, address_index):
    """
    Creates a new deposit address record for a user.
    If a user already has a pending address for the same chain, it returns that one.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # First, check if a pending address already exists for this user and chain
        cur.execute(
            "SELECT address FROM deposits WHERE user_id = %s AND chain = %s AND status = 'pending'",
            (user_id, chain)
        )
        existing_address = cur.fetchone()
        if existing_address:
            return existing_address[0], False # Return existing address, indicate not new

        # If not, create a new one
        cur.execute(
            "INSERT INTO deposits (user_id, chain, address, address_index) VALUES (%s, %s, %s, %s) RETURNING address;",
            (user_id, chain, address, address_index)
        )
        new_address = cur.fetchone()[0]
        conn.commit()
        return new_address, True # Return new address, indicate it's new
    except psycopg2.IntegrityError as e:
        conn.rollback()
        # This handles the case where a user might have a non-pending record and tries to create a new one.
        # It's better to fetch the existing pending one as done above.
        # For simplicity, we just return None and let the bot handle it.
        print(f"Database integrity error: {e}")
        return None, False
    finally:
        cur.close()
        conn.close()

def get_pending_deposit_for_user(user_id, chain):
    """Retrieves a user's pending deposit for a specific chain."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, user_id, chain, address, address_index FROM deposits WHERE user_id = %s AND chain = %s AND status = 'pending'",
        (user_id, chain)
    )
    deposit = cur.fetchone()
    cur.close()
    conn.close()
    return deposit

def get_pending_deposits():
    """Retrieves all deposits with 'pending' status."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, chain, address, address_index FROM deposits WHERE status = 'pending';")
    pending_deposits = cur.fetchall()
    cur.close()
    conn.close()
    return pending_deposits

def confirm_payment(deposit_id, tx_hash, amount_received, coin_type):
    """Updates a deposit's status to 'paid' and records transaction details."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE deposits SET status = 'paid', tx_hash = %s, amount_received = %s, coin_type = %s, paid_at = CURRENT_TIMESTAMP WHERE id = %s",
        (tx_hash, amount_received, coin_type, deposit_id)
    )
    conn.commit()
    cur.close()
    conn.close()

def has_user_paid(user_id):
    """Checks if a user has any 'paid' deposit."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT EXISTS(SELECT 1 FROM deposits WHERE user_id = %s AND status = 'paid')", (user_id,))
    exists = cur.fetchone()[0]
    cur.close()
    conn.close()
    return exists

if __name__ == '__main__':
    print("Creating or updating the 'deposits' table...")
    create_deposits_table()
    print("Table 'deposits' is ready.")
