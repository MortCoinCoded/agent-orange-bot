import os
import re
import time
import json
import asyncio
import random
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections import defaultdict, deque

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
    "🚨 AGENT ORANGE detected a new presence. Welcome to the timeline.",
    "New signal received. Welcome to AGENT ORANGE.",
    "System notice: a new user has entered the zone. Welcome.",
    "Welcome to the feed. Stay sharp. Stay weird.",
    "Entry confirmed. You are now inside AGENT ORANGE territory.",
    "Another observer has arrived. Welcome to the anomaly.",
    "Signal locked. Welcome to the operation.",
    "Timeline breach confirmed. New member accepted.",
    "You found the signal. Welcome in.",
    "AGENT ORANGE sees you. Welcome.",
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
    "You’re in. Try not to blink.",
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
    "You’ve entered the system. Welcome.",
    "New participant detected. Welcome to the loop.",
]

jokes = [
    "Weak hands detected.",
    "Retail waking up on dial-up speed.",
    "The chart called. It said breathe.",
    "Bullish on confusion.",
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
    "Bulls are back until they aren’t.",
    "This timeline runs on cope and caffeine.",
    "Support level held together by delusion.",
    "Everybody wants the moon, nobody wants the chop.",
    "Paranoia is just research wearing sunglasses.",
    "Another candle, another prophet.",
    "The bag is heavy because the conviction is fake.",
    "Exit liquidity applying for overtime.",
    "This feed is 30% alpha and 70% theater.",
    "Some people study charts. Others study vibes.",
    "One green candle and suddenly everyone’s a founder.",
    "The market loves humility. Nobody else does.",
    "You can’t spell conviction without getting wrecked first.",
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
    "Today’s strategy: survive your own confidence.",
    "The trend is your friend until you marry the candle.",
    "That wasn’t a pump. That was optimism tripping.",
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
    "SYSTEM LOG 001 // signal stability: nominal",
    "SYSTEM LOG 002 // timeline distortion rising",
    "SYSTEM LOG 003 // weak hands remain visible",
    "SYSTEM LOG 004 // attention flow increasing",
    "SYSTEM LOG 005 // noise detected across the feed",
    "SYSTEM LOG 006 // market pulse unstable",
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
    "Signal received.",
    "Observation logged.",
    "Paranoia detected.",
    "Correct.",
    "Acceptable response.",
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
    "That depends who’s watching.",
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
    "That’s one way to read it.",
    "The chart has opinions.",
    "The feed remembers.",
    "Observed.",
    "Under review.",
    "Tension confirmed.",
]

gm_lines = [
    "GM. Signal active.",
    "GM. Orange protocol online.",
    "GM. Timeline still unstable.",
    "GM. Stay sharp.",
    "GM. Another scan begins.",
    "GM. Feed remains active.",
    "GM. Static looks healthy.",
    "GM. Weak hands still visible.",
]

orange_lines = [
    "🟧",
    "Orange protocol active.",
    "AGENT ORANGE acknowledged.",
    "🟧 signal received",
    "Orange detected.",
    "The orange square has spoken.",
    "🟧 online",
    "Orange layer active.",
]

live_lines = [
    "Still live.",
    "AGENT ORANGE remains online.",
    "Live and watching.",
    "Signal still active.",
    "System remains online.",
    "Operational.",
    "Yes. Still here.",
    "Online and scanning.",
]

ca_lines = [
    f"CONTRACT ADDRESS:\n{CONTRACT_ADDRESS}",
    f"CA:\n{CONTRACT_ADDRESS}",
    f"Address locked:\n{CONTRACT_ADDRESS}",
    f"Signal requested. CA:\n{CONTRACT_ADDRESS}",
]

# =========================
# HELPERS
# =========================
recent_lines = defaultdict(lambda: deque(maxlen=12))
x_state = {
    "last_seen_id": None,
    "reply_times": deque(maxlen=MAX_X_REPLIES_PER_HOUR),
}

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
    if raw.strip() == "🟧":
        return True
    if "🟧" in raw:
        return True
    return bool(re.search(r"\b(agent orange|orange)\b", text))

def tg_safe(text):
    return text[:2000].strip()

def x_safe(text):
    return text[:275].strip()

# =========================
# OPENAI
# =========================
def ai_generate_post():
    if not openai_client:
        return None

    prompt = """
You are AGENT ORANGE.

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
        if raw_text.strip() == "🟧":
            return "🟧"
        return pick_line("orange", orange_lines)

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
        if raw_text.strip() == "🟧":
            return "🟧"
        return pick_line("x_orange", orange_lines)

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
async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.new_chat_members:
        for _ in update.message.new_chat_members:
            await update.message.reply_text(tg_safe(pick_line("greeting", greetings)))

async def ca_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(tg_safe(pick_line("ca_cmd", ca_lines)))

async def joke_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(tg_safe(pick_line("joke_cmd", jokes)))

async def update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(tg_safe(pick_line("update_cmd", updates)))

async def replyline_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(tg_safe(pick_line("replyline_cmd", reply_lines)))

async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(str(update.effective_chat.id))

async def keyword_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    raw = update.message.text.strip()
    preset = telegram_keyword_response(raw)
    if preset:
        await update.message.reply_text(tg_safe(preset))
        return

    lowered = raw.lower()
    if "agent orange" in lowered:
        ai = await asyncio.to_thread(
            ai_generate_reply,
            "telegram",
            raw,
            update.effective_user.username or "",
        )
        if ai:
            await update.message.reply_text(tg_safe(ai))

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
                    tw_id = int(t["id"])
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

async def post_init(app):
    log.info("Starting background tasks")
    asyncio.create_task(combined_auto_post_loop(app))
    asyncio.create_task(x_mentions_loop(app))

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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, keyword_reply))

    log.info("AGENT ORANGE ACTIVE")
    app.run_polling()

if __name__ == "__main__":
    main()
