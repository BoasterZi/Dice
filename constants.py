import os
import random

# --- UPDATED: Centralized data structure for all chats ---
global_data = {
    "all_chat_data": {} # Stores chat_id: {player_stats: {}, match_counter: int, match_history: [], group_admins: [], consecutive_idle_matches: 0}
}

def get_chat_data_for_id(chat_id: int):
    """
    Retrieves or initializes the chat-specific data from global_data.
    This ensures that each chat maintains its own game state, player scores, etc.
    """
    if chat_id not in global_data["all_chat_data"]:
        global_data["all_chat_data"][chat_id] = {
            "player_stats": {}, # Stores user_id: {username: str, score: int, wins: int, losses: int, last_active: datetime}
            "match_counter": 1, # Unique ID for each match within a chat
            "match_history": [], # Stores past match results
            "group_admins": [], # Cached list of admin user_ids for this specific chat
            "consecutive_idle_matches": 0 # New: Tracks idle matches for auto-stopping
        }
    return global_data["all_chat_data"][chat_id]
# --- END UPDATED ---

# Hardcoded global administrators (Telegram User IDs)
# These users will always have admin privileges regardless of specific group admin status.
# Replace with actual user IDs for your global admins.
HARDCODED_ADMINS = [
    1599213796,  # Replace with a real admin's User ID (e.g., your ID)
    # Add more admin IDs here if needed
]

# Allowed Group IDs
# The bot will only function in these specific groups.
# Replace with the actual Telegram Group IDs where you want the bot to run.
# You can get a group's ID by forwarding a message from the group to @userinfobot
ALLOWED_GROUP_IDS = [
   
   -4845472581,
]


# Initial score for new players
INITIAL_PLAYER_SCORE = 0 # Changed to 0 as per request

# Emojis for results (optional, but adds flair!)
RESULT_EMOJIS = {
    "big": "⬆️",
    "small": "⬇️",
    "lucky": "💎"
}

# Add more constants if needed, e.g., default bet amounts, game cool-downs, etc.
