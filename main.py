import logging
import re
import os # Import os for environment variables
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton # Import ReplyKeyboardMarkup and KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ChatMemberHandler, filters, ContextTypes
)

# Import handler functions from a separate 'handlers.py' file.
from handlers import (
    start, start_dice, close_bets_scheduled, roll_and_announce_scheduled,
    button_callback, handle_bet, show_score, show_stats,
    leaderboard, history, adjust_score, on_chat_member_update,
    check_user_score, refresh_admins, stop_game, # Ensure stop_game is imported
    deposit_points, withdraw_points # Import new handlers for buttons AND commands
)

# Configure logging for the bot.
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG # Keep DEBUG level for detailed output
)
logger = logging.getLogger(__name__)

# Define the custom reply 
# We use a 2D list to represent rows and columns of buttons.
custom_keyboard = [
    [KeyboardButton("ငွေထည့်မည်"), KeyboardButton("ငွေထုတ်မည်")],
    [KeyboardButton("Score"), KeyboardButton("Leaderboard"), KeyboardButton("ကစားနည်း")] # Added 'ကစားနည်း' button
]
# reply_markup=True makes the keyboard persistent and resize_keyboard=True adjusts its size
custom_keyboard_markup = ReplyKeyboardMarkup(custom_keyboard, resize_keyboard=True, one_time_keyboard=False)

# New handler for unhandled text messages
async def unhandled_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Logs all text messages that are not handled by other specific handlers."""
    if update.message and update.message.text:
        logger.debug(f"Unhandled text message received: '{update.message.text}' from user {update.effective_user.id} in chat {update.effective_chat.id}")

def main():
    """
    The main function that sets up and runs the Telegram bot.
    Initializes the Application and registers all handlers.
    """
    # Initialize the Application with your bot token.
    # It's highly recommended to load the token from an environment variable for security.
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN") #for production
    
    if not bot_token:
        logger.error("main: TELEGRAM_BOT_TOKEN environment variable not set!")
        raise ValueError("Bot token is not set. Please set the TELEGRAM_BOT_TOKEN environment variable.")


    application = ApplicationBuilder().token(bot_token).build()
    
    # Register command handlers.
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("startdice", start_dice))
    # Command handlers for Score and Leaderboard will remain so users can still type commands
    application.add_handler(CommandHandler("score", show_score))
    application.add_handler(CommandHandler(["stats","mystats"], show_stats))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("adjustscore", adjust_score))
    application.add_handler(CommandHandler("checkscore", check_user_score))
    application.add_handler(CommandHandler("refreshadmins", refresh_admins))
    application.add_handler(CommandHandler("stopgame", stop_game)) # Added handler for stop_game
    
    # --- New: Command Handlers for Deposit and Withdraw ---
    application.add_handler(CommandHandler("deposit", deposit_points))
    application.add_handler(CommandHandler("withdraw", withdraw_points))
    # --- End New ---

    # Register the CallbackQueryHandler to respond to inline keyboard button presses.
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Register the MessageHandler for text-based betting commands.
    bet_regex_pattern = re.compile(r"^(big|b|small|s|lucky|l)\s*(\d+)$", re.IGNORECASE)
    application.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(bet_regex_pattern),
        handle_bet
    ))

    # --- Message Handlers for the Custom Reply Keyboard Buttons ---
    # These handlers check for exact text matches from the custom keyboard.
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^ငွေထည့်မည်$"), deposit_points))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^ငွေထုတ်မည်$"), withdraw_points))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Score$"), show_score))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Leaderboard$"), leaderboard))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^ကစားနည်း$"), start)) # Handler for 'ကစားနည်း' button
    # --- End Custom Keyboard Handlers ---

    # Add a fallback handler for any text messages that are not commands or bets
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, # Filters out messages that are commands
        unhandled_message
    ))

    # Register ChatMemberHandler to detect when the bot joins/leaves a chat
    application.add_handler(ChatMemberHandler(on_chat_member_update, ChatMemberHandler.CHAT_MEMBER))

    logger.info("main: Dice Game Bot started polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
