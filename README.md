FouserBot: An AI Fitness Coach for Telegram

FouserBot is an intelligent, conversational AI fitness coach built for Telegram. It uses Google's Gemini API to provide personalized fitness plans, answer health questions, and dynamically track a user's progress over time.

Unlike simple bots, FouserBot operates with a single, powerful AI "brain" that manages the entire user interaction, from initial setup to long-term memory and general Q&A.

(Suggestion: Add a screenshot here, like one of the ones you sent me, showing the bot's conversation flow!)

Features

Smart Conversational AI: The bot can answer general fitness questions (e.g., "What is a calorie?") and perform complex tasks in one continuous chat.

Personalized Plan Generation: Guides new users through a 6-question setup (Name, Age, Gender, Height, Weight, Goal) to generate a custom 10-point fitness plan.

Persistent User Memory: All user data (profile and plans) is stored in a robust SQLite database.

Natural Language Updates: Users don't need commands. They can just say, "I lost 2kg" or "I'm 31 now," and the AI will understand, confirm the change, and offer to update their plan.

Dynamic "Memory" Flow: The AI is smart enough to know when to ask questions, when to answer, and when to save data. It's all managed by a single, comprehensive system prompt.

AI-Driven Data Parsing: The bot uses AI-generated tokens ([USER_DATA_JSON] and [END_OF_PLAN]) to reliably parse the AI's response and save data.

Normalized Database: User data is stored in clean, individual SQL columns (not JSON blobs) for efficient and scalable storage.

Technology Stack

Python 3.10+

Google Gemini API (gemini-2.5-flash) for the core AI logic.

python-telegram-bot: The library used to run the Telegram bot.

sqlite3: Built-in Python library for database storage.

re (RegEx): For parsing AI output tokens.

Setup & Installation

Follow these steps to run your own instance of FouserBot.

1. Clone the Repository

git clone [https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git](https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git)
cd YOUR_REPOSITORY_NAME


2. Create a Virtual Environment (Recommended)

# For Windows
python -m venv venv
.\venv\Scripts\activate

# For macOS/Linux
python3 -m venv venv
source venv/bin/activate


3. Install Dependencies

Install the required Python libraries from the requirements.txt file.

pip install -r requirements.txt


4. Configure Your Bot

You must provide two secret keys in the fouserbot_final.py script:

TELEGRAM_TOKEN: Get this from @BotFather on Telegram by creating a new bot.

GEMINI_API_KEY: Get this from Google AI Studio (formerly MakerSuite).

Paste these keys into the configuration section at the top of the file:

# --- CONFIGURATION ---
TELEGRAM_TOKEN = "YOUR_TELEGRAM_TOKEN_HERE"
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"


5. Set Up Bot Commands

For the best user experience, register your bot's commands with @BotFather.

Open your chat with @BotFather.

Send /mybots and select your bot.

Go to Edit Bot > Edit Commands.

Paste the following text and send it:

start - Start a new fitness plan
reset - Clear the bot's memory and start fresh


This will make /start and /reset clickable commands in the chat.

6. Run the Bot

Once configured, you can run the bot:

python fouserbot_final.py


The bot will automatically create the fouserbot_user.db file in the same directory and start listening for messages.

How It Works

This bot's logic is built on a few key principles:

Single Handler: A single main_chat_handler processes all text messages. This simplifies the logic and removes conflicts between different bot "modes."

The Master Prompt: The MASTER_SYSTEM_INSTRUCTION constant is the "brain" of the bot. It contains over 20 strict rules that tell the AI how to behave in every situation (new user, returning user, Q&A, data update).

Priming the AI: When a user sends their first message, the bot checks the SQLite database.

If New: It injects an INITIAL_CONTEXT into the AI's history, telling it to start the 6-question setup.

If Returning: It injects an INITIAL_CONTEXT with the user's old profile and last plan, telling the AI to greet them.

Data-Saving Flow: The AI is instructed to only output a [USER_DATA_JSON] block when it's saving a plan. The Python code looks for this block, parses it, and uses an INSERT OR REPLACE SQL command to save the new, updated data, automatically deleting the old row.

