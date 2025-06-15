import logging
from datetime import datetime
import random

from constants import global_data, INITIAL_PLAYER_SCORE

logger = logging.getLogger(__name__)

# Game states
WAITING_FOR_BETS = "WAITING_FOR_BETS"
GAME_CLOSED = "GAME_CLOSED"
GAME_OVER = "GAME_OVER"

# Function to escape Markdown V2 special characters in a string
def escape_markdown_v2(text: str) -> str:
    """Escapes common Markdown V2 special characters."""
    # List of characters that need to be escaped in Markdown V2
    special_chars = '_*[]()~`>#+-=|{}.!'
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

class DiceGame:
    def __init__(self, match_id: int, chat_id: int):
        self.match_id = match_id
        self.chat_id = chat_id
        self.state = WAITING_FOR_BETS
        self.bets = {"big": {}, "small": {}, "lucky": {}} # Stores bets: {"type": {user_id: amount}}
        self.participants = set() # Stores user_ids of players who participated in this match
        self.result = None # Stores the dice roll result (sum of two dice)

    def place_bet(self, user_id: int, username: str, bet_type: str, amount: int) -> tuple[bool, str]:
        """
        Processes a player's bet for the current game.

        Args:
            user_id (int): The Telegram user ID of the player.
            username (str): The Telegram username or first name of the player.
            bet_type (str): The type of bet ("big", "small", or "lucky").
            amount (int): The amount of points the player wants to bet.

        Returns:
            tuple[bool, str]: A tuple indicating success (True/False) and a
                              response message for the player.
        """
        # Ensure bet type is valid
        if bet_type not in ["big", "small", "lucky"]:
            logger.warning(f"place_bet: Invalid bet type '{bet_type}' from user {user_id}.")
            return False, "*❌ လောင်းကြေးအမျိုးအစားက မှားနေတယ်ရှင့်။ 'big', 'small' ဒါမှမဟုတ် 'lucky' ထဲက တစ်ခုခုဖြစ်ရမယ်နော်။*" # Feminine invalid bet type

        # Ensure amount is positive
        if amount <= 0:
            logger.warning(f"place_bet: Invalid bet amount '{amount}' from user {user_id}.")
            return False, "*❌ လောင်းကြေးပမာဏက အပေါင်းကိန်းဖြစ်ရမယ်နော်။ ၀ ဒါမှမဟုတ် အနုတ် မရပါဘူးရှင့်။*" # Feminine invalid amount

        # Ensure game is in betting phase
        if self.state != WAITING_FOR_BETS:
            logger.info(f"place_bet: User {user_id} tried to bet when betting is closed for match {self.match_id}. State: {self.state}")
            escaped_username = escape_markdown_v2(username)
            return False, f"*⚠️ @{escaped_username} ရေ၊ ဒီဂိမ်းအတွက် လောင်းကြေးတွေ ပိတ်လိုက်ပြီနော်။ နောက်ပွဲကျမှ ပြန်လာခဲ့ပါဦး!*" # Feminine closed bets

        # Get or initialize player stats for this chat
        chat_data = global_data["all_chat_data"].setdefault(self.chat_id, {
            "player_stats": {},
            "match_counter": 1,
            "match_history": [],
            "group_admins": [],
            "consecutive_idle_matches": 0 # Ensure this is present
        })
        player_stats = chat_data["player_stats"].setdefault(user_id, {
            "username": username,
            "score": INITIAL_PLAYER_SCORE,
            "wins": 0,
            "losses": 0,
            "last_active": datetime.now()
        })

        # Update username in case it changed since last interaction
        player_stats["username"] = username 
        player_stats["last_active"] = datetime.now() # Update last active time

        # Check if player has enough score
        if player_stats["score"] < amount:
            logger.info(f"place_bet: User {user_id} ({username}) tried to bet {amount} but only has {player_stats['score']}.")
            escaped_username = escape_markdown_v2(username)
            return False, f"*❌ @{username} ရေ၊ လက်ကျန်ငွေမလုံလောက်ပါဘူးရှင့်။ သင့်မှာ {player_stats['score']} ကျပ်ပဲရှိတယ်ရှင့်။*" # Feminine, casual, direct

        # Deduct bet amount from player's score
        player_stats["score"] -= amount
        
        # Add bet to the game's bets
        # Aggregate bets if the user bets multiple times on the same type
        current_bet_amount_on_type = self.bets[bet_type].get(user_id, 0)
        self.bets[bet_type][user_id] = current_bet_amount_on_type + amount
        
        self.participants.add(user_id) # Add player to participants set

        logger.info(f"place_bet: User {user_id} ({username}) placed {amount} on {bet_type}. Remaining score: {player_stats['score']}.")
        escaped_username = escape_markdown_v2(username)
        return True, f"*✅ @{username} ရေ၊ {amount} ကျပ်ကို {bet_type.upper()} ပေါ် လောင်းလိုက်ပြီနော်။ လက်ကျန်ငွေ: {player_stats['score']} ကျပ်ရှိပါသေးတယ်ရှင့်!*" # Feminine, casual confirmation


    def payout(self, chat_id: int) -> tuple[str, float, dict]:
        """
        Calculates and distributes payouts based on the dice roll result.

        Args:
            chat_id (int): The ID of the chat where the game is played.

        Returns:
            tuple[str, float, dict]: A tuple containing the winning bet type,
                                     its multiplier, and a dictionary of
                                     {user_id: winnings} for all winning players.
        """
        winning_type = ""
        multiplier = 0

        if self.result is None:
            logger.error(f"payout: Attempted to payout for match {self.match_id} in chat {chat_id} but result is None.")
            return "error", 0.0, {}

        # Determine winning type and multiplier
        if self.result > 7:
            winning_type = "big"
            multiplier = 2
        elif self.result < 7:
            winning_type = "small"
            multiplier = 2
        else: # self.result == 7
            winning_type = "lucky"
            multiplier = 5
        
        logger.info(f"payout: Match {self.match_id} result is {self.result}. Winning type: {winning_type}, Multiplier: {multiplier}.")

        # Get player stats for this chat
        chat_data = global_data["all_chat_data"].setdefault(chat_id, {
            "player_stats": {},
            "match_counter": 1,
            "match_history": [],
            "group_admins": [],
            "consecutive_idle_matches": 0 # Ensure this is present
        })
        player_stats_for_chat = chat_data["player_stats"]
        
        individual_payouts = {}
        winning_bets = self.bets.get(winning_type, {})

        for user_id, amount_bet in winning_bets.items():
            if user_id in player_stats_for_chat:
                winnings = int(amount_bet * multiplier)
                player_stats_for_chat[user_id]["score"] += winnings
                player_stats_for_chat[user_id]["wins"] += 1
                player_stats_for_chat[user_id]["last_active"] = datetime.now()
                individual_payouts[user_id] = winnings
                logger.info(f"payout: User {user_id} won {winnings} in match {self.match_id}. New score: {player_stats_for_chat[user_id]['score']}.")
            else:
                logger.warning(f"payout: Winning user {user_id} not found in player_stats_for_chat during payout for match {self.match_id}.")
        
        # Update losses for non-winning participants
        for user_id in self.participants:
            if user_id not in winning_bets and user_id in player_stats_for_chat:
                player_stats_for_chat[user_id]["losses"] += 1
                player_stats_for_chat[user_id]["last_active"] = datetime.now()
                logger.info(f"payout: User {user_id} lost in match {self.match_id}.")

        # Record match history
        chat_data["match_history"].append({
            "match_id": self.match_id,
            "result": self.result,
            "winner": winning_type,
            "participants": len(self.participants),
            "timestamp": datetime.now()
        })
        # Keep history list to a manageable size, e.g., last 20 matches
        if len(chat_data["match_history"]) > 20:
            chat_data["match_history"] = chat_data["match_history"][-20:]

        return winning_type, multiplier, individual_payouts
