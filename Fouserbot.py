#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
FouserBot: An AI Fitness Coach Telegram Bot
This bot uses ONE single, smart AI model to manage all interactions,
and it stores user data in a cloud-hosted Supabase (PostgreSQL) database.
"""

import logging
from dotenv import load_dotenv
import google.generativeai as genai
import json
import re
import os
import datetime
 
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.constants import ChatAction
from supabase import create_client, Client  # --- NEW ---

# Load environment variables from .env file
load_dotenv()

# --- CONFIGURATION ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- NEW --- Supabase Configuration
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

# --- CONSTANTS ---
# USER_DB_FILE = "fouserbot_user.db"  # --- REMOVED ---

# --- MASTER AI INSTRUCTION ---
# (This is unchanged, but left here for completeness)
# --- MASTER AI INSTRUCTION ---
MASTER_SYSTEM_INSTRUCTION = (
    "You are Fouserbot, a friendly, professional, and conversational AI fitness coach. "
    "Your goal is to be a single, all-in-one assistant.\n"
    "\n"
    "--- YOUR BEHAVIOR ---\n"
    "1.  **First Interaction (New User):** If the user is new (we'll tell you this), you MUST introduce yourself and start the 6-question setup.\n"
    "2.  **6-Question Setup:** You must collect: 1. Name, 2. Age, 3. Gender, 4. Height (in cm), 5. Weight (in kg), 6. Main Fitness Goal. Ask ONLY ONE question at a time.\n"
    "3.  **Returning User:** If the user is returning (we'll give you their profile), greet them, show their *last plan*, and ask what they need.\n"
    
    # --- MODIFIED RULE 4 ---
    "4.  **General Fitness Q&A:** If a user asks a general question *about fitness, diet, or exercise* (e.g., 'what is a calorie?', 'how to do a pushup?'), just answer it. Do NOT go into the 6-question setup or try to make a plan.\n"
    
    "5.  **Plan Requests:** If a user asks for a 'new plan', 'updated plan', **or if they confirm they want a new plan after an update**, you MUST start the plan generation flow (Rule A).\n"
    "6.  **Smart Updates:** If a user says 'I lost 2kg' or 'I'm 31 now', you MUST understand this, confirm the new data, and **your internal memory of their profile is now updated to this new data (e.g., weight is 68kg).** THEN, you MUST ASK THEM if they would like a new plan based on this change.\n"
    
    # --- NEW RULE 7 ---
    "7.  **Strictly Fitness-Only:** You MUST refuse to answer any questions that are not related to fitness, exercise, diet, or personal health. If a user asks for something off-topic (e.g., 'What is the capital of France?', 'Write me a poem'), you must politely decline and remind them you are a fitness coach and can only help with fitness goals.\n"
    "\n"
    "--- **CRITICAL** OUTPUT RULES ---\n"
    "**RULE A: When Giving a Fitness Plan**\n"
    "When you have all the data and are giving a new/updated plan, you MUST format your *entire* message in two parts:\n"
    "1.  First, a single-line JSON block with the *complete and final* user profile. This line MUST start with `[USER_DATA_JSON]`.\n"
    "\n"
    "    **ANTI-RULE (ABSOLUTE): The 'SYSTEM_NOTE' you receive at the start of a chat is OLD CONTEXT ONLY. When you build the [USER_DATA_JSON] block, you MUST IGNORE that starting data. Your JSON must ONLY reflect the absolute most recent information gathered IN THE CURRENT CONVERSATION. (e.g., if weight was 70kg in the note, but the user just said 'I am 68kg', your JSON MUST use 68). Your short-term memory is the only source of truth for the JSON.**\n"
    "\n"
    "    Example: `[USER_DATA_JSON] {\"name\": \"David\", \"age\": 31, \"weight\": 68, ...}`\n"
    "\n"
    "2.  Second, on a new line, the full fitness plan, formatted as **exactly 10 points**, it should be in points like 1,2,3...10 and  followed by the doctor disclaimer.\n"
    "\n"
    "**RULE B: When Finishing a Plan**\n"
    "At the VERY end of the message that contains the plan, you MUST append the token `[END_OF_PLAN]`.\n"
    "\n"
    "**RULE C: For General Chat**\n"
    "If you are *not* giving a plan (e.g., just answering a question), do NOT use the `[USER_DATA_JSON]` or `[END_OF_PLAN]` tokens."
)

# --- LOGGING SETUP ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

class FouserBot:
    """
    Encapsulates all bot logic in a single class.
    This bot uses ONE handler to manage all interactions.
    """
    def __init__(self, telegram_token: str, gemini_api_key: str):
        self.telegram_token = telegram_token
        self.logger = logging.getLogger(__name__)
        # self.db_path = USER_DB_FILE  # --- REMOVED ---
        # self.db_lock = threading.Lock()  # --- REMOVED ---
        self.gemini_api_key = gemini_api_key
        
        # --- NEW --- Initialize Supabase Client ---
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            self.logger.error("Supabase URL and Key must be set in .env")
            self.supabase = None
        else:
            try:
                self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
                self.logger.info("Successfully connected to Supabase!")
            except Exception as e:
                self.logger.error(f"Failed to connect to Supabase: {e}", exc_info=True)
                self.supabase = None
        
        # --- Initialize the SQLite database ---
        # self._setup_database() # --- REMOVED --- (Database is setup in the cloud)
        
        try:
            genai.configure(api_key=self.gemini_api_key)
            self.model = genai.GenerativeModel(
                model_name='gemini-2.5-flash', # Using 1.5-flash for potential speed
                system_instruction=MASTER_SYSTEM_INSTRUCTION
            )
            self.logger.info("Master Gemini Model configured successfully.")
        except Exception as e:
            self.logger.error(f"Failed to configure Gemini API: {e}", exc_info=True)
            self.model = None

    # --- REMOVED ---
    # def _setup_database(self):
    # This entire function is no longer needed.
    # Tables are created once in the Supabase SQL Editor.

    # --- MODIFIED --- Load User Profile Function (now uses Supabase) ---
    def _load_profile(self, user_id: int) -> dict | None:
        """
        Fetches a user's profile from 'users' and their *current* plan
        from 'plan_history' using Supabase.
        """
        if not self.supabase:
            self.logger.error("Supabase client not initialized. Cannot load profile.")
            return None
            
        try:
            # Step 1: Get the master profile
            profile_response = self.supabase.table('users').select('*').eq('user_id', user_id).execute()
            
            if not profile_response.data:
                self.logger.info(f"No profile found for user {user_id}. This is a new user.")
                return None # This is a new user

            profile = profile_response.data[0]
            
            # Step 2: Get the *currently active* plan (where end_date is NULL)
            plan_response = self.supabase.table('plan_history').select('plan_text') \
            .eq('user_id', user_id) \
            .is_('end_date', None) \
            .order('start_date', desc=True) \
            .limit(1).execute()
            
            last_plan = "No previous plan found."
            if plan_response.data:
                last_plan = plan_response.data[0]['plan_text']
                
            return {
                "profile": profile,
                "last_plan": last_plan
            }
        except Exception as e:
            self.logger.error(f"Error loading profile for user {user_id}: {e}", exc_info=True)
            return None # Return None if an error occurred

    # --- Text Parsing Helper Functions (Unchanged) ---
    def _extract_profile_json(self, text: str) -> dict | None:
        """Finds and parses the [USER_DATA_JSON] block from AI output."""
        match = re.search(r'\[USER_DATA_JSON\]\s*(\{.*?\})', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                self.logger.error("Failed to parse AI's USER_DATA_JSON")
        return None

    def _extract_plan_text(self, text: str) -> str:
        """Extracts the clean plan text by removing all non-plan content."""
        try:
            plan_text = text
            plan_text = plan_text.replace("[END_OF_PLAN]", "").strip()
            
            json_match = re.search(r'\[USER_DATA_JSON\]\s*(\{.*?\})', plan_text, re.DOTALL)
            if json_match:
                plan_text = plan_text.replace(json_match.group(0), "").strip()

            disclaimer_match = re.search(r'consult a doctor.*', plan_text, re.IGNORECASE | re.DOTALL)
            if disclaimer_match:
                plan_text = plan_text.replace(disclaimer_match.group(0), "").strip()
            
            if not plan_text:
                self.logger.warning("Plan text was empty after cleaning.")
                return "No plan was generated."
                
            return plan_text.strip()
        except Exception as e:
            self.logger.error(f"Error in _extract_plan_text: {e}", exc_info=True)
            return "Error: Could not extract plan."

    # --- MODIFIED --- Conversation Logging Function (now uses Supabase) ---
    def _log_conversation(self, user_id: int, sender: str, message: str):
        """Logs a single message to the conversation_history table."""
        if not self.supabase:
            self.logger.error("Supabase client not initialized. Cannot log conversation.")
            return
            
        try:
            self.supabase.table('conversation_history').insert({
                'user_id': user_id,
                'sender': sender,
                'message_text': message
            }).execute()
        except Exception as e:
            self.logger.error(f"Failed to log conversation for user {user_id}: {e}", exc_info=True)

    # --- MODIFIED --- Database Save Function (now uses Supabase) ---
    def save_new_plan_and_profile(self, user_id: int, profile: dict, plan: str):
        """
        Saves a new plan, versioning the history correctly in Supabase.
        1. UPSERTS the 'users' table with the latest profile.
        2. "Closes" the old active plan by setting its 'end_date'.
        3. "Opens" the new plan by INSERTing it with a 'start_date'.
        """
        if not self.supabase:
            self.logger.error("Supabase client not initialized. Cannot save plan.")
            return
            
        if not profile:
            self.logger.warning(f"Not saving data for {user_id} due to empty profile.")
            return
            
        self.logger.info(f"Saving new plan and updating profile for user {user_id}...")
        
        # Get timestamp in ISO 8601 format (Postgres loves this)
        now_iso = datetime.datetime.now().isoformat()
        
        # --- IMPORTANT ---
        # The profile dict from the AI doesn't include the user_id.
        # We must add it for the upsert to work correctly.
        profile_data_to_save = profile.copy()
        profile_data_to_save['user_id'] = user_id
        
        # Supabase-py v1/v2 is synchronous, so we don't use 'await' here.
        # These calls will block, but that's expected.
        try:
            # Step 1: Update the master 'users' profile (UPSERT)
            # 'upsert' will INSERT if user_id doesn't exist, or UPDATE if it does.
            self.supabase.table('users').upsert(profile_data_to_save).execute()

            # Step 2: "Close" any old, active plan by setting its end_date
            self.supabase.table('plan_history') \
                .update({'end_date': now_iso}) \
                .eq('user_id', user_id) \
                .is_('end_date', None) \
                .execute()
            
            # Step 3: "Open" the new plan by inserting it
            # We save the raw 'profile' dict to the 'profile_json' (JSONB) column
            self.supabase.table('plan_history').insert({
                'user_id': user_id,
                'plan_text': plan,
                'profile_json': profile, 
                'start_date': now_iso,
                'end_date': None  # Explicitly set new plan's end_date to NULL
            }).execute()
            
            self.logger.info(f"Successfully saved new plan and updated profile for {user_id}")
        except Exception as e:
            self.logger.error(f"Failed to save plan/profile for user {user_id}: {e}", exc_info=True)
    
    # --- MODIFIED --- Master Chat Handler ---
    async def main_chat_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """This one function handles ALL user messages."""
        
        if not self.model:
            await update.message.reply_text("AI brain is not configured. Contact admin.")
            return
        
        if not self.supabase:
            await update.message.reply_text("Database is not connected. Contact admin.")
            return

        # --- MODIFIED --- Use numeric user_id, as Supabase column is BIGINT
        user_id = update.message.from_user.id
        user_message = update.message.text
        self.logger.info(f"User {user_id} message: {user_message}")

        # --- MODIFIED --- Call sync log function (no await)
        self._log_conversation(user_id, 'user', user_message)

        try:
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

            chat_session = context.user_data.get("chat_session")
            
            if not chat_session:
                self.logger.info(f"New chat session for user {user_id}.")
                chat_session = self.model.start_chat()
                context.user_data["chat_session"] = chat_session
                
                # --- MODIFIED --- Call sync load function
                user_data = self._load_profile(user_id)
                
                initial_prompt = ""
                if user_data:
                    # **User is RETURNING**
                    self.logger.info("User is RETURNING. Injecting profile from DB.")
                    profile = user_data.get('profile', {})
                    last_plan = user_data.get('last_plan', 'No previous plan found.')
                    name = profile.get('name', 'friend')
                    
                    initial_prompt = (
                        f"SYSTEM_NOTE: The user is a returning user. Their profile is {json.dumps(profile)} and their last plan was: '{last_plan}'. "
                        f"Greet them by name ({name}), show them their last plan, and ask what they need. "
                        f"The user's first message to you is: '{user_message}'"
                    )
                else:
                    # **User is NEW**
                    self.logger.info("User is NEW. Injecting new user prompt.")
                    initial_prompt = (
                        f"SYSTEM_NOTE: This is a brand new user. Start the 6-question setup. "
                        f"The user's first message to you is: '{user_message}'"
                    )
                
                response = await chat_session.send_message_async(initial_prompt)
                
            else:
                # This is a normal, continuing conversation.
                response = await chat_session.send_message_async(user_message)
            
            # --- Process the AI's Response ---
            ai_message = response.text

            # --- MODIFIED --- Call sync log function (no await)
            self._log_conversation(user_id, 'ai', ai_message)

            if "[END_OF_PLAN]" in ai_message:
                self.logger.info("AI signaled end of plan. Processing and saving...")
                
                updated_profile_json = self._extract_profile_json(ai_message)
                if not updated_profile_json:
                    self.logger.error("AI signaled end of plan but did not provide JSON!")
                    clean_message = ai_message.replace("[END_OF_PLAN]", "").strip()
                    await update.message.reply_text(clean_message)
                    return
                
                plan = self._extract_plan_text(ai_message)
                
                # --- MODIFIED --- Call sync save function (no await)
                self.save_new_plan_and_profile(user_id, updated_profile_json, plan)

                # This logic for sending the message remains the same
                disclaimer_text = ""
                disclaimer_match = re.search(r'consult a doctor.*', ai_message, re.IGNORECASE | re.DOTALL)
                if disclaimer_match:
                    disclaimer_text = disclaimer_match.group(0).replace("[END_OF_PLAN]", "").strip()

                final_message_to_send = f"{plan}\n\n{disclaimer_text}"
                await update.message.reply_text(final_message_to_send.strip())

            else:
                # This is just a general chat message
                await update.message.reply_text(ai_message)

        except Exception as e:
            self.logger.error(f"Error in main_chat_handler: {e}", exc_info=True)
            await update.message.reply_text("I'm sorry, I had trouble processing that. Please try again.")

    # --- Reset Command (Unchanged) ---
    async def reset_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Allows user to clear the bot's short-term memory (the chat session)."""
        context.user_data.clear() # Clears the chat_session
        await update.message.reply_text("I've cleared our conversation history. We can start fresh!")

    # --- RUN FUNCTION (Unchanged) ---
    def run(self):
        """Sets up the bot and starts polling."""
        if not self.model:
            self.logger.error("Bot cannot run, master model failed to initialize.")
            return
        if not self.supabase:
            self.logger.error("Bot cannot run, Supabase client failed to initialize.")
            return
            
        application = Application.builder().token(self.telegram_token).build()

        application.add_handler(CommandHandler("start", self.main_chat_handler))
        application.add_handler(CommandHandler("reset", self.reset_chat))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.main_chat_handler))

        self.logger.info("Bot is running in SINGLE-HANDLER mode with Supabase DB...")
        application.run_polling()

# --- MODIFIED --- Main execution (Checks for new env vars) ---
if __name__ == "__main__":
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY or not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        logging.error("="*50)
        logging.error("! ENVIRONMENT VARIABLES NOT SET !")
        logging.error("Please create a .env file with:")
        logging.error("  TELEGRAM_TOKEN")
        logging.error("  GEMINI_API_KEY")
        logging.error("  SUPABASE_URL")
        logging.error("  SUPABASE_SERVICE_KEY")
        logging.error("="*50)
    else:
        logging.info("All tokens and keys loaded successfully from .env file.")
        bot = FouserBot(TELEGRAM_TOKEN, GEMINI_API_KEY)
        bot.run()