import os
import random
import asyncio
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ===== ENV VARIABLES =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET")

# ===== DATA (75+ each, random) =====
greetings = [f"🚨 AGENT ORANGE DETECTED USER #{i}\nwelcome to the timeline." for i in range(1, 80)]
jokes = [f"weak hands detected #{i}" for i in range(1, 80)]
updates = [f"SYSTEM LOG {i}\ntimeline corruption rising" for i in range(1, 80)]

CA = "0xYOURADDRESS"

# ===== TELEGRAM FUNCTIONS =====
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        await update.message.reply_text(random.choice(greetings))

async def ca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"CONTRACT ADDRESS:\n{CA}")

async def joke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(jokes))

# ===== X POST FUNCTION =====
import requests
from requests_oauthlib import OAuth1

def post_to_x(text):
    url = "https://api.twitter.com/2/tweets"

    auth = OAuth1(
        X_API_KEY,
        X_API_SECRET,
        X_ACCESS_TOKEN,
        X_ACCESS_SECRET
    )

    json_data = {"text": text}

    requests.post(url, auth=auth, json=json_data)

# ===== AUTO POST =====
async def auto_post(context: ContextTypes.DEFAULT_TYPE):
    msg = random.choice(updates)
    chat_id = context.job.chat_id
    await context.bot.send_message(chat_id=chat_id, text=msg)
    post_to_x(msg)

# ===== MAIN =====
async def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.add_handler(CommandHandler("ca", ca))
    app.add_handler(CommandHandler("joke", joke))

    chat_id = -1000000000000  # replace later

    app.job_queue.run_repeating(auto_post, interval=12600, first=10, chat_id=chat_id)

    print("AGENT ORANGE ACTIVE")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
