import os
import logging
import asyncio
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- Module Imports ---
from backend.database import (
    create_deposits_table,
    has_user_paid,
    get_next_address_index,
    create_deposit_address,
    get_pending_deposit_for_user,
    confirm_payment
)
from backend.hd_wallet import generate_new_address
from backend.blockchain import check_payment_on_address, CHAINS, MIN_STABLECOIN_AMOUNT

# --- Initial Setup ---
load_dotenv()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Environment Variables ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_INVITE_LINK = os.getenv("TELEGRAM_INVITE_LINK")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# --- Bot Application Setup ---
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# --- Command & Callback Handlers (Logic is unchanged) ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if has_user_paid(user_id):
        await update.message.reply_text(f"Welcome back! You already have access.\n{TELEGRAM_INVITE_LINK}")
        return
    keyboard = [[InlineKeyboardButton("Get Deposit Address", callback_data="create_deposit_address")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"Welcome! To get access, please make a one-time payment of {MIN_STABLECOIN_AMOUNT} USDT or USDC.\n\n"
        "Click the button below to start.",
        reply_markup=reply_markup,
    )

async def handle_button_press(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    callback_data = query.data

    if callback_data == "create_deposit_address":
        buttons = [InlineKeyboardButton(chain, callback_data=f"deposit_{chain}") for chain in CHAINS.keys()]
        keyboard = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="Please select the network for your deposit:", reply_markup=reply_markup)
    elif callback_data.startswith("deposit_"):
        chain = callback_data.split("_")[1]
        pending_deposit = get_pending_deposit_for_user(user_id, chain)
        if pending_deposit:
            address = pending_deposit[3]
        else:
            next_index = get_next_address_index()
            address = generate_new_address(next_index)
            create_deposit_address(user_id, chain, address, next_index)
        await show_deposit_address(query, chain, address)
    elif callback_data.startswith("check_"):
        chain = callback_data.split("_")[1]
        pending_deposit = get_pending_deposit_for_user(user_id, chain)
        if not pending_deposit:
            await query.edit_message_text("Error: Could not find a pending deposit.")
            return
        deposit_id, _, _, address, _ = pending_deposit
        await query.edit_message_text(f"Scanning {chain} for your payment...")
        coin_type, tx_hash, amount_paid = check_payment_on_address(chain, address)
        if tx_hash:
            confirm_payment(deposit_id, tx_hash, amount_paid, coin_type)
            await query.edit_message_text(f"Payment of {amount_paid:.2f} {coin_type} confirmed!\n\nHere is your link: {TELEGRAM_INVITE_LINK}")
        else:
            keyboard = [[InlineKeyboardButton("I Have Paid", callback_data=f"check_{chain}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Payment not detected yet. Please try again in a few minutes.", reply_markup=reply_markup)

async def show_deposit_address(query, chain, address):
    keyboard = [[InlineKeyboardButton("I Have Paid", callback_data=f"check_{chain}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"Please send at least {MIN_STABLECOIN_AMOUNT} USDT or USDC to the following address on the {chain} network:\n\n`{address}`\n\n"
        "**Important:** Send only USDT or USDC on the correct network.\n\n"
        "Once your transaction is confirmed, click the button below.",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )

# Add handlers to the application
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CallbackQueryHandler(handle_button_press))

# --- FastAPI Application ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup
    print("Initializing database...")
    create_deposits_table()
    print("Initializing bot application...")
    await application.initialize()
    if WEBHOOK_URL:
        print(f"Setting webhook to {WEBHOOK_URL}/telegram")
        await application.bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")
    else:
        print("WEBHOOK_URL not set, skipping webhook setup.")
    
    yield
    
    # On shutdown
    print("Shutting down bot application...")
    await application.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def index():
    return {"status": "ok", "message": "Bot is running"}

@app.post("/telegram")
async def webhook(request: Request):
    """This endpoint receives the updates from Telegram."""
    update_data = await request.json()
    update = Update.de_json(data=update_data, bot=application.bot)
    await application.process_update(update)
    return {"status": "ok"}
