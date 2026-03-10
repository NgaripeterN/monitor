# Crypto Payment Bot (SaaS Platform)

This is a multi-tenant platform that allows multiple "sellers" to use a single bot to verify crypto payments for their products. Each seller sets up their own wallet and can create "product bundles" containing one or more links, which are sold for a set price.

The system is built on a robust, asynchronous architecture using FastAPI and webhooks.

## Features

*   **Multi-Tenant:** Supports multiple, isolated sellers on a single bot instance.
*   **Seller Self-Service:** Sellers can register and manage their own wallets and products via secure Telegram commands.
*   **Encrypted Wallets:** Seller recovery phrases are encrypted at rest using a master key.
*   **Product Bundles:** Sellers can create products containing multiple links, and edit them with commands.
*   **Webhook Driven:** Uses FastAPI for instant and reliable message processing.
*   **Multi-Coin & Multi-chain Support:** Verifies USDT/USDC on configured chains.

## Deployment on Render

Deploy as a **Web Service** on Render.

### 1. Generate Your Encryption Key

Run this on your **local machine** to generate a secret key for encrypting seller wallets.
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Copy the output. This will be your `DATA_ENCRYPTION_KEY`.

### 2. Deploy on Render

1.  **Create a PostgreSQL Database** and copy the **Connection String**.
2.  **Create a new Web Service** on Render and connect your GitHub repository.
3.  **Settings:**
    *   **Build Command:** `pip install -r requirements.txt`
    *   **Start Command:** `uvicorn backend.bot:app --host 0.0.0.0 --port 10000`
4.  **Environment Variables:** Add all variables from `.env.example`.
5.  **Deploy (Two-Step Process):**
    1.  Deploy once **without** `WEBHOOK_URL`.
    2.  After it's live, copy the public URL, add it as the `WEBHOOK_URL` environment variable, and save. The bot will set its own webhook automatically on the next startup.

## How to Use (Seller & Buyer Guide)

### 1. As a New Seller

*   **/register `<YourShopName>`**: Creates your seller account.
*   **/setwallet `<12-24 word phrase>`**: Securely sets your payment wallet. Use a new, empty wallet. **Your message is deleted immediately.**
*   **/addproduct `<Price>` `<Product Name>`**: Creates a product bundle and returns a `ProductID`.
*   **/addlink `<ProductID>` `<Link>`**: Adds a link (e.g., for Dropbox, Telegram) to your product bundle.
*   **/myproducts**: Lists all your products, their links (with `LinkID`s), and the unique `t.me` link to give to your buyers.
*   **/editprice `<ProductID>` `<NewPrice>`**: Changes the price of a product.
*   **/removelink `<LinkID>`**: Removes a specific link from a product bundle.

### 2. As a Buyer

*   The buyer clicks the deep link from the seller (e.g., `...start=123`).
*   The bot guides them through the payment process.
*   Upon successful payment, the bot sends them a message with all the links in the product bundle they purchased.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
