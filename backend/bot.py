import os
import logging
import asyncio
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from bip_utils import Bip39Mnemonic

from backend.database import (
    create_all_tables, add_seller, get_seller_by_telegram_id, set_seller_wallet, get_wallet_by_seller_id,
    add_product, get_seller_products_with_links, get_product_by_id, add_link_to_product, get_product_links,
    update_product_price, delete_product_link, create_deposit_address, get_pending_deposit_for_user,
    confirm_payment, get_next_address_index, get_deposit_by_id
)
from backend.hd_wallet import generate_new_address
from backend.blockchain import check_payment_on_address

# --- Initial Setup & Config ---
load_dotenv()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_TELEGRAM_USER_ID = int(os.getenv("ADMIN_TELEGRAM_USER_ID", 0))
RPC_URLS = { chain: os.getenv(f"{chain}_RPC_URL") for chain in ["ETH", "POLYGON", "BASE", "ARBITRUM", "BSC"] }
TOKEN_CONTRACTS = {
    "USDT": {"ETH": "0xdac17f958d2ee523a2206206994597c13d831ec7", "POLYGON": "0xc2132d05d31c914a87c6611c10748aeb04b58e8f", "BASE": "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2", "ARBITRUM": "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9", "BSC": "0x55d398326f99059ff775485246999027b3197955"},
    "USDC": {"ETH": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "POLYGON": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", "BASE": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "ARBITRUM": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "BSC": "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d"}
}

application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# --- Auth Decorators ---
def is_seller(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        seller = get_seller_by_telegram_id(update.message.from_user.id)
        if not seller:
            await update.message.reply_text("You are not a registered seller. Use /register to sign up.")
            return
        context.user_data['seller_id'] = seller[0]
        return await func(update, context)
    return wrapper

# --- Seller & Public Commands ---
async def register_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1: return await update.message.reply_text("Usage: /register <YourShopName>")
    name = " ".join(context.args)
    success, message = add_seller(name, update.message.from_user.id)
    await update.message.reply_text(message)
    if success:
        await update.message.reply_text("Next, set your wallet with /setwallet <12 or 24 word phrase>.")

@is_seller
async def set_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mnemonic = " ".join(context.args)
    await update.message.delete()
    if len(context.args) not in [12, 24] or not Bip39Mnemonic.IsValid(mnemonic):
        return await update.message.reply_text("❌ Invalid recovery phrase. Your message was deleted for security.")
    set_seller_wallet(context.user_data['seller_id'], mnemonic)
    await update.message.reply_text("✅ Wallet set. Your message was deleted.")

@is_seller
async def add_product_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2: return await update.message.reply_text("Usage: /addproduct <Price> <Name...>")
    price_str, *name_parts = context.args
    try:
        product_id = add_product(context.user_data['seller_id'], " ".join(name_parts), float(price_str))
        await update.message.reply_text(f"✅ Product created with ID: `{product_id}`. Now add links with `/addlink`.", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ Invalid price.")

@is_seller
async def add_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2: return await update.message.reply_text("Usage: /addlink <ProductID> <Link>")
    product_id_str, link = context.args
    if not (link.startswith("http://") or link.startswith("https://")):
        return await update.message.reply_text("❌ Invalid link format.")
    try:
        if add_link_to_product(int(product_id_str), context.user_data['seller_id'], link):
            await update.message.reply_text(f"✅ Link added to product {product_id_str}.")
        else:
            await update.message.reply_text("❌ Product not found or you are not the owner.")
    except ValueError:
        await update.message.reply_text("❌ Invalid Product ID.")

@is_seller
async def edit_price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 2: return await update.message.reply_text("Usage: /editprice <ProductID> <NewPrice>")
    product_id_str, new_price_str = context.args
    try:
        if update_product_price(int(product_id_str), context.user_data['seller_id'], float(new_price_str)):
            await update.message.reply_text("✅ Price updated.")
        else:
            await update.message.reply_text("❌ Product not found or you are not the owner.")
    except ValueError:
        await update.message.reply_text("❌ Invalid Product ID or Price.")

@is_seller
async def remove_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1: return await update.message.reply_text("Usage: /removelink <LinkID>")
    try:
        if delete_product_link(int(context.args[0]), context.user_data['seller_id']):
            await update.message.reply_text("✅ Link removed.")
        else:
            await update.message.reply_text("❌ Link not found or you are not the owner.")
    except ValueError:
        await update.message.reply_text("❌ Invalid Link ID.")

@is_seller
async def my_products_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = get_seller_products_with_links(context.user_data['seller_id'])
    if not products: return await update.message.reply_text("You have no products.")
    bot_username = (await context.bot.get_me()).username
    message = "Your products:

"
    for product in products:
        deep_link = f"https://t.me/{bot_username}?start={product['id']}"
        message += f"**{product['name']}** (${float(product['price']):.2f}) - ID: `{product['id']}`
- Buyer Link: `{deep_link}`
"
        if product['links']:
            message += "- Links in bundle:
"
            for link_id, link_url in product['links']:
                message += f"  - `{link_url}` (LinkID: `{link_id}`)
"
        else:
            message += "- No links added yet. Use /addlink.
"
        message += "
"
    await update.message.reply_text(message, parse_mode="Markdown")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("Welcome! To become a seller, use /register <YourShopName>. To buy, use a seller's product link.")
    product_id_str = context.args[0]
    try:
        product = get_product_by_id(int(product_id_str))
        if not product or not product[5]:
            return await update.message.reply_text("This product link is invalid or unavailable.")
    except (ValueError, IndexError): return await update.message.reply_text("Invalid product link.")
    context.user_data['product_id'] = product[0]
    _, _, name, price, currency, _ = product
    keyboard = [[InlineKeyboardButton("✅ Proceed to Payment", callback_data="show_chains")]]
    await update.message.reply_text(f"Welcome! You are paying for **{name}**.

Amount: **${float(price):.2f}** in {currency} or USDC.", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    user_id = query.from_user.id
    product_id = context.user_data.get('product_id')
    callback_data = query.data
    if not product_id: return await query.edit_message_text("Your session has expired. Please restart using the seller's link.")
    product = get_product_by_id(product_id)
    if not product: return await query.edit_message_text("This product is no longer available.")
    prod_id, seller_id, name, price, currency, is_active = product

    if callback_data == "show_chains":
        buttons = [InlineKeyboardButton(chain, callback_data=f"deposit_{chain}") for chain in RPC_URLS if RPC_URLS.get(chain)]
        keyboard = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        await query.edit_message_text("Please select the network for your deposit:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif callback_data.startswith("deposit_"):
        chain = callback_data.split("_")[1]
        wallet = get_wallet_by_seller_id(seller_id)
        if not wallet: return await query.edit_message_text("Seller has not configured their wallet.")
        wallet_id, mnemonic = wallet["id"], wallet["mnemonic"]
        next_index = get_next_address_index(wallet_id)
        address = generate_new_address(mnemonic, next_index)
        deposit_id = create_deposit_address(product_id, wallet_id, user_id, address, next_index)
        context.user_data['deposit_id'] = deposit_id
        keyboard = [[InlineKeyboardButton("✅ I Have Paid", callback_data=f"check_{chain}")], [InlineKeyboardButton("⬅️ Back", callback_data="show_chains")]]
        await query.edit_message_text(f"Please send **${float(price):.2f}** (+ gas) to this address on the **{chain}** network:

`{address}`", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif callback_data.startswith("check_"):
        deposit_id = context.user_data.get('deposit_id')
        if not deposit_id: return await query.edit_message_text("Could not find an active deposit. Please restart.")
        _, _, wallet_id, deposit_address = get_deposit_by_id(deposit_id)
        chain = callback_data.split("_")[1]
        await query.edit_message_text(f"⏳ Scanning {chain} for your payment...")
        rpc_url = RPC_URLS.get(chain)
        tokens_to_check = {token: contract.get(chain) for token, contract in TOKEN_CONTRACTS.items() if contract.get(chain)}
        coin_type, tx_hash, amount_paid = check_payment_on_address(chain, rpc_url, deposit_address, float(price), tokens_to_check)
        if tx_hash:
            confirm_payment(deposit_id, tx_hash, amount_paid, coin_type)
            links = get_product_links(product_id)
            links_text = "
".join(links)
            await query.edit_message_text(f"✅ Payment of {amount_paid:.2f} {coin_type} confirmed!

Your link(s):
{links_text}")
        else:
            keyboard = [[InlineKeyboardButton("I Have Paid", callback_data=f"check_{chain}")], [InlineKeyboardButton("⬅️ Back", callback_data="show_chains")]]
            await query.edit_message_text("Payment not detected yet. Please try again in a few minutes.", reply_markup=InlineKeyboardMarkup(keyboard))

# --- FastAPI Application ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all_tables()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("register", register_command))
    application.add_handler(CommandHandler("setwallet", set_wallet_command))
    application.add_handler(CommandHandler("addproduct", add_product_command))
    application.add_handler(CommandHandler("addlink", add_link_command))
    application.add_handler(CommandHandler("editprice", edit_price_command))
    application.add_handler(CommandHandler("removelink", remove_link_command))
    application.add_handler(CommandHandler("myproducts", my_products_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    await application.initialize()
    if WEBHOOK_URL: await application.bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")
    yield
    await application.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/", include_in_schema=False)
async def index(): return {"status": "ok"}
@app.head("/", include_in_schema=False)
async def head(): return {"status": "ok"}

@app.post("/telegram")
async def webhook(request: Request):
    update = Update.de_json(data=await request.json(), bot=application.bot)
    await application.process_update(update)
    return {"status": "ok"}
