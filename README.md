# Crypto Payment Bot (SaaS Platform)

This is a multi-tenant platform that allows multiple "sellers" to use a single bot to verify crypto payments for their products. Each seller sets up their own wallet and can create "product bundles" containing one or more invite links, which are sold for a set price.

The system is built on a robust, asynchronous architecture using FastAPI and webhooks.

## Features

*   **Multi-Tenant:** Supports multiple, isolated sellers on a single bot instance.
*   **Seller Self-Service:** Sellers can register and manage their own wallets and products via secure Telegram commands.
*   **Encrypted Wallets:** Seller recovery phrases are encrypted at rest using a master key.
*   **Product Bundles:** Sellers can create products containing multiple invite links, delivered to the buyer after a single payment.
*   **Dynamic Payments:** Buyers use deep links specific to a seller's product, ensuring payments go to the correct seller's wallet.
*   **Webhook Driven:** Uses FastAPI for instant and reliable message processing.
*   **Multi-Coin & Multi-chain Support:** Verifies USDT/USDC on configured chains.

## Deployment on Render

Deploy as a **Web Service** on Render.

### 1. Generate Your Encryption Key

Run this on your **local machine** to generate a secret key for encrypting seller wallets.
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Copy the output. This will be your `DATA_ENCRYPTION_KEY`.

### 2. Deploy on Render

1.  **Create a PostgreSQL Database** on a provider like Neon and copy the **Connection String**.
2.  **Create a new Web Service** on Render and connect your GitHub repository.
3.  **Settings:**
    *   **Build Command:** `pip install -r requirements.txt`
    *   **Start Command:** `uvicorn backend.bot:app --host 0.0.0.0 --port 10000`
4.  **Environment Variables:** Add all variables from `.env.example`, including your `DATABASE_URL`, `TELEGRAM_BOT_TOKEN`, `ADMIN_TELEGRAM_USER_ID`, and the `DATA_ENCRYPTION_KEY` you just generated.
5.  **Deploy (Two-Step Process):**
    1.  Create the service **without** the `WEBHOOK_URL` variable and deploy.
    2.  After it's live, copy the public URL, add it as the `WEBHOOK_URL` environment variable, and save. This triggers the final deploy. The bot will set its own webhook automatically.

## How to Use (Seller & Buyer Guide)

### 1. As a New Seller

*   **Register yourself:**
    `/register <YourShopName>`
    *   Example: `/register JohnsVIP`

*   **Set your wallet:** Send your 12 or 24-word phrase from a **new, empty wallet**. The message is **deleted immediately** for security.
    `/setwallet <word1> <word2> ...`

*   **Create a product bundle:**
    `/addproduct <Price> <Product Name>`
    *   This creates the "bundle" and gives back a `ProductID`.
    *   Example: `/addproduct 25.00 VIP Access Bundle`
    *   Bot will reply: `✅ Product 'VIP Access Bundle' created with ID: 1`.

*   **Add links to the bundle:** Use the `ProductID` from the previous step.
    `/addlink <ProductID> <InviteLink>`
    *   Example: `/addlink 1 https://t.me/group_A`
    *   Example: `/addlink 1 https://t.me/channel_B`

*   **View your products & get buyer links:**
    `/myproducts`
    *   The bot will list all your products and generate the unique `t.me/YourBot?start=<product_id>` deep link for each. Give these links to your buyers.

### 2. As a Buyer

*   The buyer clicks the deep link from the seller (e.g., `...start=1`).
*   Your bot guides them through the payment process.
*   Upon successful payment, the bot sends them a message with all the links in the product bundle they purchased.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
