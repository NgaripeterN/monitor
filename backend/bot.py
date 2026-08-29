import os
import logging
import asyncio
import html
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import Forbidden, TelegramError
from bip_utils import Bip39MnemonicValidator

from backend.database import (
    create_all_tables, add_seller, get_seller_by_telegram_id, add_seller_wallet, get_wallet_by_seller_id, get_wallet_by_id,
    get_seller_wallets, set_default_wallet, assign_wallet_to_product, assign_unassigned_products_to_wallet,
    add_product, get_seller_products_with_links, get_product_by_id, add_link_to_product, get_product_links,
    update_product_price, update_product_name, delete_product_link, update_seller_name, create_deposit_address,
    get_pending_deposit_for_user, confirm_payment, get_next_address_index, get_deposit_by_id
)
from backend.hd_wallet import generate_new_address
from backend.blockchain import check_payment_on_address

def escape_html(text):
    """Helper to escape strings for Telegram's HTML parse mode."""
    if not text:
        return ""
    return html.escape(str(text))

# --- Initial Setup & Config ---
load_dotenv()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
RPC_URLS = { chain: os.getenv(f"{chain}_RPC_URL") for chain in ["ETH", "POLYGON", "BASE", "ARBITRUM", "BSC"] }
TOKEN_CONTRACTS = {
    "USDT": {"ETH": "0xdac17f958d2ee523a2206206994597c13d831ec7", "POLYGON": "0xc2132d05d31c914a87c6611c10748aeb04b58e8f", "BASE": "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2", "ARBITRUM": "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9", "BSC": "0x55d398326f99059ff775485246999027b3197955"},
    "USDC": {"ETH": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "POLYGON": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", "BASE": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "ARBITRUM": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "BSC": "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d"}
}

CHAIN_DETAILS = {
    "ETH": {"name": "Ethereum (ERC-20)", "native": "ETH"},
    "POLYGON": {"name": "Polygon (POS)", "native": "POL / MATIC"},
    "BASE": {"name": "Base", "native": "ETH"},
    "ARBITRUM": {"name": "Arbitrum One", "native": "ETH"},
    "BSC": {"name": "BNB Smart Chain (BEP-20)", "native": "BNB"},
}

application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and handle specific telegram errors like Forbidden gracefully."""
    if isinstance(context.error, Forbidden):
        user_id = update.effective_user.id if (update and getattr(update, "effective_user", None)) else "unknown"
        logger.warning("Telegram request failed: Bot was blocked by user (ID: %s).", user_id)
    elif isinstance(context.error, TelegramError):
        logger.warning("Telegram API error: %s", context.error)
    else:
        logger.error("Exception while handling an update:", exc_info=context.error)

# --- Auth Decorator ---
def is_seller(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        message = update.effective_message
        if not user or not message:
            return
        seller = get_seller_by_telegram_id(user.id)
        if not seller:
            try:
                await message.reply_text("You are not a registered seller. Use /register to sign up.")
            except Forbidden:
                logger.warning("Cannot reply to user %s: bot was blocked.", user.id)
            return
        context.user_data['seller_id'] = seller[0]
        return await func(update, context)
    return wrapper

# --- Seller & Public Commands ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    if context.args:
        # Handling a buyer who used a product link
        product_id_str = context.args[0]
        try:
            product = get_product_by_id(int(product_id_str))
            if not product or not product[5]:
                return await msg.reply_text("This product link is invalid or unavailable.")
        except (ValueError, IndexError):
            return await msg.reply_text("Invalid product link.")

        _, seller_id, _, _, _, is_active, wallet_id = product
        if not is_active or not wallet_id:
            return await msg.reply_text("This product is currently inactive because the seller has not assigned a payment wallet.")

        context.user_data['product_id'] = product[0]
        _, _, name, price, currency, _, _ = product
        keyboard = [[InlineKeyboardButton("✅ Proceed to Payment", callback_data="show_chains")]]
        await msg.reply_text(
            f"Welcome! You are paying for <b>{escape_html(name)}</b>.\n\n"
            f"Amount: <b>${float(price):.2f}</b> in {currency} or USDC.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    else:
        # General landing page for new users/sellers
        await msg.reply_text(
            "Welcome to <b>AccessBot</b>, the ultimate crypto payment gateway for digital sellers.\n\n"
            "Sell Telegram invites, Mega links, and digital bundles with automated crypto checkouts.\n\n"
            "🚀 <b>Key Features:</b>\n"
            "✅ <b>Instant Payouts:</b> Non-custodial system, funds go straight to your wallet.\n"
            "✅ <b>Multi-chain Support:</b> Accept USDT/USDC on BSC, Base, Polygon, ETH, and Arbitrum.\n"
            "✅ <b>Automated Delivery:</b> Bot delivers links instantly after payment verification.\n"
            "✅ <b>Privacy First:</b> Fresh deposit addresses for every customer.\n\n"
            "Ready to start earning? Use /register &lt;YourShopName&gt; to set up your shop.",
            parse_mode="HTML"
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    help_text = (
        "📚 <b>AccessBot Help Center</b>\n\n"
        "<b>For Sellers:</b>\n"
        "1. <code>/register &lt;ShopName&gt;</code> - Create your seller account.\n"
        "2. <code>/addproduct &lt;Price&gt; &lt;Name&gt;</code> - Create a product bundle.\n"
        "3. <code>/addlink &lt;ProductID&gt; &lt;Link&gt;</code> - Add a link to your product.\n"
        "4. <code>/setwallet &lt;Phrase&gt;</code> - Set your first payment wallet.\n"
        "5. <code>/myproducts</code> - Get your shareable buyer links and manage products.\n\n"
        "<b>Additional Commands:</b>\n"
        "• <code>/editshopname &lt;NewName&gt;</code> - Change your shop's display name.\n"
        "• <code>/editprice &lt;ProductID&gt; &lt;NewPrice&gt;</code> - Update a product's price.\n"
        "• <code>/editname &lt;ProductID&gt; &lt;NewName&gt;</code> - Update a product's name.\n"
        "• <code>/addwallet &lt;Phrase&gt;</code> - Add another payment wallet.\n"
        "• <code>/wallets</code> - List your wallet IDs and default wallet.\n"
        "• <code>/usewallet &lt;WalletID&gt;</code> - Use a wallet by default for new products.\n"
        "• <code>/assignwallet &lt;ProductID&gt; &lt;WalletID&gt;</code> - Set a product's payment wallet.\n"
        "• <code>/removelink &lt;LinkID&gt;</code> - Delete a link from a bundle.\n\n"
        "💡 <i>Tip: For your security, always use a fresh, empty wallet recovery phrase for /setwallet.</i>"
    )
    await msg.reply_text(help_text, parse_mode="HTML")

async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return
    if len(context.args) < 1:
        return await msg.reply_text("Usage: /register <YourShopName>\nExample: /register MyDigitalShop")
    name = " ".join(context.args)
    success, message = add_seller(name, user.id)
    if not success:
        return await msg.reply_text(message)
    
    await msg.reply_text(
        "✅ Seller account created successfully!\n\n"
        "<b>Step 1: Create a Product</b>\n"
        "Use the command: <code>/addproduct &lt;Price&gt; &lt;Name&gt;</code>\n"
        "Example: <code>/addproduct 19.99 Premium Bundle</code>",
        parse_mode="HTML"
    )

@is_seller
async def edit_shop_name_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    if len(context.args) < 1:
        return await msg.reply_text("Usage: /editshopname <NewName>")
    new_name = " ".join(context.args)
    if update_seller_name(context.user_data['seller_id'], new_name):
        await msg.reply_text("✅ Your shop name has been updated.")
    else:
        await msg.reply_text("❌ There was an error updating your shop name.")

@is_seller
async def set_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return

    if len(context.args) == 0:
        return await msg.reply_text(
            "🔑 <b>How to set your payment wallet:</b>\n\n"
            "Use the command: <code>/setwallet &lt;12 or 24 recovery words&gt;</code>\n"
            "Example: <code>/setwallet word1 word2 word3 ... word12</code>\n\n"
            "💡 <b>Where to get a seed phrase:</b>\n"
            "• Create a new, fresh wallet in <b>Trust Wallet</b>, <b>MetaMask</b>, <b>Exodus</b>, or <b>Phantom</b>.\n"
            "• Copy your 12 or 24-word recovery phrase (BIP-39 seed phrase).\n"
            "• Send it here with <code>/setwallet</code>.\n\n"
            "🔒 <b>Security Notice:</b> Your message will be instantly deleted upon sending to protect your phrase. Always use a fresh, empty wallet.",
            parse_mode="HTML"
        )

    mnemonic = " ".join(context.args)
    try:
        await msg.delete()
    except TelegramError:
        pass

    if len(context.args) not in [12, 24] or not Bip39MnemonicValidator().IsValid(mnemonic):
        return await msg.reply_text(
            "❌ <b>Invalid recovery phrase.</b>\n\n"
            "Your phrase must be exactly 12 or 24 valid BIP-39 English words separated by spaces.\n"
            "<i>(Your message was deleted for security.)</i>",
            parse_mode="HTML"
        )

    seller_id = context.user_data['seller_id']
    if get_wallet_by_seller_id(seller_id):
        return await msg.reply_text(
            "⚠️ You already have a default wallet. Use <code>/addwallet &lt;Phrase&gt;</code> to add another wallet, "
            "or <code>/usewallet &lt;WalletID&gt;</code> to change the default.",
            parse_mode="HTML"
        )

    wallet_id = add_seller_wallet(seller_id, mnemonic, is_default=True)
    assign_unassigned_products_to_wallet(seller_id, wallet_id)
    await msg.reply_text(
        "✅ First wallet set successfully! Existing products without a wallet now use it.\n\n"
        "Use <code>/myproducts</code> to see your shareable buyer links.",
        parse_mode="HTML"
    )

@is_seller
async def add_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    if len(context.args) == 0:
        return await msg.reply_text("Usage: /addwallet <12 or 24 recovery words>")

    mnemonic = " ".join(context.args)
    try:
        await msg.delete()
    except TelegramError:
        pass
    if len(context.args) not in [12, 24] or not Bip39MnemonicValidator().IsValid(mnemonic):
        return await msg.reply_text("❌ Invalid recovery phrase. Your message was deleted for security.")

    wallet_id = add_seller_wallet(context.user_data['seller_id'], mnemonic)
    await msg.reply_text(
        f"✅ Wallet <code>{wallet_id}</code> added. It is not the default; use "
        f"<code>/usewallet {wallet_id}</code> for new products or "
        f"<code>/assignwallet &lt;ProductID&gt; {wallet_id}</code> for a specific product.",
        parse_mode="HTML"
    )

@is_seller
async def wallets_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    wallets = get_seller_wallets(context.user_data['seller_id'])
    if not wallets:
        return await msg.reply_text("You have no wallets. Use /setwallet to add your first one.")
    lines = ["<b>Your wallets</b> (seed phrases are never shown):"]
    for wallet_id, is_default, created_at in wallets:
        default_marker = " — default for new products" if is_default else ""
        lines.append(f"• Wallet <code>{wallet_id}</code>{default_marker}")
    await msg.reply_text("\n".join(lines), parse_mode="HTML")

@is_seller
async def use_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    if len(context.args) != 1:
        return await msg.reply_text("Usage: /usewallet <WalletID>")
    try:
        wallet_id = int(context.args[0])
    except ValueError:
        return await msg.reply_text("❌ Invalid Wallet ID.")
    if set_default_wallet(context.user_data['seller_id'], wallet_id):
        await msg.reply_text(f"✅ Wallet <code>{wallet_id}</code> is now the default for new products.", parse_mode="HTML")
    else:
        await msg.reply_text("❌ Wallet not found or you are not the owner.")

@is_seller
async def assign_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    if len(context.args) != 2:
        return await msg.reply_text("Usage: /assignwallet <ProductID> <WalletID>")
    try:
        product_id, wallet_id = map(int, context.args)
    except ValueError:
        return await msg.reply_text("❌ Product ID and Wallet ID must be numbers.")
    if assign_wallet_to_product(product_id, context.user_data['seller_id'], wallet_id):
        await msg.reply_text(
            f"✅ New payments for product <code>{product_id}</code> will use wallet <code>{wallet_id}</code>. "
            "Existing pending deposits keep their original address.",
            parse_mode="HTML"
        )
    else:
        await msg.reply_text("❌ Product or wallet not found, or you are not the owner.")

@is_seller
async def add_product_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    if len(context.args) < 2:
        return await msg.reply_text("Usage: /addproduct <Price> <Name...>")
    price_str, *name_parts = context.args
    product_name = " ".join(name_parts)
    try:
        wallet = get_wallet_by_seller_id(context.user_data['seller_id'])
        product_id = add_product(context.user_data['seller_id'], product_name, float(price_str), wallet["id"] if wallet else None)
        payment_step = (
            "<b>Payments</b>\n"
            "Your existing payment wallet will automatically be used for this product."
            if wallet else
            "<b>Step 3: Activate Payments</b>\n"
            "Use <code>/setwallet &lt;Phrase&gt;</code> once to activate your shop and all its products."
        )
        await msg.reply_text(
            f"✅ Product '<b>{escape_html(product_name)}</b>' created with ID: <code>{product_id}</code>.\n\n"
            "<b>Step 2: Add Links</b>\n"
            f"Use the command: <code>/addlink {product_id} &lt;Link&gt;</code>\n"
            f"Example: <code>/addlink {product_id} https://example.com/file</code>\n\n"
            f"{payment_step}",
            parse_mode="HTML"
        )
    except ValueError:
        await msg.reply_text("❌ Invalid price.")

@is_seller
async def add_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    if len(context.args) != 2:
        return await msg.reply_text("Usage: /addlink <ProductID> <Link>")
    product_id_str, link = context.args
    if not (link.startswith("http://") or link.startswith("https://")):
        return await msg.reply_text("❌ Invalid link format.")
    try:
        if add_link_to_product(int(product_id_str), context.user_data['seller_id'], link):
            product = get_product_by_id(int(product_id_str))
            has_wallet = product and product[6]
            payment_message = (
                "The wallet assigned to this product will be used for its payments. "
                "Use <code>/myproducts</code> to get its buyer link."
                if has_wallet else
                "<b>Step 3: Assign Payments</b>\n"
                "Use <code>/assignwallet &lt;ProductID&gt; &lt;WalletID&gt;</code> to activate this product."
            )
            await msg.reply_text(
                f"✅ Link added to product <code>{product_id_str}</code>!\n\n"
                f"{payment_message}",
                parse_mode="HTML"
            )
        else:
            await msg.reply_text("❌ Product not found or you are not the owner.")
    except ValueError:
        await msg.reply_text("❌ Invalid Product ID.")

@is_seller
async def edit_price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    if len(context.args) != 2:
        return await msg.reply_text("Usage: /editprice <ProductID> <NewPrice>")
    product_id_str, new_price_str = context.args
    try:
        if update_product_price(int(product_id_str), context.user_data['seller_id'], float(new_price_str)):
            await msg.reply_text("✅ Price updated.")
        else:
            await msg.reply_text("❌ Product not found or you are not the owner.")
    except ValueError:
        await msg.reply_text("❌ Invalid Product ID or Price.")

@is_seller
async def edit_product_name_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    if len(context.args) < 2:
        return await msg.reply_text("Usage: /editname <ProductID> <NewName...>")

    product_id_str, *name_parts = context.args
    new_name = " ".join(name_parts)
    try:
        if update_product_name(int(product_id_str), context.user_data['seller_id'], new_name):
            await msg.reply_text("✅ Product name updated.")
        else:
            await msg.reply_text("❌ Product not found or you are not the owner.")
    except ValueError:
        await msg.reply_text("❌ Invalid Product ID.")

@is_seller
async def remove_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    if len(context.args) != 1:
        return await msg.reply_text("Usage: /removelink <LinkID>")
    try:
        if delete_product_link(int(context.args[0]), context.user_data['seller_id']):
            await msg.reply_text("✅ Link removed.")
        else:
            await msg.reply_text("❌ Link not found or you are not the owner.")
    except ValueError:
        await msg.reply_text("❌ Invalid Link ID.")

@is_seller
async def my_products_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg:
        return
    seller_id = context.user_data['seller_id']
    products = get_seller_products_with_links(seller_id)

    if not products:
        return await msg.reply_text("You have no products. Use /addproduct to create one.")

    bot_username = (await context.bot.get_me()).username
    message = "Your products:\n\n"

    for product in products:
        message += f"<b>{escape_html(product['name'])}</b> (${float(product['price']):.2f}) - ID: <code>{product['id']}</code>\n"
        if product['wallet_id']:
            message += f"- Payment wallet: <code>{product['wallet_id']}</code>\n"
            deep_link = f"https://t.me/{bot_username}?start={product['id']}"
            message += f"- Buyer Link: {deep_link}\n"
        else:
            message += "- Buyer Link: [INACTIVE - use /assignwallet]\n"

        if product['links']:
            message += "- Links in bundle:\n"
            for link_id, link_url in product['links']:
                message += f"  - <code>{escape_html(link_url)}</code> (LinkID: <code>{link_id}</code>)\n"
        else:
            message += "- No links added yet. Use /addlink.\n"
        message += "\n"

    await msg.reply_text(message, parse_mode="HTML")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    product_id = context.user_data.get('product_id')
    callback_data = query.data

    if not product_id:
        return await query.edit_message_text("Your session has expired. Please restart using the seller's link.")

    product = get_product_by_id(product_id)
    if not product:
        return await query.edit_message_text("This product is no longer available.")

    prod_id, seller_id, name, price, currency, is_active, wallet_id = product

    if callback_data == "show_chains" or callback_data == "back_to_chains":
        buttons = [InlineKeyboardButton(chain, callback_data=f"deposit_{chain}") for chain in RPC_URLS if RPC_URLS.get(chain)]
        keyboard = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        await query.edit_message_text(
            "Please select the network for your deposit:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif callback_data.startswith("deposit_"):
        chain = callback_data.split("_")[1]
        wallet = get_wallet_by_id(wallet_id, seller_id) if wallet_id else None
        if not wallet:
            return await query.edit_message_text("Seller has not configured their wallet.")
        
        wallet_id, mnemonic = wallet["id"], wallet["mnemonic"]
        
        # Check if this user already has a pending deposit for this product on this chain
        existing_deposit = get_pending_deposit_for_user(user_id, product_id, chain)
        
        if existing_deposit:
            deposit_id, address = existing_deposit
        else:
            # Generate a new unique address
            next_index = get_next_address_index(wallet_id)
            address = generate_new_address(mnemonic, next_index)
            try:
                deposit_id = create_deposit_address(product_id, wallet_id, user_id, address, next_index, seller_id, chain)
            except Exception as e:
                # Handle potential race condition if another process took the index
                logger.error(f"Error creating deposit: {e}")
                return await query.edit_message_text("An error occurred. Please try again.")

        context.user_data['deposit_id'] = deposit_id
        keyboard = [
            [InlineKeyboardButton("✅ I Have Paid", callback_data=f"check_{chain}")],
            [InlineKeyboardButton("⬅️ Back", callback_data="show_chains")]
        ]
        chain_info = CHAIN_DETAILS.get(chain, {"name": chain, "native": "native coin"})
        chain_name = chain_info["name"]
        native_token = chain_info["native"]
        formatted_price = f"{float(price):.2f}"

        deposit_text = (
            f"💳 <b>Payment Details</b>\n\n"
            f"• <b>Amount:</b> <code>{formatted_price} USDC</code> or <code>{formatted_price} USDT</code>\n"
            f"• <b>Network:</b> <b>{chain_name}</b>\n"
            f"• <b>Deposit Address:</b>\n"
            f"<code>{address}</code>\n\n"
            f"⚠️ <b>Important:</b>\n"
            f"• Send <b>USDC or USDT only</b> (do <b>NOT</b> send {native_token}).\n"
            f"• <b>Wallets (MetaMask / Trust):</b> Keep a little {native_token} for gas.\n"
            f"• <b>Exchanges (Kraken / Binance / OKX):</b> Withdraw directly to the address above (no gas needed)."
        )

        await query.edit_message_text(
            deposit_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

    elif callback_data.startswith("check_"):
        deposit_id = context.user_data.get('deposit_id')
        if not deposit_id:
            return await query.edit_message_text("Could not find an active deposit. Please restart.")
        deposit_record = get_deposit_by_id(deposit_id)
        if not deposit_record:
            return await query.edit_message_text("Deposit record not found.")

        _, _, _, deposit_address = deposit_record
        chain = callback_data.split("_")[1]
        await query.edit_message_text(f"⏳ Scanning {chain} for your payment...")
        rpc_url = RPC_URLS.get(chain)
        tokens_to_check = {token: contract.get(chain) for token, contract in TOKEN_CONTRACTS.items() if contract.get(chain)}
        coin_type, tx_hash, amount_paid = check_payment_on_address(chain, rpc_url, deposit_address, float(price), tokens_to_check)

        if tx_hash:
            confirm_payment(deposit_id, tx_hash, amount_paid, coin_type)
            links = get_product_links(product_id)
            links_text = "\n".join(links)
            await query.edit_message_text(
                f"✅ Payment of {amount_paid:.2f} {coin_type} confirmed!\n\n"
                f"Your link(s):\n{links_text}"
            )
        else:
            keyboard = [
                [InlineKeyboardButton("I Have Paid", callback_data=f"check_{chain}")],
                [InlineKeyboardButton("⬅️ Back", callback_data="show_chains")]
            ]
            await query.edit_message_text(
                "Payment not detected yet. Please try again in a few minutes.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

# --- FastAPI Application ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all_tables()

    commands = [
        BotCommand("start", "Start the bot or view landing page"),
        BotCommand("help", "View full command guide"),
        BotCommand("register", "Create your seller account"),
        BotCommand("myproducts", "List and manage your products"),
        BotCommand("addproduct", "Create a new product bundle"),
        BotCommand("addlink", "Add a link to a product"),
        BotCommand("removelink", "Remove a link from a product"),
        BotCommand("editprice", "Change a product's price"),
        BotCommand("editname", "Change a product name"),
        BotCommand("editshopname", "Change your shop name"),
        BotCommand("setwallet", "Set your payment wallet"),
        BotCommand("addwallet", "Add another payment wallet"),
        BotCommand("wallets", "List your payment wallets"),
        BotCommand("usewallet", "Set default wallet for new products"),
        BotCommand("assignwallet", "Assign a wallet to a product"),
    ]
    await application.bot.set_my_commands(commands)

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("register", register_command))
    application.add_handler(CommandHandler("setwallet", set_wallet_command))
    application.add_handler(CommandHandler("addwallet", add_wallet_command))
    application.add_handler(CommandHandler("wallets", wallets_command))
    application.add_handler(CommandHandler("usewallet", use_wallet_command))
    application.add_handler(CommandHandler("assignwallet", assign_wallet_command))
    application.add_handler(CommandHandler("addproduct", add_product_command))
    application.add_handler(CommandHandler("addlink", add_link_command))
    application.add_handler(CommandHandler("editprice", edit_price_command))
    application.add_handler(CommandHandler("editname", edit_product_name_command))
    application.add_handler(CommandHandler("removelink", remove_link_command))
    application.add_handler(CommandHandler("myproducts", my_products_command))
    application.add_handler(CommandHandler("editshopname", edit_shop_name_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    application.add_error_handler(error_handler)

    await application.initialize()
    if WEBHOOK_URL:
        await application.bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")
    yield
    await application.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/", include_in_schema=False)
async def index():
    return {"status": "ok"}

@app.head("/", include_in_schema=False)
async def head():
    return {"status": "ok"}

@app.post("/telegram")
async def webhook(request: Request):
    update = Update.de_json(data=await request.json(), bot=application.bot)
    await application.process_update(update)
    return {"status": "ok"}
