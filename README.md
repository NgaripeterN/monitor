# Crypto Payment Verification Telegram Bot

This bot verifies USDT/USDC payments on multiple chains using a webhook-driven architecture with FastAPI and HD wallets.

## Features

*   **Webhook Driven:** Uses FastAPI and webhooks for instant, reliable, and production-ready message processing.
*   **Multi-Coin Support:** Verifies both USDT and USDC payments.
*   **Multi-chain Support:** Works on Ethereum, Polygon, Base, Arbitrum, and BSC.
*   **Unique Deposit Addresses:** Automatically generates a new, unique payment address for each user using an HD wallet.
*   **Automated Setup:** Automatically initializes the database and sets the Telegram webhook on startup.
*   **Persistent:** Uses a PostgreSQL database to track deposit statuses.

## Deployment on Render

This bot is designed for easy deployment as a **Web Service** on Render.

### Step 1: Create a PostgreSQL Database

*   On your Render Dashboard, click **New > PostgreSQL**.
*   Create a database (the Free plan is fine).
*   After creation, copy the **Internal Connection String** from the "Info" tab.

### Step 2: Create the Web Service

*   On your Render Dashboard, click **New > Web Service** and connect your GitHub repository.
*   Enter the following settings:
    *   **Build Command:** `pip install -r requirements.txt`
    *   **Start Command:** `uvicorn backend.bot:app --host 0.0.0.0 --port 10000`

### Step 3: Add Environment Variables

Go to the **Environment** tab for your new service and add all the necessary variables.

*   **Crucial Variables:**
    *   `DATABASE_URL`: Paste the Internal Connection String from your Render database.
    *   `TELEGRAM_BOT_TOKEN`: Your token from BotFather.
    *   `HD_WALLET_MNEMONIC`: Your 12 or 24-word secret recovery phrase.
*   **RPC & Contract Addresses:**
    *   Add the `_RPC_URL` and `_CONTRACT_ADDRESS_` variables for all the chains you want to support, as defined in `.env.example`.

### Step 4: Deploy

*   Click **"Create Web Service"**.
*   On the first deployment, the bot will start, but it won't know its own public URL to set the webhook.
*   After the first deploy is live, copy the public URL Render gives you (e.g., `https://your-bot-name.onrender.com`).
*   Go back to the **Environment** tab, add a final variable:
    *   **Name:** `WEBHOOK_URL`
    *   **Value:** `https://your-bot-name.onrender.com`
*   Click **"Save Changes"**. This will trigger a final redeploy.

Upon this final deployment, the bot will automatically initialize the database and set its own webhook with Telegram. **There is no need to visit any URL manually.** Your bot is now live and stable.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
