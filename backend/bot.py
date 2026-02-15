import os
import logging
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


# --- Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    user_id = update.message.from_user.id
    
    # Check if the user has already paid
    if has_user_paid(user_id):
        await update.message.reply_text(
            "Welcome back! You already have access. Here is the link just in case:\n"
            f"{TELEGRAM_INVITE_LINK}"
        )
        return

    # If the user hasn't paid, show the welcome message and payment button
    keyboard = [[InlineKeyboardButton("Get Deposit Address", callback_data="create_deposit_address")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Welcome to the Payment Bot!\n\n"
        f"To get your invite link, you need to make a one-time payment of {MIN_STABLECOIN_AMOUNT} USDT or USDC.\n\n"
        "Click the button below to generate your unique deposit address.",
        reply_markup=reply_markup
    )

# --- Callback Handlers for Button Presses ---
async def handle_button_press(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles all button presses and routes them to the correct function."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data

    if callback_data == "create_deposit_address":
        await query.edit_message_text(text="Please select the network for your deposit:")
        keyboard = [[InlineKeyboardButton(chain, callback_data=f"deposit_{chain}") for chain in CHAINS.keys()]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="Please select the network for your deposit:", reply_markup=reply_markup)

    elif callback_data.startswith("deposit_"):
        chain = callback_data.split("_")[1]
        
        # Check if user already has a pending address for this chain
        pending_deposit = get_pending_deposit_for_user(user_id, chain)
        
        if pending_deposit:
            address = pending_deposit[3] # (id, user_id, chain, address, ...)
        else:
            # Generate a new address
            next_index = get_next_address_index()
            address = generate_new_address(next_index)
            create_deposit_address(user_id, chain, address, next_index)

        await show_deposit_address(query, chain, address)

    elif callback_data.startswith("check_"):
        chain = callback_data.split("_")[1]
        pending_deposit = get_pending_deposit_for_user(user_id, chain)

        if not pending_deposit:
            await query.edit_message_text("Error: Could not find a pending deposit for you. Please try generating an address again.")
            return

        deposit_id, _, _, address, _ = pending_deposit
        await query.edit_message_text(f"Scanning {chain} for your payment to {address[:10]}... This may take a moment.")
        
        coin_type, tx_hash, amount_paid = check_payment_on_address(chain, address)

        if tx_hash:
            confirm_payment(deposit_id, tx_hash, amount_paid, coin_type)
            await query.edit_message_text(
                f"Payment of {amount_paid} {coin_type} confirmed! Thank you.\n\n"
                f"Here is your invite link: {TELEGRAM_INVITE_LINK}"
            )
        else:
            keyboard = [[InlineKeyboardButton("I Have Paid", callback_data=f"check_{chain}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "Payment not detected yet. Please ensure your transaction has been confirmed on the blockchain and try again in a few minutes.",
                reply_markup=reply_markup
            )


async def show_deposit_address(query, chain, address):
    """Displays the deposit address and instructions to the user."""
    keyboard = [[InlineKeyboardButton("I Have Paid", callback_data=f"check_{chain}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Please send at least {MIN_STABLECOIN_AMOUNT} USDT or USDC to the following address on the {chain} network:\n\n"
        f"`{address}`\n\n"
        "**Important:**\n"
        f"- Send only USDT or USDC on the {chain} network.\n"
        "- Sending any other token or using a different network will result in the loss of your funds.\n\n"
        "Once your transaction is confirmed on the blockchain, click the button below.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


# --- Main Bot Function ---
def main() -> None:
    """Sets up and runs the Telegram bot."""
    # Ensure the database and table are created before starting
    print("Initializing database...")
    create_deposits_table()
    
    print("Starting bot...")
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(handle_button_press))

    # Start the bot
    application.run_polling()
    print("Bot stopped.")


if __name__ == '__main__':
    main()
