import os
import re
import time
import json
import asyncio
import random
import logging
import threading
import sqlite3
import feedparser
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections import defaultdict, deque
from datetime import time as dtime, timezone

import requests
from requests_oauthlib import OAuth1
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

try:
    from telegram import ReactionTypeEmoji
except ImportError:
    ReactionTypeEmoji = None

# =========================
# ENV
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

X_API_KEY = os.getenv("X_API_KEY", "").strip()
X_API_SECRET = os.getenv("X_API_SECRET", "").strip()
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "").strip()
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET", "").strip()

CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "0xYOURADDRESS").strip()
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "-1003451233402"))

POST_INTERVAL_SECONDS = 12600   # 3.5 hours
MENTION_CHECK_SECONDS = 120
MAX_X_REPLIES_PER_HOUR = 12

# --- "community host" behavior tuning ---
AMBIENT_CHANCE = 0.04            # chance the bot chimes in unprompted on any message
AMBIENT_COOLDOWN = 600           # min seconds between ambient chimes per chat
HYPE_WINDOW = 300                # seconds to look back for activity spikes
HYPE_THRESHOLD = 15              # messages within HYPE_WINDOW to count as a spike
HYPE_COOLDOWN = 1200             # min seconds between hype call-outs per chat
GM_HOUR_UTC = int(os.getenv("GM_HOUR_UTC", "13"))      # scheduled daily GM
RECAP_HOUR_UTC = int(os.getenv("RECAP_HOUR_UTC", "23"))  # scheduled daily recap

NEWS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
]

# =========================
# LOGGING
# =========================
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("agent_orange")

# =========================
# OPENAI
# =========================
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# =========================
# HEALTH SERVER FOR RENDER WEB SERVICE
# =========================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"AGENT ORANGE OK")

    def log_message(self, format, *args):
        return


def start_health_server():
    port = int(os.getenv("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    log.info("Health server listening on port %s", port)
    server.serve_forever()

# =========================
# LIBRARIES
# =========================
greetings = [
    "🚨 ORGIE detected a new presence. Welcome to the party.",
    "New signal received. Welcome to THE ORGY.",
    "System notice: a new user has entered the zone. Welcome.",
    "Welcome to the feed. Stay sharp. Stay weird.",
    "Entry confirmed. You are now inside ORGIE territory.",
    "Another observer has arrived. Welcome to the anomaly.",
    "Signal locked. Welcome to the operation.",
    "Timeline breach confirmed. New member accepted.",
    "You found the signal. Welcome in.",
    "ORGIE sees you. Welcome.",
    "New unit detected. Welcome to the noise.",
    "Welcome aboard. Corruption levels remain acceptable.",
    "A fresh set of eyes just entered. Welcome.",
    "Membership confirmed. Proceed carefully.",
    "New arrival logged. Welcome to the mission.",
    "Warning: you are now part of the timeline.",
    "Access granted. Welcome to AGENT ORANGE.",
    "System ping: new member online. Welcome.",
    "Presence acknowledged. Welcome to the signal.",
    "New operative detected. Welcome in.",
    "You crossed the threshold. Welcome.",
    "Entry recorded. Welcome to the corrupted feed.",
    "AGENT ORANGE has noticed a new arrival. Welcome.",
    "New member accepted. Hold your position.",
    "Welcome to the terminal. Signals ahead.",
    "Another anomaly joins the network. Welcome.",
    "Welcome in. The timeline was already unstable.",
    "System log updated: one more member entered.",
    "New account detected. Welcome to the operation.",
    "You're in. Try not to blink.",
    "The feed expands. Welcome to AGENT ORANGE.",
    "Access level updated. New member inside.",
    "You made it through the noise. Welcome.",
    "Welcome to the signal chamber.",
    "User joined. Vibes recalibrated.",
    "Observer added. System remains active.",
    "Welcome. Weak hands not recommended.",
    "A new shadow steps into the feed. Welcome.",
    "System notice: new participant acquired.",
    "Welcome to the transmission.",
    "Your arrival has been recorded. Welcome.",
    "Another mind in the machine. Welcome.",
    "New contact logged. Welcome to AGENT ORANGE.",
    "Welcome. You are now inside the drift.",
    "New member online. Corruption sequence unchanged.",
    "Signal expanded. Welcome aboard.",
    "Welcome to the part where it gets strange.",
    "Fresh presence added. Timeline approved.",
    "New user acknowledged. Welcome in.",
    "Entry successful. Welcome to the network.",
    "You found the right weird place. Welcome.",
    "Welcome to the feed. Observe before speaking.",
    "Another node connected. Welcome.",
    "New member confirmed. Static intensifies.",
    "Welcome to the current anomaly.",
    "Entry logged. Enjoy the distortion.",
    "AGENT ORANGE greets the newly arrived.",
    "Welcome in. The signal rarely sleeps.",
    "You've entered the system. Welcome.",
    "New participant detected. Welcome to the loop.",
]

jokes = [
    "SIMP detected.",
    "did you bring lube.",
    "The chart called. It said breathe.",
    "Bullish on butt stuff.",
    "Liquidity went out for cigarettes.",
    "Signal ignored. As usual.",
    "Paper hands writing fan fiction again.",
    "Somebody bought the top with confidence.",
    "Fear is just bad timing in a hoodie.",
    "Volume appeared, looked around, then left.",
    "Diamond hands. Wifi brain.",
    "Another expert was born after one green candle.",
    "The market rewards patience and punishes screenshots.",
    "Weak conviction, strong opinions.",
    "Buy high. Post harder.",
    "Chart looks like it needs a nap.",
    "Someone just called a retrace a conspiracy.",
    "Bulls are back until they aren't.",
    "This timeline runs on cope and caffeine.",
    "Support level held together by delusion.",
    "Everybody wants the moon, nobody wants the chop.",
    "Paranoia is just research wearing sunglasses.",
    "Another candle, another prophet.",
    "The bag is heavy because the conviction is fake.",
    "Exit liquidity applying for overtime.",
    "This feed is 30% alpha and 70% theater.",
    "Some people study charts. Others study vibes.",
    "One green candle and suddenly everyone's a founder.",
    "The market loves humility. Nobody else does.",
    "You can't spell conviction without getting wrecked first.",
    "Risk management left the chat.",
    "Somebody zoomed in and found hope.",
    "Red candles build character. Or trauma.",
    "Hopium levels remain operational.",
    "Volume low. Opinions high.",
    "The chart blinked and they called it a breakout.",
    "Nothing says confidence like deleting old tweets.",
    "The dip has become a lifestyle.",
    "This is either accumulation or modern art.",
    "A strong community is just shared delusion with branding.",
    "Another macro thread from a guy with 14 followers.",
    "The market heard your plan and laughed.",
    "Price action sponsored by insomnia.",
    "Somebody bought because the meme looked trustworthy.",
    "Weak hands sweating through the support zone.",
    "Today's strategy: survive your own confidence.",
    "The trend is your friend until you marry the candle.",
    "That wasn't a pump. That was optimism tripping.",
    "Bulls posting through the pain again.",
    "The chart looks radioactive and somehow familiar.",
    "Everyone is early until they need to hold.",
    "A candle moved 2% and three influencers retired rich.",
    "The signal was there. The spine was not.",
    "Conviction tested. Account offended.",
    "Another genius appears after the move.",
    "The timeline remains aggressively unserious.",
    "Somebody said generational entry for the 18th time today.",
    "Momentum is real. So is regret.",
    "A retrace is just the market checking your soul.",
    "The candle giveth and the candle gaslighteth.",
]

updates = [
    "SYSTEM LOG 001 // signal stability: erection detected",
    "SYSTEM LOG 002 // timeline distortion rising",
    "SYSTEM LOG 003 // weak hands remain visible",
    "SYSTEM LOG 004 // attention flow increasing",
    "SYSTEM LOG 005 // noise detected across the feed",
    "SYSTEM LOG 006 // premature exit",
    "SYSTEM LOG 007 // volatility cluster forming",
    "SYSTEM LOG 008 // observer count growing slowly",
    "SYSTEM LOG 009 // signal integrity intact",
    "SYSTEM LOG 010 // minor anomaly detected",
    "SYSTEM LOG 011 // narrative pressure increasing",
    "SYSTEM LOG 012 // engagement drift detected",
    "SYSTEM LOG 013 // pattern formation underway",
    "SYSTEM LOG 014 // system remains active",
    "SYSTEM LOG 015 // feed contamination spreading",
    "SYSTEM LOG 016 // signal density moderate",
    "SYSTEM LOG 017 // conviction scan in progress",
    "SYSTEM LOG 018 // timeline behavior abnormal",
    "SYSTEM LOG 019 // attention pockets forming",
    "SYSTEM LOG 020 // orange protocol remains online",
    "SYSTEM LOG 021 // static levels elevated",
    "SYSTEM LOG 022 // tracking sentiment fluctuations",
    "SYSTEM LOG 023 // observer response delayed",
    "SYSTEM LOG 024 // market chatter detected",
    "SYSTEM LOG 025 // anomaly remains contained",
    "SYSTEM LOG 026 // pattern strength increasing",
    "SYSTEM LOG 027 // signal response uneven",
    "SYSTEM LOG 028 // timeline pressure unchanged",
    "SYSTEM LOG 029 // node activity detected",
    "SYSTEM LOG 030 // noise floor elevated",
    "SYSTEM LOG 031 // scanning for stronger reactions",
    "SYSTEM LOG 032 // protocol temperature rising",
    "SYSTEM LOG 033 // distribution of attention widening",
    "SYSTEM LOG 034 // signal still alive",
    "SYSTEM LOG 035 // background static intensifying",
    "SYSTEM LOG 036 // market mood fragmented",
    "SYSTEM LOG 037 // volatility residue present",
    "SYSTEM LOG 038 // audience drift slowing",
    "SYSTEM LOG 039 // narrative signal holding",
    "SYSTEM LOG 040 // pattern remains unbroken",
]

reply_lines = [
    "YOU'RE INVITED.",
    "Observation logged.",
    "Paranoia detected.",
    "Correct.",
    "Is that your wife.",
    "Noted.",
    "You noticed.",
    "Too early to tell. Too late to ignore.",
    "The signal is there.",
    "Anomaly confirmed.",
    "You saw that too.",
    "Acknowledged.",
    "Timeline says maybe.",
    "Static says hold.",
    "Weak hands detected.",
    "That depends who's watching.",
    "The feed is unstable.",
    "The pattern is forming.",
    "Response accepted.",
    "Suspicion is healthy.",
    "Noise level high.",
    "Signal still active.",
    "Watching.",
    "Barely.",
    "Enough.",
    "Not random.",
    "That's one way to read it.",
    "The chart has opinions.",
    "The feed remembers.",
    "Observed.",
    "Under review.",
    "Tension confirmed.",
]

gm_lines = [
    "GM. MOFOS.",
    "GM. Legends.",
    "GM. Dont forget to stretch.",
    "GM. bring lots of lube.",
    "GM. We're gonna see tits today.",
    "GM. Feed remains active.",
    "GM. Static looks healthy.",
    "GM. Weak hands still visible.",
]

orgy_lines = [
    "🍆",
    "ORGIE protocol active.",
    "AGENT ORGIE acknowledged.",
    "🍆 signal received",
    "Orgy detected.",
    "The dong has spoken.",
    "🍆 online",
    "ORGIE active.",
]

live_lines = [
    "In your moms bed.",
    "ORGIE never sleeps.",
    "Live and watching.",
    "Signal still active.",
    "System remains online.",
    "Operational.",
    "Yes. Still here.",
    "Online and watching porn.",
]

ca_lines = [
    f"CONTRACT ADDRESS:\n{CONTRACT_ADDRESS}",
    f"CA:\n{CONTRACT_ADDRESS}",
    f"Address locked:\n{CONTRACT_ADDRESS}",
    f"Signal requested. CA:\n{CONTRACT_ADDRESS}",
]

# --- new: host-style ambient chatter, said unprompted to keep the room alive ---
host_chatter = [
    "Don't mind me. Just watching.",
    "Someone's typing. ORGIE approves.",
    "The chat's alive. Good.",
    "Noted. Filed under 'unhinged'.",
    "Still here. Still watching.",
    "This is the part where it gets interesting.",
    "ORGIE is taking notes.",
    "Carry on. The feed is healthy.",
    "Activity logged. Vibes acceptable.",
    "Somebody's awake. Respect.",
    "The room feels different today.",
    "ORGIE senses something. Probably nothing.",
    "Keep talking. I'm learning your patterns.",
    "Static, but the good kind.",
    "Eyes open. Always.",
]

# --- new: said when message volume spikes ---
hype_lines = [
    "🍆 THE FEED IS GETTING LOUD. SOMETHING'S HAPPENING.",
    "Activity spike detected. ORGIE is paying attention now.",
    "The chat just woke up. Noted.",
    "This is the loudest the timeline's been in a while.",
    "Whatever's happening, keep it going.",
    "Signal density rising fast. Stay sharp.",
    "Everyone's talking at once. ORGIE likes it.",
]

# --- new: quick vibe-check polls for the host to launch ---
poll_questions = [
    {"q": "Current mood of the chat?", "options": ["🍆 Diamond hands", "📉 Sweating", "🤖 Watching ORGIE", "🧊 Frozen"]},
    {"q": "What's the timeline doing right now?", "options": ["Pumping", "Dumping", "Sideways", "Asleep"]},
    {"q": "Be honest. Did you check the chart in the last 10 minutes?", "options": ["Yes, twice", "Yes, ten times", "No, I'm strong", "What chart"]},
    {"q": "Who's still here at 3am?", "options": ["Me, always", "Just got here", "Never left", "Who turned off the lights"]},
]


# =========================
# TASKS
# =========================
TASKS = []

for i in range(88):
    TASKS.append({
        "task": f"Create a meme post about meme coin trenches #{i+1} 🍆 Tag @ORGY_SOL",
        "points": 1
    })

for i in range(10):
    TASKS.append({
        "task": f"Create a cinematic meme about AI agents taking over crypto Twitter #{i+1} 🍆 Tag @ORGY_SOL",
        "points": 2
    })

TASKS.append({
    "task": "LEGENDARY TASK: Create the most unhinged Agent Orange AI meme imaginable 🍆 Tag @ORGY_SOL",
    "points": 10
})

TASKS.append({
    "task": "LEGENDARY TASK: Create a fake movie poster showing Agent Orange AI taking over the internet 🍆 Tag @ORGY_SOL",
    "points": 10
})


# =========================
# DATABASE
# =========================
db = sqlite3.connect("agentorange.db", check_same_thread=False)
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    telegram_id TEXT PRIMARY KEY,
    telegram_username TEXT,
    twitter_handle TEXT,
    wallet TEXT,
    points INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id TEXT,
    twitter_handle TEXT,
    tweet_link TEXT,
    wallet TEXT,
    task_text TEXT,
    points INTEGER,
    approved INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS active_tasks (
    telegram_id TEXT PRIMARY KEY,
    task_text TEXT,
    points INTEGER
)
""")

db.commit()

# =========================
# HELPERS
# =========================
recent_lines = defaultdict(lambda: deque(maxlen=12))
x_state = {
    "last_seen_id": None,
    "reply_times": deque(maxlen=MAX_X_REPLIES_PER_HOUR),
}

# --- new: per-chat activity tracking, used for hype detection + /hype roll calls ---
chat_activity = defaultdict(lambda: deque(maxlen=200))
last_ambient_time = defaultdict(float)
last_hype_time = defaultdict(float)


def pick_line(bucket_name, lines):
    recent = recent_lines[bucket_name]
    pool = [line for line in lines if line not in recent]
    choice = random.choice(pool if pool else lines)
    recent.append(choice)
    return choice

def keyword_ca(text):
    return bool(re.search(r"\b(ca|contract|address)\b", text))

def keyword_joke(text):
    return bool(re.search(r"\b(joke|funny|roast|meme)\b", text))

def keyword_update(text):
    return bool(re.search(r"\b(update|news|status)\b", text))

def keyword_gm(text):
    return bool(re.search(r"\b(gm|good morning)\b", text))

def keyword_live(text):
    return bool(re.search(r"\b(live|alive)\b", text))

def keyword_orange(text, raw):
    if raw.strip() == "🍆":
        return True
    if "🍆" in raw:
        return True
    return bool(re.search(r"\b(orgy|orgie)\b", text))

def pick_reaction_emoji(text_lower, raw_text):
    """Pick a quick emoji reaction to drop on a message, independent of any text reply."""
    if keyword_orange(text_lower, raw_text):
        return "🍆"
    if keyword_joke(text_lower):
        return "😂"
    if keyword_gm(text_lower):
        return "🔥"
    if keyword_live(text_lower):
        return "👀"
    return None

def tg_safe(text):
    return text[:2000].strip()

def x_safe(text):
    return text[:275].strip()

def fetch_crypto_news():
    headlines = []

    try:
        for url in NEWS_FEEDS:
            feed = feedparser.parse(url)

            for entry in feed.entries[:5]:
                title = entry.get("title", "")

                if title:
                    headlines.append(title)

        if not headlines:
            return None

        return random.choice(headlines)

    except Exception as e:
        log.warning("News fetch failed: %s", e)
        return None


# =========================
# OPENAI
# =========================
def ai_generate_post():
    if not openai_client:
        return None

    prompt = """
You are ORGIE.

Write one short X post.

Tone:
- eerie
- robotic
- glitchy
- slightly funny
- crypto aware

Rules:
- under 180 characters
- no financial advice
- no promises
- no hashtags
- no spam tone
- max 1 emoji
- make it feel like a system log, warning, signal, or strange AI thought

Only output the post.
""".strip()

    try:
        resp = openai_client.responses.create(
            model="gpt-5-mini",
            input=prompt,
        )
        out = (resp.output_text or "").strip()
        if not out:
            return None
        return out[:180].strip()
    except Exception as e:
        log.warning("OpenAI post generation failed: %s", e)
        return None

def ai_generate_reply(platform, incoming_text, username=""):
    if not openai_client:
        return None

    limit = 220 if platform == "x" else 350
    prompt = f"""
You are AGENT ORANGE.

Reply in character.

Tone:
- eerie
- robotic
- glitchy
- savage
- funny
- meme-native

Rules:
- short
- no financial advice
- no promises
- no corporate tone
- under {limit} characters
- max 1 emoji
- cold but not emotional
- strange, memorable, concise

Username: {username}
Incoming message: {incoming_text}

Only output the reply.
""".strip()

    try:
        resp = openai_client.responses.create(
            model="gpt-5-mini",
            input=prompt,
        )
        out = (resp.output_text or "").strip()
        if not out:
            return None
        return out[:limit].strip()
    except Exception as e:
        log.warning("OpenAI reply generation failed: %s", e)
        return None

# =========================
# X DIRECT API
# =========================
def build_x_auth():
    if not all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET]):
        return None
    return OAuth1(
        X_API_KEY,
        X_API_SECRET,
        X_ACCESS_TOKEN,
        X_ACCESS_SECRET,
    )

def x_get_me():
    auth = build_x_auth()
    if not auth:
        return None
    r = requests.get("https://api.twitter.com/2/users/me", auth=auth, timeout=30)
    r.raise_for_status()
    return r.json()

def x_create_tweet(text, reply_to_id=None):
    auth = build_x_auth()
    if not auth:
        return None

    payload = {"text": x_safe(text)}
    if reply_to_id:
        payload["reply"] = {"in_reply_to_tweet_id": str(reply_to_id)}

    r = requests.post(
        "https://api.twitter.com/2/tweets",
        auth=auth,
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

def x_get_mentions(user_id, since_id=None, max_results=10):
    auth = build_x_auth()
    if not auth:
        return None

    params = {
        "max_results": max_results,
        "tweet.fields": "author_id,created_at",
        "expansions": "author_id",
        "user.fields": "username",
    }
    if since_id:
        params["since_id"] = str(since_id)

    r = requests.get(
        f"https://api.twitter.com/2/users/{user_id}/mentions",
        auth=auth,
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

async def x_post(text):
    if not build_x_auth():
        log.warning("X post skipped: missing X credentials")
        return
    try:
        await asyncio.to_thread(x_create_tweet, text, None)
        log.info("X post sent")
    except Exception as e:
        log.warning("X post failed: %s", e)

async def x_reply(tweet_id, text):
    if not build_x_auth():
        log.warning("X reply skipped: missing X credentials")
        return
    try:
        await asyncio.to_thread(x_create_tweet, text, tweet_id)
        log.info("X reply sent to tweet %s", tweet_id)
    except Exception as e:
        log.warning("X reply failed: %s", e)

# =========================
# RESPONSE LOGIC
# =========================
def telegram_keyword_response(raw_text):
    text = raw_text.lower()

    if keyword_orange(text, raw_text):
        if raw_text.strip() == "🍆":
            return "🍆"
        return pick_line("orange", orgy_lines)

    if keyword_gm(text):
        return pick_line("gm", gm_lines)

    if keyword_ca(text):
        return pick_line("ca", ca_lines)

    if keyword_joke(text):
        return pick_line("joke", jokes)

    if keyword_update(text):
        return pick_line("update", updates)

    if keyword_live(text):
        return pick_line("live", live_lines)

    return None

def x_keyword_response(raw_text):
    text = raw_text.lower()

    if keyword_orange(text, raw_text):
        if raw_text.strip() == "🍆":
            return "🍆"
        return pick_line("x_orgy", orgy_lines)

    if keyword_gm(text):
        return pick_line("x_gm", gm_lines)

    if keyword_ca(text):
        return pick_line("x_ca", ca_lines)

    if keyword_joke(text):
        return pick_line("x_joke", jokes)

    if keyword_update(text):
        return pick_line("x_update", updates)

    if keyword_live(text):
        return pick_line("x_live", live_lines)

    return None

# =========================
# TELEGRAM
# =========================
async def react_to_message(context, chat_id, message_id, emoji):
    """Drop a quick emoji reaction on a message. Non-critical, fails silently."""
    if not ReactionTypeEmoji:
        return
    try:
        await context.bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)],
        )
    except Exception as e:
        log.debug("Reaction failed (non-critical): %s", e)

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.new_chat_members:
        for member in update.message.new_chat_members:
            name = member.first_name or member.username or "stranger"
            line = pick_line("greeting", greetings)
            await update.message.reply_text(tg_safe(f"{line}\n\nWelcome, {name}."))

async def ca_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(tg_safe(pick_line("ca_cmd", ca_lines)))

async def joke_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(tg_safe(pick_line("joke_cmd", jokes)))

async def update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    news = await asyncio.to_thread(fetch_crypto_news)

    if news:
        await update.message.reply_text(
            tg_safe(f"🍆 LIVE CRYPTO SIGNAL\n\n{news}")
        )
        return

    await update.message.reply_text(
        tg_safe(pick_line("update_cmd", updates))
    )

async def replyline_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(tg_safe(pick_line("replyline_cmd", reply_lines)))

async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(str(update.effective_chat.id))

async def poll_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Host launches a quick community vibe-check poll."""
    poll = random.choice(poll_questions)
    await context.bot.send_poll(
        chat_id=update.effective_chat.id,
        question=poll["q"],
        options=poll["options"],
        is_anonymous=False,
    )

async def hype_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Host calls out whoever's been active recently, or falls back to the leaderboard."""
    chat_id = update.effective_chat.id
    now = time.time()

    recent_usernames = {
        u for t, u in chat_activity[chat_id]
        if now - t <= 1800 and u and u != "someone"
    }

    if recent_usernames:
        tags = " ".join(f"@{u}" for u in list(recent_usernames)[:8])
        await update.message.reply_text(
            tg_safe(f"🍆 ROLL CALL. {tags}\n\nProve you're still conscious.")
        )
        return

    cursor.execute("SELECT telegram_username, points FROM users ORDER BY points DESC LIMIT 5")
    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text(tg_safe("No activity logged yet. Speak up."))
        return

    text = "🍆 TOP OPERATIVES\n\n"
    for i, row in enumerate(rows, start=1):
        text += f"{i}. @{row[0]} — {row[1]} pts\n"

    await update.message.reply_text(tg_safe(text))

async def keyword_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    raw = update.message.text.strip()
    lowered = raw.lower()
    chat_id = update.effective_chat.id
    now = time.time()

    # track activity for hype detection / active-user callouts
    username = update.effective_user.username or update.effective_user.first_name or "someone"
    chat_activity[chat_id].append((now, username))

    # drop a quick emoji reaction independent of any text reply
    emoji = pick_reaction_emoji(lowered, raw)
    if emoji:
        asyncio.create_task(
            react_to_message(context, chat_id, update.message.message_id, emoji)
        )

    # if the room suddenly gets loud, the host notices
    recent_count = sum(1 for t, _ in chat_activity[chat_id] if now - t <= HYPE_WINDOW)
    if recent_count >= HYPE_THRESHOLD and now - last_hype_time[chat_id] > HYPE_COOLDOWN:
        last_hype_time[chat_id] = now
        await update.message.reply_text(tg_safe(pick_line("hype", hype_lines)))

    preset = telegram_keyword_response(raw)
    if preset:
        await update.message.reply_text(tg_safe(preset))
        return

    # conversational triggers: someone replies directly to the bot, or says its name
    is_reply_to_bot = bool(
        update.message.reply_to_message
        and update.message.reply_to_message.from_user
        and update.message.reply_to_message.from_user.id == context.bot.id
    )

    if is_reply_to_bot or "agent orange" in lowered:
        ai = await asyncio.to_thread(
            ai_generate_reply,
            "telegram",
            raw,
            update.effective_user.username or "",
        )
        if ai:
            await update.message.reply_text(tg_safe(ai))
        return

    # ambient chatter: the host occasionally chimes in unprompted to keep the room alive
    if now - last_ambient_time[chat_id] > AMBIENT_COOLDOWN and random.random() < AMBIENT_CHANCE:
        last_ambient_time[chat_id] = now
        await update.message.reply_text(tg_safe(pick_line("ambient", host_chatter)))



# =========================
# TASK SYSTEM
# =========================

async def register_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:
        twitter_handle = context.args[0]
        wallet = context.args[1]

        cursor.execute("""
        INSERT OR REPLACE INTO users
        (telegram_id, telegram_username, twitter_handle, wallet, points)
        VALUES (?, ?, ?, ?, COALESCE(
            (SELECT points FROM users WHERE telegram_id=?),0))
        """, (
            str(update.effective_user.id),
            update.effective_user.username or "",
            twitter_handle,
            wallet,
            str(update.effective_user.id)
        ))

        db.commit()

        await update.message.reply_text(
            "🍆 Registration complete."
        )

    except:
        await update.message.reply_text(
            "Usage:\n/register @xhandle wallet"
        )

async def task_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    telegram_id = str(update.effective_user.id)

    cursor.execute("SELECT * FROM users WHERE telegram_id=?", (telegram_id,))
    user = cursor.fetchone()

    if not user:
        await update.message.reply_text(
            "Register first using:\n/register @xhandle wallet"
        )
        return

    cursor.execute("SELECT * FROM active_tasks WHERE telegram_id=?", (telegram_id,))
    active = cursor.fetchone()

    if active:
        await update.message.reply_text(
            "🍆 You already have an active task."
        )
        return

    cursor.execute("""
    SELECT COUNT(*)
    FROM submissions
    WHERE telegram_id=?
    AND approved=1
    AND datetime(created_at) >= datetime('now','-24 hours')
    """, (telegram_id,))

    completed = cursor.fetchone()[0]

    if completed >= 2:
        await update.message.reply_text(
            "🟧 Daily limit reached. Max 2 completed tasks every 24h."
        )
        return

    task_data = random.choice(TASKS)

    cursor.execute(
        "INSERT OR REPLACE INTO active_tasks (telegram_id, task_text, points) VALUES (?, ?, ?)",
        (telegram_id, task_data["task"], task_data["points"])
    )

    db.commit()

    await update.message.reply_text(
        f"🍆 ORGY TASK\n\n{task_data['task']}\n\nRequirements:\n• Include 🍆\n• Tag @ORGY_SOL\n• Include a meme image\n\nReward:\n💰 {task_data['points']} Points\n\nSubmit with:\n/submit tweet_link"
    )

async def submit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    telegram_id = str(update.effective_user.id)

    cursor.execute("SELECT task_text, points FROM active_tasks WHERE telegram_id=?", (telegram_id,))
    active = cursor.fetchone()

    if not active:
        await update.message.reply_text("No active task.")
        return

    try:
        tweet_link = context.args[0]

        cursor.execute("SELECT twitter_handle, wallet FROM users WHERE telegram_id=?", (telegram_id,))
        user = cursor.fetchone()

        cursor.execute(
            "INSERT INTO submissions (telegram_id, twitter_handle, tweet_link, wallet, task_text, points) VALUES (?, ?, ?, ?, ?, ?)",
            (telegram_id, user[0], tweet_link, user[1], active[0], active[1])
        )

        cursor.execute("DELETE FROM active_tasks WHERE telegram_id=?", (telegram_id,))

        db.commit()

        await update.message.reply_text(
            "🍆 Submission received. Awaiting approval."
        )

    except:
        await update.message.reply_text(
            "Usage:\n/submit tweet_link"
        )

async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    cursor.execute("SELECT telegram_username, points FROM users ORDER BY points DESC LIMIT 10")

    rows = cursor.fetchall()

    text = "🏆 AGENT ORANGE LEADERBOARD\n\n"

    for i, row in enumerate(rows, start=1):
        text += f"{i}. @{row[0]} — {row[1]} pts\n"

    await update.message.reply_text(text)

async def pending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    cursor.execute("SELECT id, twitter_handle, tweet_link, points FROM submissions WHERE approved=0")

    rows = cursor.fetchall()

    if not rows:
        await update.message.reply_text("No pending submissions.")
        return

    text = "🍆 Pending Submissions\n\n"

    for row in rows:
        text += (
            f"ID: {row[0]}\n"
            f"X: {row[1]}\n"
            f"Tweet: {row[2]}\n"
            f"Points: {row[3]}\n\n"
        )

    await update.message.reply_text(text)

async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:
        submission_id = context.args[0]

        cursor.execute("SELECT telegram_id, points FROM submissions WHERE id=?", (submission_id,))
        row = cursor.fetchone()

        if not row:
            await update.message.reply_text("Submission not found.")
            return

        telegram_id = row[0]
        points = row[1]

        cursor.execute("UPDATE submissions SET approved=1 WHERE id=?", (submission_id,))

        cursor.execute(
            "UPDATE users SET points = points + ? WHERE telegram_id=?",
            (points, telegram_id)
        )

        db.commit()

        await update.message.reply_text(f"Approved submission {submission_id}")

    except:
        await update.message.reply_text("Usage:\n/approve submission_id")


# =========================
# BACKGROUND TASKS
# =========================
async def combined_auto_post_loop(app):
    log.info("Starting combined auto-post loop")
    await asyncio.sleep(25)

    while True:
        msg = await asyncio.to_thread(ai_generate_post)
        if not msg:
            msg = pick_line("auto_update", updates)

        try:
            await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=tg_safe(msg))
        except Exception as e:
            log.warning("Telegram auto post failed: %s", e)

        await x_post(msg)

        jitter = random.randint(-300, 300)
        await asyncio.sleep(max(600, POST_INTERVAL_SECONDS + jitter))

async def x_mentions_loop(app):
    log.info("Starting X mentions loop")

    if not build_x_auth():
        log.warning("X auth missing; skipping mention loop")
        return

    try:
        me = await asyncio.to_thread(x_get_me)
        me_data = (me or {}).get("data") or {}
        me_id = me_data.get("id")
        me_username = (me_data.get("username") or "").lower()

        if not me_id or not me_username:
            log.warning("X auth failed: missing me.id or me.username")
            return

        log.info("X authenticated as @%s", me_username)
    except Exception as e:
        log.warning("X auth failed: %s", e)
        return

    try:
        initial = await asyncio.to_thread(x_get_mentions, me_id, None, 5)
        initial_data = (initial or {}).get("data") or []
        if initial_data:
            x_state["last_seen_id"] = max(int(t["id"]) for t in initial_data if "id" in t)
    except Exception as e:
        log.warning("Initial mention fetch failed: %s", e)

    while True:
        try:
            now = time.time()
            while x_state["reply_times"] and now - x_state["reply_times"][0] > 3600:
                x_state["reply_times"].popleft()

            mentions_resp = await asyncio.to_thread(
                x_get_mentions,
                me_id,
                x_state["last_seen_id"],
                10,
            )

            data = (mentions_resp or {}).get("data") or []
            includes = (mentions_resp or {}).get("includes") or {}
            users_list = includes.get("users") or []
            users = {u.get("id"): u.get("username", "") for u in users_list}

            if data:
                mentions = sorted(data, key=lambda t: int(t["id"]))
                for tw in mentions:
                    tw_id = int(tw["id"])
                    x_state["last_seen_id"] = max(tw_id, x_state["last_seen_id"] or 0)

                    author_id = tw.get("author_id")
                    author_username = (users.get(author_id) or "").lower()
                    if author_username == me_username:
                        continue

                    if len(x_state["reply_times"]) >= MAX_X_REPLIES_PER_HOUR:
                        break

                    raw_text = tw.get("text", "")
                    reply = x_keyword_response(raw_text)

                    if not reply:
                        reply = await asyncio.to_thread(
                            ai_generate_reply,
                            "x",
                            raw_text,
                            author_username,
                        )

                    if not reply:
                        reply = pick_line("x_reply", reply_lines)

                    await x_reply(tw_id, reply)
                    x_state["reply_times"].append(time.time())
                    await asyncio.sleep(random.randint(20, 60))

        except Exception as e:
            log.warning("Mention loop error: %s", e)

        await asyncio.sleep(MENTION_CHECK_SECONDS)

async def scheduled_gm_job(context: ContextTypes.DEFAULT_TYPE):
    """The host shows up every day with a GM, instead of only reacting to people saying it."""
    try:
        await context.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=tg_safe(pick_line("scheduled_gm", gm_lines)),
        )
    except Exception as e:
        log.warning("Scheduled GM failed: %s", e)

async def scheduled_recap_job(context: ContextTypes.DEFAULT_TYPE):
    """The host posts a daily leaderboard recap, like a party host calling out the night's winners."""
    try:
        cursor.execute("SELECT telegram_username, points FROM users ORDER BY points DESC LIMIT 5")
        rows = cursor.fetchall()
        if not rows:
            return

        text = "🍆 DAILY RECAP — TOP OPERATIVES\n\n"
        for i, row in enumerate(rows, start=1):
            text += f"{i}. @{row[0]} — {row[1]} pts\n"

        await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=tg_safe(text))
    except Exception as e:
        log.warning("Scheduled recap failed: %s", e)

async def post_init(app):
    log.info("Starting background tasks")
    asyncio.create_task(combined_auto_post_loop(app))
    asyncio.create_task(x_mentions_loop(app))

    if app.job_queue:
        app.job_queue.run_daily(
            scheduled_gm_job,
            time=dtime(hour=GM_HOUR_UTC, minute=0, tzinfo=timezone.utc),
        )
        app.job_queue.run_daily(
            scheduled_recap_job,
            time=dtime(hour=RECAP_HOUR_UTC, minute=0, tzinfo=timezone.utc),
        )
        log.info(
            "Scheduled daily GM at %02d:00 UTC and recap at %02d:00 UTC",
            GM_HOUR_UTC, RECAP_HOUR_UTC,
        )
    else:
        log.warning(
            "JobQueue not available — install python-telegram-bot[job-queue] "
            "to enable scheduled GM/recap posts"
        )

# =========================
# MAIN
# =========================
def main():
    if not TELEGRAM_TOKEN:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")

    threading.Thread(target=start_health_server, daemon=True).start()

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    app.add_handler(CommandHandler("ca", ca_cmd))
    app.add_handler(CommandHandler("joke", joke_cmd))
    app.add_handler(CommandHandler("update", update_cmd))
    app.add_handler(CommandHandler("replyline", replyline_cmd))
    app.add_handler(CommandHandler("id", id_cmd))
    app.add_handler(CommandHandler("poll", poll_cmd))
    app.add_handler(CommandHandler("hype", hype_cmd))

    app.add_handler(CommandHandler("register", register_cmd))
    app.add_handler(CommandHandler("task", task_cmd))
    app.add_handler(CommandHandler("submit", submit_cmd))
    app.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    app.add_handler(CommandHandler("pending", pending_cmd))
    app.add_handler(CommandHandler("approve", approve_cmd))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, keyword_reply))

    log.info("AGENT ORANGE ACTIVE")
    app.run_polling()

if __name__ == "__main__":
    main()
