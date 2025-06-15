import logging
import asyncio # For async.sleep
from datetime import datetime
import random # For random.randint fallback in dice roll
import re # Import the 're' module for regex operations
from typing import Optional # Import Optional for type hinting
from apscheduler.jobstores.base import JobLookupError # Import JobLookupError for error handling

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton # Import ReplyKeyboardMarkup and KeyboardButton
from telegram.ext import ContextTypes # Only ContextTypes is needed here from telegram.ext

# Import necessary components from other modules
from game_logic import DiceGame, WAITING_FOR_BETS, GAME_CLOSED, GAME_OVER
from constants import global_data, HARDCODED_ADMINS, RESULT_EMOJIS, INITIAL_PLAYER_SCORE, ALLOWED_GROUP_IDS, get_chat_data_for_id


# Configure logging for this module (this will be overridden by main.py's config)
logger = logging.getLogger(__name__)

# Function to escape Markdown V2 special characters in a string
def escape_markdown_v2(text: str) -> str:
    """Escapes common Markdown V2 special characters."""
    # List of characters that need to be escaped in Markdown V2
    special_chars = '_*[]()~`>#+-=|{}.!'
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

def is_admin(chat_id, user_id):
    """
    Checks if a user is an administrator in a specific chat
    or if they are one of the hardcoded global administrators.
    """
    chat_specific_data = get_chat_data_for_id(chat_id)
    is_chat_admin = user_id in chat_specific_data["group_admins"]
    is_hardcoded_admin = user_id in HARDCODED_ADMINS
    logger.debug(f"is_admin: Checking admin status for user {user_id} in chat {chat_id}: is_chat_admin={is_chat_admin}, is_hardcoded_admin={is_hardcoded_admin}")
    return is_chat_admin or is_hardcoded_admin

async def update_group_admins(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Fetches the current list of administrators for a given chat
    and updates the global_data storage.
    Returns True on success, False on failure.
    """
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        admin_ids = [admin.user.id for admin in admins]
        
        chat_specific_data = get_chat_data_for_id(chat_id)
        chat_specific_data["group_admins"] = admin_ids # Update chat-specific admin list
        
        logger.info(f"update_group_admins: Updated admin list for chat {chat_id}: {admin_ids}")
        return True
    except Exception as e:
        logger.error(f"update_group_admins: Failed to get chat administrators for chat {chat_id}: {e}")
        return False

async def on_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles updates related to chat members, specifically when the bot
    is added to or removed from a group, or its status changes.
    """
    chat_member_update = update.chat_member
    if not chat_member_update:
        return

    # --- Group ID check for chat member updates ---
    if update.effective_chat.id not in ALLOWED_GROUP_IDS:
        logger.info(f"on_chat_member_update: Ignoring update from disallowed chat ID: {update.effective_chat.id}")
        # Optionally, send a message to the user/group that the bot is not authorized here.
        # await context.bot.send_message(update.effective_chat.id, "This bot is not authorized to run in this group.")
        return
    # --- END Group ID check ---

    if chat_member_update.new_chat_member.user.id == context.bot.id:
        chat_id = chat_member_update.chat.id
        new_status = chat_member_update.new_chat_member.status

        if new_status in ("member", "administrator"):
            logger.info(f"on_chat_member_update: Bot was added to chat {chat_id} or its status changed. New status: {new_status}.")
            if await update_group_admins(chat_id, context):
                custom_keyboard = [
                    [KeyboardButton("ငွေထည့်မည်"), KeyboardButton("ငွေထုတ်မည်")],
                    [KeyboardButton("Score"), KeyboardButton("Leaderboard"), KeyboardButton("ကစားနည်း")] # Added 'ကစားနည်း' button
                ]
                custom_keyboard_markup = ReplyKeyboardMarkup(custom_keyboard, resize_keyboard=True, one_time_keyboard=False)
                
                await context.bot.send_message(
                    chat_id,
                    "*အန်စာဂိမ်းဆော့ကစားတဲ့ Group လေးထဲမှ ကြိုဆိုပါတယ်ရှင့်🥳🥰*\n" # Feminine welcome
                    "*ကဲ.....ဂိမ်းလေးစဆော့လိုက်ကြဖို့ Admin တစ်ယောက်ကို ဂိမ်းစခိုင်းလိုက်တော့နော်.......လက်ကျန်ငွေကိုစစ်ဖို့ အခုပဲ /Score ကိုနှိပ်ပြီးစစ်ဆေးလိုက်တော့နော်...🥰*", # Feminine, casual
                    parse_mode="Markdown",
                    reply_markup=custom_keyboard_markup # Send the custom keyboard
                )
            else:
                await context.bot.send_message(
                    chat_id,
                    "*� ဟိုင်း! ကျွန်တော်က အန်စာတုံးဂိမ်းဘော့တ်ပါ။ Admin စာရင်းကို ရယူရာမှာ နည်းနည်းအခက်အခဲရှိနေလို့ပါ။ 'Chat Admins တွေကို ရယူဖို့' ခွင့်ပြုချက် ပေးထားလား စစ်ပေးပါဦးနော်။*", # More casual error
                    parse_mode="Markdown"
                )
        elif new_status == "left":
            logger.info(f"on_chat_member_update: Bot was removed from chat {chat_id}.")
            # Clean up all chat-specific data when the bot is removed from the group
            if chat_id in global_data["all_chat_data"]:
                del global_data["all_chat_data"][chat_id]
                logger.info(f"on_chat_member_update: Cleaned all_chat_data for chat {chat_id}.")
            if chat_id in context.chat_data:
                del context.chat_data[chat_id]
                logger.info(f"on_chat_member_update: Cleaned context.chat_data for chat {chat_id}.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /start command, sending a welcoming, more descriptive message
    and instructions to the user.
    """
    chat_id = update.effective_chat.id
    # --- Group ID check ---
    if chat_id not in ALLOWED_GROUP_IDS:
        logger.info(f"start: Ignoring command from disallowed chat ID: {chat_id}")
        await update.message.reply_text(f"*Sorry, this bot is not authorized to run in this group ({chat_id}). Please add it to an allowed group.*", parse_mode="Markdown")
        return
    # --- END Group ID check ---

    user_id = update.effective_user.id
    logger.info(f"start: Received /start command from user {user_id} in chat {chat_id}")

    custom_keyboard = [
        [KeyboardButton("ငွေထည့်မည်"), KeyboardButton("ငွေထုတ်မည်")],
        [KeyboardButton("Score"), KeyboardButton("Leaderboard"), KeyboardButton("ကစားနည်း")] # Added 'ကစားနည်း' button
    ]
    custom_keyboard_markup = ReplyKeyboardMarkup(custom_keyboard, resize_keyboard=True, one_time_keyboard=False)

    await update.message.reply_text(
        "*🌟🎲 အန်စာဂိမ်းဆော့ကစားတဲ့ Group လေးထဲမှ ကြိုဆိုပါတယ်ရှင့် 🎉🌟*\n\n" # Feminine welcome
        "*ကဲ.......ကစားပွဲလိုက်ရအောင်!!အန်စာတုံးဂိမ်းလေးရဲ့ စည်းမျဥ်းတွေက ဒီလိုပါရှင့်...🥳*\n\n"
        "*✨ ဂိမ်းစည်းမျဉ်းလေးတွေ:အန်စာတုံးနှစ်လုံးလှိမ့်မှာဖြစ်ပြီး အဲ့ဒီရလဒ်ကို ခန့်မှန်းရမှာပေါ့!* \n"
        "* 7 ထက်ငယ်ရယ် Small 7 ထက်ကြီးရင် Big 7 ဆိုရင်တော့ Lucky ဖြစ်ပြီး* \n"
        "* B နဲ့ S မှာလောင်းကြေးရဲ့ နှစ်ဆ ရမှာဖြစ်ပြီး*\n"
        "* Lucky မှာတော့ 5ဆကြီးများတောင် ရမှာနော်....😋🥰*\n\n"
        "*💰 ဘယ်လိုလောင်းမလဲ:*\n"
        "* -လောင်းကြေးထပ်ဖို့အတွက်ယခုပဲ* \n"
        "* - အကြီးကိုလောင်းဖို့ B 100 အသေးကိုလောင်းမယ်ဆိုရင် S 250 Lucky ကိုလောင်းဖို့အတွက်ကတော့ L 100*\n"
        "* (B/S/L အနောက်က နံပတ်တွေကမိမိရဲ့လောင်းကြေးဖြစ်တာကြောင့်လိုသလိုပြုပြင်နိုင်ပါတယ်ရှင်❤️) *\n\n"
        "*📊 သုံးလို့ရတဲ့ အမိန့်တွေ:*\n"
        "* - /score ကိုနှိပ်ပြီး မိမိရဲ့လက်ကျန်ငွေကိုစစ်ဆေးလို့ရတယ်နော်...🌷*\n"
        "* - /stats မိမိရဲ့အနိုင်အရှုံးမှတ်တမ်းအသေးစိတ်ကိုကြည့်ဖို့နော်....❤️*\n"
        "* - /leaderboard ကိုနှိပ်ပြီး ဒီGroupထဲက အနိုင်ရရှိမှုအများဆုံးကစားသမားတွေကို ကြည့်လိုက်ရအောင်.....🌷*\n"
        "* - /history: မကြာသေးခင်က ပွဲစဉ်ရလဒ်လေးတွေ ပြန်ကြည့်ဖို့ပါ။*\n\n"
        "*ကဲ... ကံတရားက သင့်ဘက်မှာ အမြဲရှိပါစေရှင့်!* 😉", # Feminine, casual tone
        parse_mode="Markdown",
        reply_markup=custom_keyboard_markup # Attach the custom keyboard
    )

async def _start_interactive_game_round(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """
    Helper function to initiate a single interactive game round.
    This logic is extracted to be reusable for both single /startdice and sequential games.
    """
    # --- Group ID check ---
    if chat_id not in ALLOWED_GROUP_IDS:
        logger.info(f"_start_interactive_game_round: Ignoring action from disallowed chat ID: {chat_id}")
        return
    # --- END Group ID check ---

    chat_specific_data = get_chat_data_for_id(chat_id)
    match_id = chat_specific_data["match_counter"] # Get chat-specific match counter
    chat_specific_data["match_counter"] += 1 # Increment chat-specific match counter
    
    game = DiceGame(match_id, chat_id)
    context.chat_data["game"] = game # Store the game instance in chat-specific data

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("BIG 🔼 (Total > 7)", callback_data="bet_big"),
            InlineKeyboardButton("SMALL 🔽 (Total < 7)", callback_data="bet_small"),
            InlineKeyboardButton("LUCKY 🍀 (Total = 7)", callback_data="bet_lucky")
        ]
    ])

    await context.bot.send_message(
        chat_id,
        f"*🔥 ပွဲစဉ် {match_id}: လောင်းကြေးတွေ ဖွင့်လိုက်ပါပြီရှင့်! 🔥*\n\n"
        "*💰  7 ထက်ငယ်ရင် Small 7 ထက်ကြီးရင် Big 7 ဆိုရင်တော့ Lucky ဖြစ်ပါတယ်*\n"
        "*ပွဲတစ်ပွဲတည်းမှာ မတူညီတဲ့ အကြီးအသေးတွေပေါ် အကြိမ်ပေါင်းများစွာ လောင်းကြေးထပ်လို့ရပါတယ်နော်။* \n\n"
        "*⏳ လောင်းကြေးတွေကို စက္ကန့် ၆၀ အတွင်း ပိတ်တော့မယ်နော်! မြန်မြန်လေး... ကံကြမ္မာက သင့်ကိုစောင့်နေတယ်။ ကံကောင်းပါစေရှင့်!* ✨",
        parse_mode="Markdown", reply_markup=keyboard
    )
    logger.info(f"_start_interactive_game_round: Match {match_id} started successfully in chat {chat_id}. Betting open for 60 seconds.")

    # Store the job object in chat_data to allow cancellation
    context.chat_data["close_bets_job"] = context.job_queue.run_once(
        close_bets_scheduled,
        60, # seconds from now
        chat_id=chat_id,
        data=game,
        name=f"close_bets_{chat_id}_{game.match_id}" # Give the job a name for easier identification/debugging
    )
    logger.info(f"_start_interactive_game_round: Job for close_bets_scheduled scheduled for match {match_id} in chat {chat_id}.")


async def _manage_game_sequence(context: ContextTypes.DEFAULT_TYPE):
    """
    This function is called by the job queue to start the next interactive game in a sequence.
    """
    chat_id = context.job.chat_id
    # --- Group ID check ---
    if chat_id not in ALLOWED_GROUP_IDS:
        logger.info(f"_manage_game_sequence: Ignoring action from disallowed chat ID: {chat_id}")
        return
    # --- END Group ID check ---
    
    num_matches_total = context.chat_data.get("num_matches_total")
    current_match_index = context.chat_data.get("current_match_index")

    if num_matches_total is None or current_match_index is None:
        logger.error(f"_manage_game_sequence: Missing sequence state in chat {chat_id}. Aborting sequence.")
        if "num_matches_total" in context.chat_data: del context.chat_data["num_matches_total"]
        if "current_match_index" in context.chat_data: del context.chat_data["current_match_index"]
        if "game" in context.chat_data: del context.chat_data["game"]
        # Clear next_game_job if sequence state is invalid, as no next game will be scheduled
        if "next_game_job" in context.chat_data:
            del context.chat_data["next_game_job"]
        return

    if current_match_index < num_matches_total:
        logger.info(f"_manage_game_sequence: Starting next game in sequence. Match {current_match_index + 1} of {num_matches_total} for chat {chat_id}.")
        context.chat_data["current_match_index"] += 1
        await _start_interactive_game_round(chat_id, context)
    else:
        logger.info(f"_manage_game_sequence: All {num_matches_total} matches in sequence completed for chat {chat_id}. Cleaning up.")
        if "num_matches_total" in context.chat_data:
            del context.chat_data["num_matches_total"]
        if "current_match_index" in context.chat_data:
            del context.chat_data["current_match_index"]
        if "game" in context.chat_data:
            del context.chat_data["game"]
        # Clear next_game_job here as sequence has finished
        if "next_game_job" in context.chat_data:
            del context.chat_data["next_game_job"]
        await context.bot.send_message(
            chat_id,
            "*🎉 ပွဲစဥ်တွေအားလုံး ပြီးဆုံးသွားပါပီရှင့် နောက်ထပ်ကစားပွဲများ စတင်ရန် Admin အားပြောပါရှင့်....❤️ 🎉*\n",
            parse_mode="Markdown"
        )


async def start_dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Starts a new dice game round or multiple automatic rounds.
    Only accessible by administrators.
    Usage: /startdice [number_of_matches]
    - If number_of_matches is provided, plays that many automatic matches.
    - If no number is provided, starts a single interactive betting round.
    """
    chat_id = update.effective_chat.id
    # --- Group ID check ---
    if chat_id not in ALLOWED_GROUP_IDS:
        logger.info(f"start_dice: Ignoring command from disallowed chat ID: {chat_id}")
        await update.message.reply_text(f"*Sorry, this bot is not authorized to run in this group ({chat_id}). Please add it to an allowed group.*", parse_mode="Markdown")
        return
    # --- END Group ID check ---

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    logger.info(f"start_dice: User {user_id} ({username}) attempting to start a game in chat {chat_id}")

    chat_specific_data = get_chat_data_for_id(chat_id)
    # Check if admin list for this specific chat is loaded or empty
    if not chat_specific_data["group_admins"]:
        logger.info(f"start_dice: Admin list for chat {chat_id} is empty or not loaded. Attempting to update it now.")
        if not await update_group_admins(chat_id, context):
            await update.message.reply_text(
                "*❌ Admin စာရင်းကို ရယူလို့မရသေးဘူးရှင့်။ Bot ကို 'Chat Admins တွေကို ရယူဖို့' ခွင့်ပြုချက် ပေးထားတာ သေချာလား စစ်ပေးပါဦးနော်။ ထပ်ပြီး ကြိုးစားကြည့်ပါဦး။*", # Feminine, casual error
                parse_mode="Markdown"
            )
            return

    if not is_admin(chat_id, user_id):
        logger.warning(f"start_dice: User {user_id} is not an admin and tried to start a game in chat {chat_id}.")
        return await update.message.reply_text("*❌ Admin တွေပဲ အန်စာတုံးဂိမ်းအသစ်ကို စလို့ရနိုင်တာပါနော်。*", parse_mode="Markdown") # Feminine, casual warning

    current_game = context.chat_data.get("game")
    if current_game and current_game.state != GAME_OVER:
        logger.warning(f"start_dice: Game already active in chat {chat_id}. State: {current_game.state}")
        return await update.message.reply_text("*⚠️ ဟိတ်! ဂိမ်းလေး စနေပြီရှင့်။ အရင်ပွဲလေး ပြီးသွားမှပဲ အသစ်စလို့ရမယ်နော်။ နည်းနည်းလေး စောင့်ပေးပါဦး။*", parse_mode="Markdown") # Feminine, casual waiting
    
    if context.chat_data.get("num_matches_total") is not None:
         return await update.message.reply_text("*⚠️ ပွဲစဉ်တွေ ဆက်တိုက် စထားပြီးပြီနော်။ လက်ရှိပွဲစဉ်တွေ ပြီးဆုံးသွားတဲ့အထိ စောင့်ပေးပါဦးနော်。*", parse_mode="Markdown") # Feminine, casual waiting


    num_matches_requested = 1

    if context.args:
        try:
            num_matches_requested = int(context.args[0])
            if num_matches_requested <= 0:
                return await update.message.reply_text("*❌ ပွဲအရေအတွက်က ဂဏန်းအပြုသဘော (positive integer) ဖြစ်ရမယ်နော်。*", parse_mode="Markdown") # Feminine, casual error
            elif num_matches_requested > 100: 
                return await update.message.reply_text("*❌ တစ်ခါတည်း အန်စာတုံးပွဲ ၁၀၀ ပွဲအထိပဲ စီစဉ်လို့ရပါသေးတယ်နော်。*", parse_mode="Markdown") # Feminine, casual limit
        except ValueError:
            await update.message.reply_text(
                "*ℹ️ `/startdice` အတွက် မှားယွင်းတဲ့ စာရိုက်ပုံလေး ဖြစ်နေတယ်ရှင့်။ တစ်ပွဲတည်းသော အန်စာတုံးပွဲကိုတော့ စတင်ပေးလိုက်ပါမယ်။*\n"
                "*အသုံးပြုပုံလေးကတော့: `/startdice` ဆိုရင် တစ်ပွဲစမယ်။ ဒါမှမဟုတ် `/startdice <အရေအတွက်>` ဆိုရင်တော့ ဆက်တိုက်ပွဲများစွာအတွက် သုံးလို့ရပါတယ်။*",
                parse_mode="Markdown"
            )
            num_matches_requested = 1


    if num_matches_requested > 1:
        context.chat_data["num_matches_total"] = num_matches_requested
        context.chat_data["current_match_index"] = 0

        await context.bot.send_message(
            chat_id,
            f"*🎮 ပွဲစဉ် {num_matches_requested} ပွဲ စပေးထားတယ်နော်! ဆော့ဖို့အတွက် အဆင်သင့်ပြင်ထားလိုက်တော့!*", # Feminine, casual countdown
            parse_mode="Markdown"
        )
        # Store the job object for sequence management
        context.chat_data["next_game_job"] = context.job_queue.run_once(
            _manage_game_sequence,
            2, # Small delay before first game starts
            chat_id=chat_id,
            name=f"sequence_start_{chat_id}"
        )
    else:
        await _start_interactive_game_round(chat_id, context)


async def close_bets_scheduled(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    game = job.data
    chat_id = game.chat_id

    # --- Group ID check ---
    if chat_id not in ALLOWED_GROUP_IDS:
        logger.info(f"close_bets_scheduled: Ignoring action from disallowed chat ID: {chat_id}")
        return
    # --- END Group ID check ---

    logger.info(f"close_bets_scheduled: Job called for match {game.match_id} in chat {chat_id}.")
    
    current_game_in_context = context.chat_data.get("game")
    # Also clear the close_bets_job after it has run
    if "close_bets_job" in context.chat_data:
        del context.chat_data["close_bets_job"]

    if current_game_in_context is None or current_game_in_context != game:
        logger.warning(f"close_bets_scheduled: Skipping action for match {game.match_id} in chat {chat_id} as game instance changed or no game. Current game: {current_game_in_context.match_id if current_game_in_context else 'None'}.")
        return

    game.state = GAME_CLOSED
    logger.info(f"close_bets_scheduled: Bets closed for match {game.match_id} in chat {chat_id}. State set to GAME_CLOSED.")
    
    bet_summary_lines = [
        f"*⏳ ပွဲစဉ် {game.match_id}: လောင်းကြေးတွေ ပိတ်လိုက်ပါပြီရှင့်! ⏳*\n", # Feminine, casual closing
        "*လက်ရှိလောင်းထားတာတွေကတော့:*\n"
    ]
    
    has_bets = False
    for bet_type_key, bets_dict in game.bets.items():
        if bets_dict:
            has_bets = True
            bet_summary_lines.append(f"* *{bet_type_key.upper()}* {RESULT_EMOJIS[bet_type_key]}:*")
            sorted_bets = sorted(bets_dict.items(), key=lambda item: item[1], reverse=True)
            for uid, amount in sorted_bets:
                player_info = get_chat_data_for_id(chat_id)["player_stats"].get(uid) # Use chat-specific player_stats
                # Use raw username for @mention, no escaping needed for Telegram
                username_display = player_info['username'] if player_info else f"User {uid}"
                bet_summary_lines.append(f"* → @{username_display}: {amount} ကျပ်*")
    
    if not has_bets:
        bet_summary_lines.append("*ဒီပွဲမှာ ဘယ်သူမှ လောင်းကြေးထပ်မထားကြပါဘူးရှင့်။ စိတ်မကောင်းစရာပဲနော်。*") # Feminine, casual empty bets

    bet_summary_lines.append("\n*အန်စာတုံးလေးတွေ လှိမ့်နေပြီနော်... ရင်ခုန်နေပြီလား!💥*") # Exciting
    
    try:
        logger.info(f"close_bets_scheduled: Attempting to send 'Bets closed and summary' message for match {game.match_id} to chat {chat_id}.")
        await context.bot.send_message(chat_id, "\n".join(bet_summary_lines), parse_mode="Markdown")
        logger.info(f"close_bets_scheduled: 'Bets closed and summary' message sent successfully for match {game.match_id}.")
    except Exception as e:
        logger.error(f"close_bets_scheduled: Error sending 'Bets closed' message for chat {chat_id}: {e}", exc_info=True)

    # Store the job object for roll and announce
    context.chat_data["roll_and_announce_job"] = context.job_queue.run_once(
        roll_and_announce_scheduled,
        10, # seconds from now
        chat_id=chat_id,
        data=game,
        name=f"roll_announce_{chat_id}_{game.match_id}"
    )
    logger.info(f"close_bets_scheduled: Job for roll_and_announce_scheduled set for 30 seconds for match {game.match_id} in chat {chat_id}.")
    logger.info(f"close_bets_scheduled: Function finished for match {game.match_id} in chat {chat_id}.")


async def roll_and_announce_scheduled(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    game = job.data
    chat_id = game.chat_id

    # --- Group ID check ---
    if chat_id not in ALLOWED_GROUP_IDS:
        logger.info(f"roll_and_announce_scheduled: Ignoring action from disallowed chat ID: {chat_id}")
        return
    # --- END Group ID check ---

    logger.info(f"roll_and_announce_scheduled: Job called for match {game.match_id} in chat {chat_id}.")
    
    current_game_in_context = context.chat_data.get("game")
    # Also clear the roll_and_announce_job after it has run
    if "roll_and_announce_job" in context.chat_data:
        del context.chat_data["roll_and_announce_job"]

    if current_game_in_context is not None and current_game_in_context != game and game.state != GAME_CLOSED:
         logger.warning(f"roll_and_announce_scheduled: Skipping action for match {game.match_id} in chat {chat_id} due to invalid state or game instance change. Current game: {current_game_in_context.match_id if current_game_in_context else 'None'}, Game state: {game.state}.")
         return
    if game.state == GAME_OVER:
        logger.warning(f"roll_and_announce_scheduled: Skipping action for match {game.match_id} as it's already GAME_OVER.")
        return
    
    game.state = GAME_OVER

    d1, d2 = 0, 0

    try:
        logger.info(f"roll_and_announce_scheduled: Sending first animated dice for match {game.match_id}.")
        dice_message_1 = await context.bot.send_dice(chat_id=chat_id)
        d1 = dice_message_1.dice.value
        logger.info(f"roll_and_announce_scheduled: First dice rolled: {d1}.")
        await asyncio.sleep(2)

        logger.info(f"roll_and_announce_scheduled: Sending second animated dice for match {game.match_id}.")
        dice_message_2 = await context.bot.send_dice(chat_id=chat_id)
        d2 = dice_message_2.dice.value
        logger.info(f"roll_and_announce_scheduled: Second dice rolled: {d2}.")
        await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"roll_and_announce_scheduled: Error sending animated dice for chat {chat_id}: {e}", exc_info=True)
        logger.warning("Falling back to random dice values due to Telegram API error.")
        d1, d2 = random.randint(1,6), random.randint(1,6)

    game.result = d1 + d2
    winning_type, multiplier, individual_payouts = game.payout(chat_id)

    result_message_text = (
        f"*🎉 ပွဲစဉ် {game.match_id} ရဲ့ အနိုင် အရှုံး ရလဒ်တွေ ထွက်ပေါ်လာပါပြီရှင့်! 🎉*\n"
        f"*🎲 ရလဒ်ကတော့: {d1} + {d2} = {d1 + d2} ဖြစ်ပါတယ်!*\n"
        f"*🏆 အနိုင်ရလောင်းကြေးက: {winning_type.upper()} {RESULT_EMOJIS[winning_type]} ပေါ် လောင်းထားသူတွေ {multiplier} ဆ ပြန်ရမှာနော်*!\n\n"
        "*အနိုင်ရရှိသူတွေကတော့:*\n"
    )
    
    chat_specific_data = get_chat_data_for_id(chat_id)
    stats = chat_specific_data["player_stats"] # Use chat-specific player_stats
    
    if individual_payouts:
        payout_lines = []
        sorted_payouts = sorted(
            individual_payouts.items(), 
            key=lambda item: (item[1], stats.get(item[0], {}).get('username', f"User {item[0]}")), 
            reverse=True
        )

        for uid, winnings in sorted_payouts:
            player_info = stats.get(uid)
            if player_info:
                # Use raw username for @mention, no escaping needed for Telegram
                username_display = player_info['username']
                payout_lines.append(f"* ✨ @{username_display}: +{winnings} ကျပ် ရရှိပြီး လက်ကျန်ငွေ: *{player_info['score']}*!*")
            else:
                payout_lines.append(f"* ✨ User ID {uid}: +{winnings} ကျပ် ရရှိခဲ့ပါတယ်!*")
        result_message_text += "\n".join(payout_lines)
    else:
        result_message_text += " *ဒီတစ်ပွဲမှာတော့ ဘယ်သူမှ ကံမကောင်းခဲ့ဘူးရှင့်! စိတ်မပျက်ပါနဲ့၊ နောက်ပွဲမှာ ပိုက်ဆံတွေ ပုံအောလိုက်တော့နော်!* 💔"

    lost_players = []
    for uid in game.participants:
        if uid not in individual_payouts:
            player_info = stats.get(uid)
            if player_info:
                # Use raw username for @mention, no escaping needed for Telegram
                username_display = player_info['username']
                lost_players.append(f"* 💀 @{username_display} (လက်ကျန်ငွေ: {player_info['score']}) - ကံမကောင်းခဲ့ဘူးရှင့်!*")
            else:
                lost_players.append(f"* 💀 User ID {uid} (ရမှတ်မတွေ့ပါ) - ဘယ်သူဘယ်ဝါမှန်းမသိဘဲ ရှုံးသွားတာလားရှင့်!*")

    if lost_players:
        result_message_text += "\n\n*ဒီပွဲမှာ ကံဆိုးခဲ့ကြသူတွေကတော့:*\n"
        result_message_text += "\n".join(lost_players)


    try:
        logger.info(f"roll_and_announce_scheduled: Attempting to send 'Results' message for match {game.match_id} to chat {chat_id}.")
        await context.bot.send_message(chat_id, result_message_text, parse_mode="Markdown")
        logger.info(f"roll_and_announce_scheduled: 'Results' message sent successfully for match {game.match_id}.")
    except Exception as e:
        logger.error(f"roll_and_announce_scheduled: Error sending 'Results' message for chat {chat_id}: {e}", exc_info=True)

    # --- UPDATED: Idle match logic ---
    chat_specific_data = get_chat_data_for_id(chat_id)
    
    if not game.participants: # No bets were placed in this match
        chat_specific_data["consecutive_idle_matches"] += 1
        logger.info(f"No participants in match {game.match_id}. Consecutive idle matches for chat {chat_id}: {chat_specific_data['consecutive_idle_matches']}")
    else:
        chat_specific_data["consecutive_idle_matches"] = 0 # Reset if bets were placed
        logger.info(f"Participants found in match {game.match_id}. Resetting idle counter for chat {chat_id}.")

    if chat_specific_data["consecutive_idle_matches"] >= 5:
        logger.info(f"Stopping game sequence in chat {chat_id} due to 3 consecutive idle matches.")
        await context.bot.send_message(
            chat_id,
            "*😴 ဂိမ်းရပ်လိုက်ပါပြီရှင့်! �*\n\n"
            "*ဆက်တိုက် ၅ ပွဲဆက် ဘယ်သူမှ လောင်းကြေးထပ်တာ မတွေ့ရလို့ ဂိမ်းကို ခဏရပ်လိုက်ပါပြီရှင့်။*"
            "*ပြန်ကစားချင်ရင် Admin ကိုပြောပေးပါရှင့်။*",
            parse_mode="Markdown"
        )
        # Force stop the game: clear game state and pending jobs
        context.chat_data.pop("game", None)
        context.chat_data.pop("num_matches_total", None)
        context.chat_data.pop("current_match_index", None)
        
        # Cancel any pending sequence/next game jobs
        if "next_game_job" in context.chat_data:
            try:
                context.chat_data["next_game_job"].schedule_removal()
            except JobLookupError:
                logger.warning(f"roll_and_announce_scheduled: JobLookupError for 'next_game_job' during auto-stop for chat {chat_id}.")
            finally:
                del context.chat_data["next_game_job"]
        
        # Ensure other scheduled jobs related to this specific match are also cleared
        if "close_bets_job" in context.chat_data:
            try:
                context.chat_data["close_bets_job"].schedule_removal()
            except JobLookupError:
                logger.warning(f"roll_and_announce_scheduled: JobLookupError for 'close_bets_job' during auto-stop for chat {chat_id}.")
            finally:
                del context.chat_data["close_bets_job"]
        
        # roll_and_announce_job is already popped at the start of this function.
        
        return # Stop further processing for this match, no next game is scheduled
    # --- END UPDATED ---

    if context.chat_data.get("num_matches_total") is not None:
        logger.info(f"roll_and_announce_scheduled: Multi-match sequence active. Scheduling next game in sequence for chat {chat_id}.")
        # Store the job object for the next game in sequence
        context.chat_data["next_game_job"] = context.job_queue.run_once(
            _manage_game_sequence,
            5, # 5-second delay before starting the next game
            chat_id=chat_id,
            name=f"next_game_sequence_{chat_id}"
        )
    else:
        if "game" in context.chat_data:
            del context.chat_data["game"]
            logger.info(f"roll_and_announce_scheduled: Cleaned up game data for chat {chat_id} after single interactive match {game.match_id}.")
        # Also clear next_game_job if it was part of a sequence that just ended
        if "next_game_job" in context.chat_data:
            del context.chat_data["next_game_job"]

    logger.info(f"roll_and_announce_scheduled: Function finished for match {game.match_id} in chat {chat_id}.")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles inline keyboard button presses for placing bets.
    """
    chat_id = update.effective_chat.id
    # --- Group ID check ---
    if chat_id not in ALLOWED_GROUP_IDS:
        logger.info(f"button_callback: Ignoring callback from disallowed chat ID: {chat_id}")
        await update.callback_query.answer(f"*Sorry, this bot is not authorized to run in this group ({chat_id}).*", show_alert=True)
        return
    # --- END Group ID check ---

    query = update.callback_query
    await query.answer() 
    
    data = query.data
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name
    
    # Do NOT escape username for @mentions. Telegram handles it.
    # username_escaped = escape_markdown_v2(username) # REMOVED

    game = context.chat_data.get("game")
    
    if not game:
        logger.info(f"button_callback: User {user_id} ({username}) tried to bet via button but no game active in chat {chat_id}.")
        return await query.message.reply_text(
            f"*⚠️ @{username} ရေ၊ အန်စာတုံးဂိမ်းက မစသေးဘူးရှင့်။ Admin တစ်ယောက်က စပေးမှ ရမှာနော်。", # Feminine, casual no game
            parse_mode="Markdown"
        )
    
    if game.state != WAITING_FOR_BETS:
        logger.info(f"button_callback: User {user_id} ({username}) tried to bet via button but betting is closed for match {game.match_id} in chat {chat_id}. State: {game.state}")
        return await query.message.reply_text(
            f"*⚠️ @{username} ရေ၊ ဒီဂိမ်းအတွက် လောင်းကြေးတွေ ပိတ်လိုက်ပြီရှင့်။ နောက်ပွဲကမှ ထပ်လောင်းလို့ရမယ်နော်!*", # Feminine, casual closed bets
            parse_mode="Markdown"
        )

    bet_type = data.split("_")[1]
    
    success, response_message = game.place_bet(user_id, username, bet_type, 100)
    
    # --- UPDATED: Reset idle counter on successful bet ---
    if success:
        chat_specific_data = get_chat_data_for_id(chat_id)
        chat_specific_data["consecutive_idle_matches"] = 0 
        logger.info(f"button_callback: Bet placed by {user_id}, resetting idle counter for chat {chat_id}.")
    # --- END UPDATED ---

    await query.message.reply_text(response_message, parse_mode="Markdown")
    logger.info(f"button_callback: User {user_id} placed bet via button: {bet_type} (100 pts) in chat {chat_id}. Success: {success}")


async def handle_bet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles text-based bet commands (e.g., 'b 500', 's 200', 'l 100', 'big 50', 'lucky50').
    It now expects a single bet per message and will not be chatty on non-bet text.
    """
    chat_id = update.effective_chat.id
    # --- Group ID check ---
    if chat_id not in ALLOWED_GROUP_IDS:
        logger.info(f"handle_bet: Ignoring message from disallowed chat ID: {chat_id}")
        return # Do not send a reply to disallowed groups for non-command messages
    # --- END Group ID check ---

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    message_text = update.message.text.strip()
    
    # Do NOT escape username for @mentions. Telegram handles it.
    # username_escaped = escape_markdown_v2(username) # REMOVED

    logger.info(f"handle_bet: User {user_id} ({username}) attempting to place text bet: '{message_text}' in chat {chat_id}")

    game = context.chat_data.get("game")
    if not game:
        logger.info(f"handle_bet: User {user_id} tried to place text bet but no game active in chat {chat_id}.")
        return await update.message.reply_text(
            f"*⚠️ @{username} ရေ၊ အန်စာတုံးဂိမ်းက မစသေးဘူးရှင့်။ Admin တစ်ယောက်က စပေးမှ ရမှာနော်。", # Feminine, casual no game
            parse_mode="Markdown"
        )
    
    if game.state != WAITING_FOR_BETS:
        logger.info(f"handle_bet: User {user_id} ({username}) tried to place text bet but betting is closed for match {game.match_id} in chat {chat_id}. State: {game.state}")
        return await update.message.reply_text(
            f"*⚠️ @{username} ရေ၊ ဒီဂိမ်းအတွက် လောင်းကြေးတွေ ပိတ်လိုက်ပြီရှင့်။ နောက်ပွဲကမှ ထပ်လောင်းလို့ရမယ်နော်!*", # Feminine, casual closed bets
            parse_mode="Markdown"
        )

    # Simplified regex for single bet parsing
    bet_match = re.match(r"^(big|b|small|s|lucky|l)\s*(\d+)$", message_text, re.IGNORECASE)

    if not bet_match:
        logger.warning(f"handle_bet: Invalid bet format for user {user_id} in message: '{message_text}' in chat {chat_id}.")
        return await update.message.reply_text(
            f"*❌ @{username} ရေ၊ လောင်းကြေးထပ်တာ ပုံစံလေး မှားနေတယ်ရှင့်။ ကျေးဇူးပြုပြီး: `big 500`, `small 100`, `lucky 250` စသည်ဖြင့် ရိုက်ပေးနော်။*\n"
            "*ခလုတ်တွေ နှိပ်ပြီးတော့လည်း (မူရင်း ၁၀၀ မှတ်) လောင်းလို့ရတယ်နော်!*",
            parse_mode="Markdown"
        )
    
    bet_type_str, amount_str = bet_match.groups()
    
    bet_types_map = {
        "b": "big", "big": "big",
        "s": "small", "small": "small",
        "l": "lucky", "lucky": "lucky"
    }
    bet_type = bet_types_map.get(bet_type_str.lower())
    
    try:
        amount = int(amount_str)
    except ValueError:
        logger.error(f"handle_bet: Failed to convert bet amount to integer from user {user_id}: '{amount_str}' in chat {chat_id}.")
        # This error should ideally be caught by the regex already (digits only)
        return await update.message.reply_text(f"*❌ @{username} ရေ၊ လောင်းကြေးပမာဏက English ဂဏန်းဖြစ်ရမှာနော်。", parse_mode="Markdown") # Feminine, casual error

    success, msg = game.place_bet(user_id, username, bet_type, amount)
    
    # --- UPDATED: Reset idle counter on successful bet ---
    if success:
        chat_specific_data = get_chat_data_for_id(chat_id)
        chat_specific_data["consecutive_idle_matches"] = 0
        logger.info(f"handle_bet: Bet placed by {user_id}, resetting idle counter for chat {chat_id}.")
    # --- END UPDATED ---

    await update.message.reply_text(msg, parse_mode="Markdown")
    logger.info(f"handle_bet: User {user_id} placed bet: {bet_type} {amount} pts in chat {chat_id}. Success: {success}")


async def show_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in ALLOWED_GROUP_IDS:
        logger.info(f"show_score: Ignoring action from disallowed chat ID: {chat_id}")
        if update.message:
            await update.message.reply_text(f"*Sorry, this bot is not authorized to run in this group ({chat_id}). Please add it to an allowed group.*", parse_mode="Markdown")
        return

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    logger.info(f"show_score: User {user_id} ({username}) requested score in chat {chat_id}")

    chat_specific_data = get_chat_data_for_id(chat_id)
    player_stats = chat_specific_data["player_stats"]

    user_data = player_stats.get(user_id)

    if user_data:
        # Get and escape necessary data
        escaped_username = escape_markdown_v2(user_data['username']) # Escape username
        escaped_score = escape_markdown_v2(str(user_data['score'])) # Escape score (convert to string first)

        score_message = (
            f"*@{username}* ရဲ့ လက်ကျန်ငွေကတော့ *{escaped_score}* ကျပ် ဖြစ်ပါတယ်ရှင့်! 💰"
        )
    else:
        score_message = (
            f"*@{username}* ရေ၊ မှတ်တမ်းမတွေ့ရသေးဘူးနော်။ ဂိမ်းစကစားပြီးမှ ပြန်စစ်ကြည့်ပါဦးရှင့်!"
        )

    await (update.message or update.callback_query.message).reply_text(
        score_message,
        parse_mode="Markdown"
    )

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Displays detailed personal game statistics for the user,
    including points, games played, wins, losses, win rate, and last active time.
    """
    chat_id = update.effective_chat.id
    # --- Group ID check ---
    if chat_id not in ALLOWED_GROUP_IDS:
        logger.info(f"show_stats: Ignoring command from disallowed chat ID: {chat_id}")
        await update.message.reply_text(f"*Sorry, this bot is not authorized to run in this group ({chat_id}). Please add it to an allowed group.*", parse_mode="Markdown")
        return
    # --- END Group ID check ---

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    logger.info(f"show_stats: User {user_id} ({username}) requested detailed stats in chat {chat_id}")

    chat_specific_data = get_chat_data_for_id(chat_id)
    player_stats = chat_specific_data["player_stats"].get(user_id) # Use chat-specific player_stats

    if player_stats:
        total_games = player_stats['wins'] + player_stats['losses']
        win_rate = 0.0 
        if total_games > 0:
            win_rate = (player_stats['wins'] / total_games) * 100

        # Use raw username for @mention, no escaping needed for Telegram
        username_display = player_stats['username']

        await update.message.reply_text(
            f"*👤 @{username_display}* *၏ စုစု‌ပေါင်းအခြေအနေ:*\n"
            f"* 💰 လက်ကျန်ငွေ*: *{player_stats['score']} ကျပ်*\n"
            f"* ကစားခဲ့တဲ့ပွဲ*: *{total_games} ပွဲ*\n"
            f"* ✅ အနိုင်*: *{player_stats['wins']} ပွဲ*\n"
            f"* ❌ အရှုံး*: *{player_stats['losses']} ပွဲ*\n"
            f"* win rate*: *{win_rate:.1f}%*\n"
            f"* နောက်ဆုံးကစားချိန်*: *{player_stats['last_active'].strftime('%Y-%m-%d %H:%M')}*",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("*ℹ️ ဟိတ်! သင့်အတွက် အချက်အလက်တွေ မတွေ့ရသေးဘူးနော်။ ဂိမ်းစပြီး ကစားလိုက်ပါဦး၊ ပြီးမှ မှတ်တမ်းတင်ပေးမယ်ရှင့်!*", parse_mode="Markdown") # Feminine, casual no stats

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Displays the top 10 players by score in the current chat.
    Filters out players who haven't made any bets (still on initial 1000 points).
    """
    chat_id = update.effective_chat.id
    # --- Group ID check ---
    if chat_id not in ALLOWED_GROUP_IDS:
        logger.info(f"leaderboard: Ignoring command from disallowed chat ID: {chat_id}")
        await update.message.reply_text(f"*Sorry, this bot is not authorized to run in this group ({chat_id}). Please add it to an allowed group.*", parse_mode="Markdown")
        return
    # --- END Group ID check ---

    logger.info(f"leaderboard: User {update.effective_user.id} requested leaderboard in chat {chat_id}")

    chat_specific_data = get_chat_data_for_id(chat_id)
    stats_for_chat = chat_specific_data["player_stats"] # Use chat-specific player_stats
    
    active_players = [
        p for p in stats_for_chat.values()
        if p["wins"] > 0 or p["losses"] > 0 or p["score"] != INITIAL_PLAYER_SCORE
    ]
    top_players = sorted(active_players, key=lambda x: x["score"], reverse=True)[:10]

    if not top_players:
        return await update.message.reply_text("*ℹ️ ဒီ Chat ထဲမှာတော့ မှတ်တမ်းတင်ထားတဲ့ ကစားသမားတွေ မရှိသေးဘူးရှင့်။ ဂိမ်းစပြီး လောင်းကြေးထပ်လိုက်မှပဲ အမှတ်တွေတက်လာမှာနော်。*", parse_mode="Markdown") # Feminine, casual no players
    
    message_lines = ["*🏆 ဒီ Group ထဲက ထိပ်တန်းအနိုင်ရရှိသူတွေကတော့:*\n"] # Feminine, casual title
    for i, player in enumerate(top_players):
        # Use raw username for @mention, no escaping needed for Telegram
        username_display = player['username']
        message_lines.append(f"*{i+1}. @{username_display}: {player['score']}ကျပ်*")
    
    await update.message.reply_text("\n".join(message_lines), parse_mode="Markdown")


async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Displays the recent match history for the current chat (last 5 matches).
    """
    chat_id = update.effective_chat.id
    # --- Group ID check ---
    if chat_id not in ALLOWED_GROUP_IDS:
        logger.info(f"history: Ignoring command from disallowed chat ID: {chat_id}")
        await update.message.reply_text(f"*Sorry, this bot is not authorized to run in this group ({chat_id}). Please add it to an allowed group.*", parse_mode="Markdown")
        return
    # --- END Group ID check ---

    logger.info(f"history: User {update.effective_user.id} requested match history in chat {chat_id}")

    chat_specific_data = get_chat_data_for_id(chat_id)
    match_history_for_chat = chat_specific_data["match_history"] # Use chat-specific match_history
    
    if not match_history_for_chat:
        return await update.message.reply_text("*ℹ️ ဒီ Chat ထဲမှာတော့ ပွဲမှတ်တမ်းတွေ မရှိသေးဘူးရှင့်။ မှတ်တမ်းတွေ ဖန်တီးချင်ရင် ဂိမ်းတွေ များများ ကစားပါဦးနော်。", parse_mode="Markdown") # Feminine, casual no history
    
    message_lines = ["*📜 မကြာသေးခင်က ပြီးသွားတဲ့ နောက်ဆုံး ၅ ပွဲ ကတော့:*\n"] # Feminine, casual title
    for match in match_history_for_chat[-5:][::-1]: 
        timestamp_str = match['timestamp'].strftime('%Y-%m-%d %H:%M')
        # --- UPDATED: Comprehensive Markdown V2 escaping for winner_display (not username) ---
        winner_display = escape_markdown_v2(match['winner'].upper())
        # --- END UPDATED ---
        winner_emoji = RESULT_EMOJIS.get(match['winner'], '')
        
        message_lines.append(
            f"* • ပွဲစဉ် {match['match_id']} | ရလဒ်: {match['result']} ({winner_display} {winner_emoji}) | ပါဝင်ကစားသူ: {match['participants']} ယောက် | အချိန်*: {timestamp_str}*"
        )
    
    await update.message.reply_text("\n".join(message_lines), parse_mode="Markdown")

async def adjust_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin command to adjust a player's score.
    Usage:
    - Reply to a user's message: /adjustscore <amount>
    - Direct input (numeric ID): /adjustscore <user_id> <amount>
    - Direct input (@username): /adjustscore @username <amount>
    """
    chat_id = update.effective_chat.id
    # --- Group ID check ---
    if chat_id not in ALLOWED_GROUP_IDS:
        logger.info(f"adjust_score: Ignoring command from disallowed chat ID: {chat_id}")
        await update.message.reply_text(f"*Sorry, this bot is not authorized to run in this group ({chat_id}). Please add it to an allowed group.*", parse_mode="Markdown")
        return
    # --- END Group ID check ---

    requester_user_id = update.effective_user.id
    logger.info(f"adjust_score: User {requester_user_id} attempting to adjust score in chat {chat_id}")

    if not is_admin(chat_id, requester_user_id):
        logger.warning(f"adjust_score: User {requester_user_id} is not an admin and tried to adjust score in chat {chat_id}.")
        return await update.message.reply_text("*❌ Admin တွေပဲ ကစားသမားတွေကို ငွေထည့်ပေးလို့ရတာနော်。", parse_mode="Markdown") # Feminine, casual admin check

    target_user_id = None
    amount_to_adjust = None
    target_username_display = None # This will hold the *unescaped* username for display

    if update.message.reply_to_message:
        if not context.args or len(context.args) != 1:
            return await update.message.reply_text(
                "*❌ ပြန်ဖြေပြီး သုံးတာ ပုံစံလေး မှားနေတယ်ရှင့်။ ကျေးဇူးပြုပြီး: `/adjustscore <ပမာဏ>` ကိုပဲ သုံးပေးပါနော်。*\n"
                "*ဥပမာ- အသုံးပြုသူရဲ့ မက်ဆေ့ချ်ကို ပြန်ဖြေပြီး `/adjustscore 500` (၅၀၀ မှတ် ထည့်ဖို့ပေါ့) လို့ ရိုက်လိုက်ပါ။*",
                parse_mode="Markdown"
            )
        
        target_user_id = update.message.reply_to_message.from_user.id
        target_username_display = update.message.reply_to_message.from_user.username or update.message.reply_to_message.from_user.first_name
        
        try:
            amount_to_adjust = int(context.args[0])
        except ValueError:
            return await update.message.reply_text(
                "*❌ ပမာဏက ဂဏန်းဖြစ်ရမှာနော်။ မှားနေတယ်ရှင့်。\n"
                "*ဥပမာ- အသုံးပြုသူရဲ့ မက်ဆေ့ချ်ကို ပြန်ဖြေပြီး `/adjustscore 500` လို့ ရိုက်လိုက်ပါ။*",
                parse_mode="Markdown"
            )

    elif context.args and len(context.args) >= 2:
        first_arg = context.args[0]
        try:
            amount_to_adjust = int(context.args[1])
        except ValueError:
            return await update.message.reply_text(
                "*❌ ပမာဏက ဂဏန်းဖြစ်ရမှာနော်။ မှားနေတယ်ရှင့်。\n"
                "*ဥပမာ- `/adjustscore 123456789 500` ဒါမှမဟုတ် `/adjustscore @someuser 100` စသည်ဖြင့် သုံးပါနော်。",
                parse_mode="Markdown"
            )

        chat_specific_data = get_chat_data_for_id(chat_id)
        
        if first_arg.startswith('@'):
            mentioned_username = first_arg[1:]
            
            # Try to find user in bot's in-memory player_stats first
            for uid, player_info in chat_specific_data["player_stats"].items():
                if player_info.get("username", "").lower() == mentioned_username.lower():
                    target_user_id = uid
                    target_username_display = player_info.get("username")
                    break
            
            if target_user_id is None: # User not found in local player_stats by username
                try:
                    # Do not escape mentioned_username for @mention in error message
                    return await update.message.reply_text(
                        f"*❌ အသုံးပြုသူ '@{mentioned_username}' ကို ဒီ Chat ရဲ့ ဂိမ်းအချက်အလက်တွေထဲမှာ ရှာမတွေ့ဘူးရှင့်။ သူတို့က Bot နဲ့ ဒီ Chat မှာ အရင်က ဆော့ဖူးမှ ရမှာနော်။ ဒါမှမဟုတ် သူတို့ပို့ထားတဲ့ မက်ဆေ့ချ်ကို ပြန်ဖြေပြီး သုံးတာ ဒါမှမဟုတ် သူတို့ရဲ့ User ID ကို ဂဏန်းနဲ့ ရိုက်ပြီး သုံးကြည့်ပါလား。",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"adjust_score: Attempt to fetch user {mentioned_username} by username via get_chat_member failed: {e}")
                    pass # Continue to the check below for None target_user_id
        else: # Numeric user ID provided
            try:
                target_user_id = int(first_arg)
            except ValueError:
                return await update.message.reply_text(
                    "*❌ User ID ဒါမှမဟုတ် ပမာဏက မှားနေတယ်ရှင့်။ ကျေးဇူးပြုပြီး: `/adjustscore <user_id>` ဒါမှမဟုတ် `/adjustscore @username <ပမာဏ>` ကိုသုံးပေးနော်。\n"
                    "*ဥပမာ- `/adjustscore 123456789 500` ဒါမှမဟုတ် `/adjustscore @someuser 100`。",
                    parse_mode="Markdown"
                )
            
    else: # Neither reply nor valid direct args
        return await update.message.reply_text(
            "*❌ သုံးတဲ့ပုံစံလေး မှားနေတယ်နော်။ ကျေးဇူးပြုပြီး အောက်က ပုံစံတွေထဲက တစ်ခုခုကို သုံးပေးပါ:*\n"
            "* - အသုံးပြုသူရဲ့ မက်ဆေ့ချ်ကို ပြန်ဖြေပြီး: `/adjustscore <ပမာဏ>`*\n"
            "* - တိုက်ရိုက်ရိုက်ထည့်ချင်ရင်: `/adjustscore <user_id>`*\n"
            "* - Username နဲ့ ရိုက်ထည့်ချင်ရင်: `/adjustscore @username <ပမာဏ>`*\n"
            "*ဥပမာ- `/adjustscore 123456789 500` ဒါမှမဟုတ် `/adjustscore @someuser 100`。",
            parse_mode="Markdown"
        )

    if target_user_id is None or amount_to_adjust is None:
        logger.error(f"adjust_score: Logic error: target_user_id ({target_user_id}) or amount_to_adjust ({amount_to_adjust}) is None after initial parsing. update_message: {update.message.text}")
        return await update.message.reply_text("*❌ မထင်မှတ်ထားတဲ့ ပြဿနာလေး ဖြစ်သွားတယ်ရှင့်။ ကျေးဇူးပြုပြီး ထပ်ကြိုးစားကြည့်ပါဦးနော် ဒါမှမဟုတ် Admin ကို အကူအညီတောင်းပါ။*", parse_mode="Markdown") # Feminine, casual error

    chat_specific_data = get_chat_data_for_id(chat_id)
    player_stats_for_chat = chat_specific_data["player_stats"]
    target_player_stats = player_stats_for_chat.get(target_user_id)

    if not target_player_stats:
        try:
            chat_member = await context.bot.get_chat_member(chat_id, target_user_id)
            fetched_username = chat_member.user.username or chat_member.user.first_name
            # Do not escape fetched_username for @mention
            
            player_stats_for_chat[target_user_id] = {
                "username": fetched_username,
                "score": INITIAL_PLAYER_SCORE,
                "wins": 0,
                "losses": 0,
                "last_active": datetime.now()
            }
            target_player_stats = player_stats_for_chat[target_user_id]
            if target_username_display is None:
                target_username_display = fetched_username 
        except Exception as e:
            logger.error(f"adjust_score: Failed to fetch user details for {target_user_id} in chat {chat_id}: {e}", exc_info=True)
            return await update.message.reply_text(
                f"*❌ User ID `{target_user_id}` နဲ့ ကစားသမားကို ဒီ Chat ထဲမှာ ရှာမတွေ့ဘူးရှင့်။ Telegram က သူတို့ရဲ့ အချက်အလက်တွေကို ရယူလို့မရလို့ပါ။ သူတို့က ဒီ Chat ရဲ့ အဖွဲ့ဝင် ဟုတ်မဟုတ် သေချာအောင် စစ်ပေးပါဦးနော် ဒါမှမဟုတ် သူတို့ရဲ့ မက်ဆေ့ချ်တစ်ခုကို ပြန်ဖြေကြည့်ပါ။*",
                parse_mode="Markdown"
            )
            
    if target_username_display is None:
        target_username_display = target_player_stats.get('username', f"User {target_user_id}")

    old_score = target_player_stats['score']
    target_player_stats['score'] += amount_to_adjust
    target_player_stats['last_active'] = datetime.now() 
    new_score = target_player_stats['score']

    # Use raw target_username_display for @mention, no escaping needed for Telegram
    await update.message.reply_text(
        f"*✅ @{target_username_display} (ID: `{target_user_id}`) ရဲ့ Wallet ကို {amount_to_adjust} ကျပ် ပြောင်းလိုက်ပါပြီရှင့်*\n"
        f"*Old Wallet: {old_score} ကျပ် | New Wallet: {new_score} ကျပ်*",
        parse_mode="Markdown"
    )
    logger.info(f"adjust_score: User {requester_user_id} adjusted score for {target_user_id} in chat {chat_id} by {amount_to_adjust}. New score: {new_score}")

async def check_user_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin command to check a specific player's score and stats.
    Usage:
    - Reply to a user's message: /checkscore
    - Direct input (numeric ID): /checkscore <user_id>
    - Direct input (@username): /checkscore @username
    """
    chat_id = update.effective_chat.id
    # --- Group ID check ---
    if chat_id not in ALLOWED_GROUP_IDS:
        logger.info(f"check_user_score: Ignoring command from disallowed chat ID: {chat_id}")
        await update.message.reply_text(f"*Sorry, this bot is not authorized to run in this group ({chat_id}). Please add it to an allowed group.*", parse_mode="Markdown")
        return
    # --- END Group ID check ---

    requester_user_id = update.effective_user.id
    logger.info(f"check_user_score: User {requester_user_id} attempting to check score in chat {chat_id}")

    if not is_admin(chat_id, requester_user_id):
        logger.warning(f"check_user_score: User {requester_user_id} is not an admin and tried to check score in chat {chat_id}.")
        return await update.message.reply_text("*❌ Admin တွေပဲ တခြားကစားသမားတွေရဲ့ Walletကို စစ်ဆေးကြည့်လို့ရတာနော်。", parse_mode="Markdown") # Feminine, casual admin check

    target_user_id = None
    target_username_display = None # This will hold the *unescaped* username for display

    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
        target_username_display = update.message.reply_to_message.from_user.username or update.message.reply_to_message.from_user.first_name
        logger.info(f"check_user_score: Admin {requester_user_id} checking score by reply for user {target_user_id}.")
    elif context.args and len(context.args) == 1:
        first_arg = context.args[0]
        
        if first_arg.startswith('@'):
            mentioned_username = first_arg[1:]
            
            chat_specific_data = get_chat_data_for_id(chat_id)
            # Try to find user in bot's in-memory player_stats first
            for uid, player_info in chat_specific_data["player_stats"].items():
                if player_info.get("username", "").lower() == mentioned_username.lower():
                    target_user_id = uid
                    target_username_display = player_info.get("username")
                    break
            
            if target_user_id is None: # User not found in local player_stats by username
                try:
                    # Do not escape mentioned_username for @mention in error message
                    return await update.message.reply_text(
                        f"*❌ အသုံးပြုသူ '@{mentioned_username}' ကို ဒီ Chat ရဲ့ ဂိမ်းအချက်အလက်တွေထဲမှာ ရှာမတွေ့ဘူးရှင့်။ သူတို့က Bot နဲ့ ဒီ Chat မှာ အရင်က ဆော့ဖူးမှ ရမှာနော်။ ဒါမှမဟုတ် သူတို့ပို့ထားတဲ့ မက်ဆေ့ချ်ကို ပြန်ဖြေပြီး သုံးတာ ဒါမှမဟုတ် သူတို့ရဲ့ User ID ကို ဂဏန်းနဲ့ ရိုက်ပြီး သုံးကြည့်ပါလား。",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.warning(f"check_user_score: Attempt to fetch user {mentioned_username} by username via get_chat_member failed: {e}")
                    pass # Continue to the check below for None target_user_id
        else: # Numeric user ID provided
            try:
                target_user_id = int(first_arg)
                logger.info(f"check_user_score: Admin {requester_user_id} checking score by numeric ID for user {target_user_id}.")
            except ValueError:
                return await update.message.reply_text(
                    "*❌ User ID ဒါမှမဟုတ် ပမာဏက မှားနေတယ်ရှင့်။ ကျေးဇူးပြုပြီး: `/checkscore <user_id>` ဒါမှမဟုတ် `/checkscore @username` ကိုသုံးပေးနော်。\n"
                    "*ဥပမာ- `/checkscore 123456789` ဒါမှမဟုတ် `/checkscore @someuser`。",
                    parse_mode="Markdown"
                )
    else:
        return await update.message.reply_text(
            "*❌ သုံးတဲ့ပုံစံလေး မှားနေတယ်နော်။ ကျေးဇူးပြုပြီး အောက်က ပုံစံတွေထဲက တစ်ခုခုကို သုံးပေးပါ:*\n"
            "* - အသုံးပြုသူရဲ့ မက်ဆေ့ချ်ကို ပြန်ဖြေပြီး: `/checkscore`*\n"
            "* - တိုက်ရိုက်ရိုက်ထည့်ချင်ရင်: `/checkscore <user_id>`*\n"
            "* - Username နဲ့ ရိုက်ထည့်ချင်ရင်: `/checkscore @username`*\n"
            "*ဥပမာ- `/checkscore 123456789` ဒါမှမဟုတ် `/checkscore @someuser`。",
            parse_mode="Markdown"
        )

    if target_user_id is None:
        logger.error(f"check_user_score: Logic error: target_user_id ({target_user_id}) is None after initial parsing. update_message: {update.message.text}")
        return await update.message.reply_text("*❌ မထင်မှတ်ထားတဲ့ ပြဿနာလေး ဖြစ်သွားတယ်ရှင့်။ ကျေးဇူးပြုပြီး ထပ်ကြိုးစားကြည့်ပါဦးနော် ဒါမှမဟုတ် Admin ကို အကူအညီတောင်းပါ။*", parse_mode="Markdown") # Feminine, casual error

    chat_specific_data = get_chat_data_for_id(chat_id)
    player_stats = chat_specific_data["player_stats"].get(target_user_id)

    if not player_stats:
        try:
            chat_member = await context.bot.get_chat_member(chat_id, target_user_id)
            fetched_username = chat_member.user.username or chat_member.user.first_name
            # Do not escape fetched_username for @mention
            
            await update.message.reply_text(
                f"*👤 @{fetched_username} (ID: `{target_user_id}`) မှာတော့ ဒီ Chat အတွက် ဂိမ်းမှတ်တမ်းတွေ မရှိသေးဘူးရှင့်。\n"
                f"*သူတို့ရဲ့ လက်ကျန်ငွေကတော့ {INITIAL_PLAYER_SCORE} ကျပ်ဖြစ်ပါတယ်နော်。",
                parse_mode="Markdown"
            )
            logger.info(f"check_user_score: Admin {requester_user_id} checked score for new user {target_user_id} (no stats yet).")
            return # Exit after informing user

        except Exception as e:
            logger.error(f"check_user_score: Failed to find player {target_user_id} or fetch their details in chat {chat_id}: {e}", exc_info=True)
            return await update.message.reply_text(
                f"*❌ User ID `{target_user_id}` နဲ့ ကစားသမားကို ဒီ Chat ထဲမှာ ရှာမတွေ့ဘူးရှင့်။ Telegram က သူတို့ရဲ့ အချက်အလက်တွေကို ရယူလို့မရလို့ပါ။ သူတို့က ဒီ Chat ရဲ့ အဖွဲ့ဝင် ဟုတ်မဟုတ် သေချာအောင် စစ်ပေးပါဦးနော် ဒါမှမဟုတ် သူတို့ရဲ့ မက်ဆေ့ချ်တစ်ခုကို ပြန်ဖြေကြည့်ပါ။*",
                parse_mode="Markdown"
            )
            
    if target_username_display is None:
        target_username_display = player_stats.get('username', f"User {target_user_id}")
    
    # Rest of the check_user_score logic (displaying stats)
    total_games = player_stats['wins'] + player_stats['losses']
    win_rate = 0.0
    if total_games > 0:
        win_rate = (player_stats['wins'] / total_games) * 100

    # Use raw target_username_display for @mention, no escaping needed for Telegram
    await update.message.reply_text(
        f"*👤 @{target_username_display}* *ရဲ့ အချက်အလက်တွေ (ID: `{target_user_id}`) ကတော့*:\n"
        f"* လက်ကျန်ငွေ: {player_stats['score']} မှတ်*\n"
        f"* ကစားခဲ့တဲ့ပွဲ: {total_games} ပွဲ*\n"
        f"* ✅ အနိုင်ပွဲ: {player_stats['wins']} ပွဲ*\n"
        f"* ❌ ရှုံးပွဲ: {player_stats['losses']} ပွဲ*\n"
        f"* Win rate: {win_rate:.1f}% *\n"
        f"* last active: {player_stats['last_active'].strftime('%Y-%m-%d %H:%M')}*",
        parse_mode="Markdown"
    )
    logger.info(f"check_user_score: Admin {requester_user_id} successfully checked score for user {target_user_id}.")

async def refresh_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin command to force a refresh of the group's admin list.
    """
    chat_id = update.effective_chat.id
    # --- Group ID check ---
    if chat_id not in ALLOWED_GROUP_IDS:
        logger.info(f"refresh_admins: Ignoring command from disallowed chat ID: {chat_id}")
        await update.message.reply_text(f"*Sorry, this bot is not authorized to run in this group ({chat_id}). Please add it to an allowed group.*", parse_mode="Markdown")
        return
    # --- END Group ID check ---

    user_id = update.effective_user.id

    # Allow hardcoded global admins to use this even if group_admins isn't yet populated
    if not is_admin(chat_id, user_id) and user_id not in HARDCODED_ADMINS:
        logger.warning(f"refresh_admins: User {user_id} tried to refresh admins in chat {chat_id} but is not an admin.")
        return await update.message.reply_text("*❌ Admin တွေပဲ Admin စာရင်းကို ပြန် Refresh လုပ်လို့ရတာနော်。", parse_mode="Markdown") # Feminine, casual admin check

    logger.info(f"refresh_admins: User {user_id} attempting to refresh admin list for chat {chat_id}.")
    
    if await update_group_admins(chat_id, context):
        await update.message.reply_text("*✅ Admin စာရင်းကို အောင်မြင်စွာ ပြန် Refresh လုပ်ပြီးပါပြီရှင့်! အခုဆို အချက်အလက်တွေ အသစ်ဖြစ်သွားပြီနော်。", parse_mode="Markdown") # Feminine, casual success
    else:
        await update.message.reply_text(
            "*❌ Admin စာရင်းကို ပြန် Refresh လုပ်လို့ မရသေးဘူးရှင့်။ Bot ကို 'Chat Admins တွေကို ရယူဖို့' ခွင့်ပြုချက် ပေးထားတာ သေချာလား စစ်ပေးပါဦးနော်。",
            parse_mode="Markdown"
        )


async def stop_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Admin command to forcefully stop the current game (if active) and refund all placed bets.
    This can be used to interrupt a game or a sequence of games.
    
    Args:
        update (Update): The update object containing the /stop command.
        context (ContextTypes.DEFAULT_TYPE): The context object.
    """
    chat_id = update.effective_chat.id

    if chat_id not in ALLOWED_GROUP_IDS:
        logger.info(f"stop_game: Ignoring command from disallowed chat ID: {chat_id}")
        await update.message.reply_text(f"*Sorry, this bot is not authorized to run in this group ({chat_id}). Please add it to an allowed group.*", parse_mode="Markdown")
        return

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    logger.info(f"stop_game: User {user_id} ({username}) attempting to stop a game in chat {chat_id}")

    if not is_admin(chat_id, user_id): # Check if the requester is an admin
        logger.warning(f"stop_game: User {user_id} is not an admin and tried to stop a game in chat {chat_id}.")
        return await update.message.reply_text("*❌ Admin တွေပဲ လက်ရှိဂိမ်းကို ရပ်တန့်လို့ရပါတယ်နော်。", parse_mode="Markdown")

    # Access the game object directly from context.chat_data
    current_game = context.chat_data.get("game")

    if not current_game:
        logger.info(f"stop_game: No game object found in chat_data for chat {chat_id}.")
        return await update.message.reply_text(
            "*ℹ️ လက်ရှိစထားတဲ့ အန်စာတုံးဂိမ်း မရှိသေးဘူးရှင့်။ စတင်ဖို့ Admin က စရမယ်နော်。",
            parse_mode="Markdown"
        )
    
    if current_game.state == GAME_OVER:
        logger.info(f"stop_game: Game is already GAME_OVER for match {current_game.match_id} in chat {chat_id}.")
        return await update.message.reply_text(
            f"*ℹ️ ပွဲစဉ် #{current_game.match_id} က ပြီးသွားပါပြီရှင့်။ ပြီးသွားတဲ့ပွဲကို ရပ်လို့မရဘူးနော်။ နောက်ပွဲကျမှ ကြိုးစားကြည့်ပါ!*",
            parse_mode="Markdown"
        )

    # List of job keys to attempt to cancel and remove from chat_data
    job_keys_to_clear = ["close_bets_job", "roll_and_announce_job", "next_game_job"]
    
    for job_key in job_keys_to_clear:
        job = context.chat_data.get(job_key)
        if job:
            try:
                job.schedule_removal()
                logger.info(f"stop_game: Successfully cancelled job: {job.name} for chat {chat_id}.")
            except JobLookupError:
                logger.warning(f"stop_game: JobLookupError when trying to cancel job {job.name} for chat {chat_id}. It might have already run or been cancelled.")
            except Exception as e:
                logger.error(f"stop_game: Unexpected error canceling job '{job_key}' for chat {chat_id}: {e}", exc_info=True)
            finally:
                context.chat_data.pop(job_key, None) # Ensure it's removed from chat_data


    refunded_players_info = []
    player_stats_for_chat = get_chat_data_for_id(chat_id)["player_stats"]

    # Process refunds for all bets placed in the current game
    total_refunded_amount = 0
    total_bets_by_user = {} # Aggregate total bets per user across all bet types

    for bet_type_dict in current_game.bets.values():
        for uid, amount_bet in bet_type_dict.items():
            total_bets_by_user[uid] = total_bets_by_user.get(uid, 0) + amount_bet
    
    for uid, refunded_amount in total_bets_by_user.items():
        if uid in player_stats_for_chat:
            player_stats = player_stats_for_chat[uid]
            player_stats["score"] += refunded_amount # Add refunded amount back to score
            player_stats["last_active"] = datetime.now() # Update last active time
            total_refunded_amount += refunded_amount
            
            # Use raw username for @mention, no escaping needed for Telegram
            username_display = player_stats['username']
            refunded_players_info.append(
                f"* @{username_display}: *+{refunded_amount}* ကျပ် (လက်ကျန်ငွေ: {player_stats['score']})*"
            )
            logger.info(f"stop_game: Refunded {refunded_amount} to user {uid} in chat {chat_id}. New score: {player_stats['score']}")
        else:
            logger.warning(f"stop_game: Could not find player {uid} in stats for refund in chat {chat_id}.")

    # Clear the current game instance and any sequence-related state from context.chat_data
    context.chat_data.pop("game", None)
    context.chat_data.pop("num_matches_total", None)
    context.chat_data.pop("current_match_index", None)
    # The individual job keys should already be popped by the loop above, but ensure it.
    context.chat_data.pop("close_bets_job", None)
    context.chat_data.pop("roll_and_announce_job", None)
    context.chat_data.pop("next_game_job", None) # Clear the sequence job as well

    refund_message = f"*🛑 ပွဲစဉ် #{current_game.match_id} ကို ရပ်တန့်လိုက်ပါပြီရှင့်! 🛑*\n\n"
    if refunded_players_info:
        refund_message += "*လောင်းကြေးတွေ အားလုံး ပြန်အမ်းပေးလိုက်ပြီနော်:*\n"
        refund_message += "\n".join(refunded_players_info)
        refund_message += f"\n\n*စုစုပေါင်း ပြန်အမ်းပေးလိုက်တဲ့ ပမာဏ: {total_refunded_amount} ကျပ်*"
    else:
        refund_message += "*လက်ရှိပွဲစဉ်မှာ လောင်းကြေးထပ်ထားတဲ့သူ မရှိလို့ ပြန်အမ်းစရာ မလိုပါဘူးရှင့်。*"
    
    await update.message.reply_text(refund_message, parse_mode="Markdown")

async def deposit_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in ALLOWED_GROUP_IDS:
        logger.info(f"deposit_points: Ignoring action from disallowed chat ID: {chat_id}")
        if update.message: # Only reply if it was a message (not a callback)
            await update.message.reply_text(f"*Sorry, this bot is not authorized to run in this group ({chat_id}). Please add it to an allowed group.*", parse_mode="Markdown")
        return

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    logger.info(f"deposit_points: User {user_id} ({username}) requested deposit information in chat {chat_id}")
    
    await (update.message or update.callback_query.message).reply_text(
        "*🪙 ငွေထည့်ရန်:* 1 point = 1 kyat\n"
        "ငွေဖြည့်သွင်းရန်အတွက် Admin ကို ဒီကနေ DM ပို့ပေးပါ 👉 @BOASTER_OFFICIAL422sycat1204\n" # Username directly mentioned
        "ကျေးဇူးတင်ပါတယ်!",
        parse_mode="Markdown"
    )

async def withdraw_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the 'ငွေထုတ်မည်' (Withdraw) button and /withdraw command.
    Provides instructions for withdrawing points.
    """
    chat_id = update.effective_chat.id
    if chat_id not in ALLOWED_GROUP_IDS:
        logger.info(f"withdraw_points: Ignoring action from disallowed chat ID: {chat_id}")
        if update.message: # Only reply if it was a message (not a callback)
            await update.message.reply_text(f"*Sorry, this bot is not authorized to run in this group ({chat_id}). Please add it to an allowed group.*", parse_mode="Markdown")
        return

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    logger.info(f"withdraw_points: User {user_id} ({username}) requested withdraw information in chat {chat_id}")

    await (update.message or update.callback_query.message).reply_text(
        "*💸 ငွေထုတ်ရန်:* 1 point = 1 kyat\n"
        "ငွေထုတ်ယူရန်အတွက် Admin ကို ဒီကနေ DM ပို့ပေးပါ 👉 @BOASTER_OFFICIAL422\n" # Username directly mentioned
        "ကျေးဇူးတင်ပါတယ်!",
        parse_mode="Markdown"
    )