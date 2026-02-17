# Crypto Payment Verification Telegram Bot (HD Wallet Version)

This is a Telegram bot designed to verify USDT and USDC payments across multiple blockchain networks. It uses a Hierarchical Deterministic (HD) wallet to generate a unique deposit address for each user, providing a smooth and secure payment experience.

## Features

*   **Webhook Driven:** Uses webhooks for instant and reliable message processing. This is the professional standard and avoids the `Conflict` errors common with polling.
*   **Multi-Coin Support:** Verifies both USDT and USDC payments.
*   **Multi-chain Support:** Works on Ethereum Mainnet, Polygon, Base, Arbitrum, and BSC.
*   **Unique Deposit Addresses:** Automatically generates a new, unique payment address for each user.
*   **Automated Verification:** Users click an "I Have Paid" button to trigger an automatic scan of the blockchain for their payment.
*   **Secure:** Uses a single master recovery phrase (mnemonic) to control all generated addresses.
*   **Persistent:** Uses a PostgreSQL database to track deposit addresses and payment statuses.

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
*   The 12 or 24-word secret recovery phrase (mnemonic) from your own crypto wallet.
*   RPC URLs for all desired chains.
*   An invite link to your private Telegram group/channel.

### 2. Install Dependencies

Install the required Python packages:
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a file named `.env` in the root directory of your project. Copy the contents of `.env.example` into it and fill in your actual credentials.

### 4. Initialize the Database

Run the `database.py` script to create/update the `deposits` table:
```bash
python -c "from backend.database import create_deposits_table; create_deposits_table()"
```

### 5. Running Locally (for Development)

To run the bot locally for testing, you will need a tool like `ngrok` to expose your local server to the internet so Telegram can send webhooks to it. The production deployment on Render is easier.

## Deployment on Render

This bot is designed to be deployed as a **Web Service** on Render.

1.  **Create the Service:**
    *   On your Render Dashboard, click **New > Web Service** and connect your GitHub repository.
    *   **Region:** Choose a region (e.g., `Virginia (US East)`).
    *   **Branch:** `main`
    *   **Build Command:** 
        ```
        pip install -r requirements.txt && python -c "from backend.database import create_deposits_table; create_deposits_table()"
        ```
    *   **Start Command:** 
        ```
        gunicorn backend.bot:app
        ```
    *   **Instance Type:** `Free` is sufficient to start.

2.  **Add Environment Variables:**
    *   Go to the **Environment** tab for your new service.
    *   Add all the required variables from your `.env.example` file (e.g., `TELEGRAM_BOT_TOKEN`, `HD_WALLET_MNEMONIC`, `DATABASE_URL`, all RPC and token contract addresses).
    *   **Add a new, crucial variable:**
        *   **Name:** `WEBHOOK_URL`
        *   **Value:** Your service's public URL provided by Render (e.g., `https://your-bot-name.onrender.com`).

3.  **Deploy:**
    *   Click **"Create Web Service"**. Wait for the service to build and deploy.

4.  **Set the Webhook (One-Time Setup):**
    *   After your service is live, take your service URL (e.g., `https://your-bot-name.onrender.com`) and visit the `/set_webhook` endpoint in your browser.
    *   Go to this URL: **`https://your-bot-name.onrender.com/set_webhook`**
    *   You should see a "Webhook set successfully!" message.

Your bot is now fully deployed, stable, and will no longer produce `Conflict` errors.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
