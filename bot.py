import os
import json
import html
import logging
from flask import Flask, request, jsonify
import requests

# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

LINK_EXPIRE_SECONDS = int(os.getenv("LINK_EXPIRE_SECONDS", "600"))

# Example:
# {
#   "Black Clover": {
#       "channel_id": "-1001234567890",
#       "poster": "https://example.com/blackclover.jpg"
#   }
# }
try:
    ANIME_CHANNELS = json.loads(
        os.getenv("ANIME_CHANNELS", "{}")
    )
except Exception:
    ANIME_CHANNELS = {}

PORT = int(os.getenv("PORT", "10000"))

# =========================
# APP
# =========================

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# =========================
# TELEGRAM API
# =========================

def telegram(method, data=None):

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")

    response = requests.post(
        f"{API}/{method}",
        json=data or {},
        timeout=30
    )

    response.raise_for_status()

    result = response.json()

    if not result.get("ok"):
        raise RuntimeError(result)

    return result["result"]


# =========================
# SEND MESSAGE
# =========================

def send_message(chat_id, text, keyboard=None):

    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }

    if keyboard:
        data["reply_markup"] = keyboard

    return telegram("sendMessage", data)


# =========================
# SEND PHOTO
# =========================

def send_photo(chat_id, photo, caption, keyboard=None):

    data = {
        "chat_id": chat_id,
        "photo": photo,
        "caption": caption,
        "parse_mode": "HTML"
    }

    if keyboard:
        data["reply_markup"] = keyboard

    return telegram("sendPhoto", data)


# =========================
# FIND ANIME
# =========================

def find_anime(search):

    search = search.strip().casefold()

    for anime_name, config in ANIME_CHANNELS.items():

        if search == anime_name.strip().casefold():
            return anime_name, config

    return None, None


# =========================
# CREATE TEMP LINK
# =========================

def create_channel_link(channel_id):

    expire_date = int(__import__("time").time()) + LINK_EXPIRE_SECONDS

    result = telegram(
        "createChatInviteLink",
        {
            "chat_id": channel_id,

            # User sends join request
            "creates_join_request": True,

            # Automatically expires
            "expire_date": expire_date
        }
    )

    return result["invite_link"]


# =========================
# SEND ANIME
# =========================

def send_anime(chat_id, anime_name, config):

    channel_id = str(
        config.get("channel_id", "")
    ).strip()

    poster = str(
        config.get("poster", "")
    ).strip()

    if not channel_id:

        send_message(
            chat_id,
            "❌ Channel is not configured for this anime."
        )

        return

    try:

        invite_link = create_channel_link(channel_id)

    except Exception as error:

        logger.exception(
            "Failed to create invite link: %s",
            error
        )

        send_message(
            chat_id,
            "❌ I couldn't create the channel link.\n\n"
            "Please contact the bot administrator."
        )

        return

    minutes = LINK_EXPIRE_SECONDS // 60

    safe_name = html.escape(anime_name)

    caption = (
        f"🎬 <b>{safe_name}</b>\n\n"
        f"🔗 <b>Open Channel</b>\n"
        f"⏳ Link expires in {minutes} minutes"
    )

    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "🔗 Open Channel",
                    "url": invite_link
                }
            ]
        ]
    }

    # Poster available
    if poster:

        try:

            send_photo(
                chat_id,
                poster,
                caption,
                keyboard
            )

            return

        except Exception as error:

            logger.warning(
                "Poster failed: %s",
                error
            )

    # No poster / poster failed
    send_message(
        chat_id,
        caption,
        keyboard
    )


# =========================
# ADMIN COMMAND
# =========================

def is_admin(user_id):

    return user_id in ADMIN_IDS


# =========================
# HANDLE UPDATE
# =========================

def handle_update(update):

    message = update.get("message")

    if not message:
        return

    chat = message.get("chat")

    if not chat:
        return

    chat_id = chat["id"]

    user = message.get("from", {})

    user_id = user.get("id")

    text = message.get("text", "").strip()

    if not text:
        return

    # =====================
    # START
    # =====================

    if text.startswith("/start"):

        send_message(
            chat_id,
            "👋 <b>Welcome to Anime Channel Assistant!</b>\n\n"
            "🎬 Send an anime name.\n\n"
            "Example:\n"
            "<code>Black Clover</code>"
        )

        return

    # =====================
    # HELP
    # =====================

    if text.startswith("/help"):

        send_message(
            chat_id,
            "🎬 <b>How to use</b>\n\n"
            "Simply send an anime name.\n"
            "Example: <code>Black Clover</code>\n\n"
            "🔗 You will receive a temporary channel link."
        )

        return

    # =====================
    # ADMIN STATUS
    # =====================

    if text.startswith("/admin"):

        if not is_admin(user_id):

            send_message(
                chat_id,
                "❌ You are not an administrator."
            )

            return

        send_message(
            chat_id,
            "👑 <b>Admin Access</b>\n\n"
            "You have administrator access."
        )

        return

    # =====================
    # ANIME SEARCH
    # =====================

    anime_name, config = find_anime(text)

    if anime_name:

        # IMPORTANT:
        # NO ADMIN CHECK HERE.
        #
        # Every user can request an anime link.

        send_anime(
            chat_id,
            anime_name,
            config
        )

        return

    # =====================
    # NOT FOUND
    # =====================

    available = list(ANIME_CHANNELS.keys())

    if available:

        names = "\n".join(
            f"• {html.escape(name)}"
            for name in available
        )

        send_message(
            chat_id,
            "❌ <b>Anime Not Found</b>\n\n"
            "Available anime:\n\n"
            f"{names}"
        )

    else:

        send_message(
            chat_id,
            "⚠️ No anime channels are configured yet."
        )


# =========================
# WEBHOOK
# =========================

@app.route("/webhook", methods=["POST"])
def webhook():

    if WEBHOOK_SECRET:

        received_secret = request.headers.get(
            "X-Telegram-Bot-Api-Secret-Token",
            ""
        )

        if received_secret != WEBHOOK_SECRET:

            return jsonify({
                "ok": False,
                "error": "Unauthorized"
            }), 403

    update = request.get_json(
        silent=True
    )

    if update:

        try:

            handle_update(update)

        except Exception:

            logger.exception(
                "Update processing failed"
            )

    return jsonify({
        "ok": True
    })


# =========================
# HEALTH CHECK
# =========================

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "status": "online",
        "bot": "Anime Channel Assistant",
        "link_expiry": LINK_EXPIRE_SECONDS
    })


# =========================
# SET WEBHOOK
# =========================

def setup_webhook():

    if not WEBHOOK_URL:
        logger.warning(
            "WEBHOOK_URL is not configured."
        )
        return

    webhook_url = f"{WEBHOOK_URL}/webhook"

    data = {
        "url": webhook_url
    }

    if WEBHOOK_SECRET:

        data["secret_token"] = WEBHOOK_SECRET

    result = telegram(
        "setWebhook",
        data
    )

    logger.info(
        "Webhook result: %s",
        result
    )


# =========================
# START
# =========================

if __name__ == "__main__":

    if BOT_TOKEN:

        try:
            setup_webhook()

        except Exception:

            logger.exception(
                "Webhook setup failed"
            )

    else:

        logger.error(
            "BOT_TOKEN is missing!"
        )

    app.run(
        host="0.0.0.0",
        port=PORT
      )
