# Crypto Payment Verification Telegram Bot (HD Wallet Version)

This is a Telegram bot designed to verify USDT and USDC payments across multiple blockchain networks. It uses a Hierarchical Deterministic (HD) wallet to generate a unique deposit address for each user, providing a smooth and secure payment experience.

## Features

*   **Multi-Coin Support:** Verifies both USDT and USDC payments.
*   **Multi-chain Support:** Works on Ethereum Mainnet, Polygon, Base, Arbitrum, and BSC.
*   **Unique Deposit Addresses:** Automatically generates a new, unique payment address for each user.
*   **Automated Verification:** Users click an "I Have Paid" button to trigger an automatic scan of the blockchain for their payment.
*   **Secure:** Uses a single master recovery phrase (mnemonic) to control all generated addresses. Your main wallet's funds and addresses are kept separate by using a different account index.
*   **Persistent:** Uses a PostgreSQL database to track deposit addresses and payment statuses.
*   **Always-On (Free Tier):** Includes a lightweight web server to work with external uptime monitors, keeping the bot alive on free hosting plans.

## New User Workflow

1.  User starts the bot and clicks "Get Deposit Address".
2.  User selects their preferred blockchain network (e.g., Polygon).
3.  The bot generates and displays a brand new address, unique to that user.
4.  The user sends the required USDT or USDC amount to that specific address.
5.  The user returns to the bot and clicks "I Have Paid".
6.  The bot scans the blockchain, finds the payment, and sends the user the private invite link.

## Setup Instructions

### 1. Prerequisites

*   Python 3.8+
*   A PostgreSQL database
*   A Telegram Bot Token (from BotFather)
*   The 12 or 24-word secret recovery phrase (mnemonic) from your own crypto wallet. **It is highly recommended to use a new, clean wallet for this bot.**
*   RPC URLs for Ethereum, Polygon, Base, Arbitrum, and BSC.
*   An invite link to your private Telegram group/channel.

### 2. Install Dependencies

Install the required Python packages:
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a file named `.env` in the root directory of your project. Copy the contents of `.env.example` into it and fill in your actual credentials.

You must provide your wallet's secret recovery phrase to the `HD_WALLET_MNEMONIC` variable and ensure all RPC and contract address variables are set.

```ini
# Your wallet's 12 or 24-word secret recovery phrase (mnemonic)
HD_WALLET_MNEMONIC="word1 word2 word3 word4 word5 word6 word7 word8 word9 word10 word11 word12"

# Telegram Bot Token, Database URL, RPC URLs, etc.
TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
DATABASE_URL=postgresql://user:password@host:port/database

# ... (and all the other variables from .env.example, including USDT and USDC addresses)
```

**CRITICAL SECURITY NOTE:** The `HD_WALLET_MNEMONIC` is the master key to your funds. **Treat it like a password.** Do not share it, do not commit it to Git, and ensure your hosting environment (e.g., Render) is secure.

### 4. Initialize the Database

Run the `database.py` script to create/update the `deposits` table:
```bash
python backend/database.py
```
*(Note: If you are updating from a previous version, you may need to manually add the `coin_type` column to your existing table or drop the table and re-run this script.)*

### 5. Run the Bot

Start the Telegram bot:
```bash
python backend/bot.py
```

Your bot is now running with support for both USDT and USDC!

## Deployment on Render (Free Tier Workaround)

Render's free "Web Service" tier automatically puts your service to sleep if it doesn't receive any web traffic. To prevent this and keep the bot running 24/7, we have included a tiny web server in the bot. You must use a free "uptime monitor" service to ping your bot every 5-15 minutes.

Here’s how to set it up:

1.  **Deploy your bot** on Render as a **Web Service**. You will get a URL for your service (e.g., `https://your-bot-name.onrender.com`).
2.  **Sign up for a free uptime monitor service** like [UptimeRobot](https://uptimerobot.com/).
3.  **Create a new monitor** in UptimeRobot:
    *   **Monitor Type:** `HTTP(S)`
    *   **Friendly Name:** Give it any name (e.g., "My Telegram Bot Ping").
    *   **URL (or IP):** Paste your Render service URL from Step 1.
    *   **Monitoring Interval:** Set it to `5 minutes`.
4.  **Save the monitor.** That's it! The service will now ping your bot regularly, keeping it awake and running continuously.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
