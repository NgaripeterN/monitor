# Crypto Payment Verification Telegram Bot (HD Wallet Version)

This is a Telegram bot designed to verify USDT (Tether) payments across multiple blockchain networks. It uses a Hierarchical Deterministic (HD) wallet to generate a unique deposit address for each user, providing a smooth and secure payment experience.

## Features

*   **Unique Deposit Addresses:** Automatically generates a new, unique payment address for each user, eliminating confusion and enhancing security.
*   **Multi-chain Support:** Verifies USDT payments on Ethereum Mainnet, Polygon, Base, and Arbitrum.
*   **Automated Verification:** Users click an "I Have Paid" button to trigger an automatic scan of the blockchain for their payment.
*   **Secure:** Uses a single master recovery phrase (mnemonic) to control all generated addresses. Your main wallet's funds and addresses are kept separate by using a different account index in the derivation path.
*   **Persistent:** Uses a PostgreSQL database to track deposit addresses and payment statuses.

## New User Workflow

1.  User starts the bot and clicks "Get Deposit Address".
2.  User selects their preferred blockchain network (e.g., Polygon).
3.  The bot generates and displays a brand new address, unique to that user.
4.  The user sends the required USDT amount to that specific address.
5.  The user returns to the bot and clicks "I Have Paid".
6.  The bot scans the blockchain, finds the payment, and sends the user the private invite link.

## Setup Instructions

### 1. Prerequisites

*   Python 3.8+
*   A PostgreSQL database
*   A Telegram Bot Token (from BotFather)
*   The 12 or 24-word secret recovery phrase (mnemonic) from your own crypto wallet. **It is highly recommended to use a new, clean wallet for this bot.**
*   RPC URLs for Ethereum, Polygon, Base, and Arbitrum (e.g., from Infura, Alchemy).
*   An invite link to your private Telegram group/channel.

### 2. Install Dependencies

Install the required Python packages:
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a file named `.env` in the root directory of your project. Copy the contents of `.env.example` into it and fill in your actual credentials.

**New in this version:** You must provide your wallet's secret recovery phrase to the `HD_WALLET_MNEMONIC` variable.

```ini
# Your wallet's 12 or 24-word secret recovery phrase (mnemonic)
HD_WALLET_MNEMONIC="word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12"

# Telegram Bot Token, Database URL, RPC URLs, etc.
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
DATABASE_URL=postgresql://user:password@host:port/database
# ... (and all the other variables from .env.example)
```

**CRITICAL SECURITY NOTE:** The `HD_WALLET_MNEMONIC` is the master key to your funds. **Treat it like a password.** Do not share it, do not commit it to Git, and ensure your hosting environment (e.g., Render) is secure.

### 4. Initialize the Database

Run the `database.py` script to create the new `deposits` table:
```bash
python backend/database.py
```

### 5. Run the Bot

Start the Telegram bot:
```bash
python backend/bot.py
```

Your bot is now running with the new, more professional, unique deposit address system!

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
