import telebot
from telebot import types
import os
import sqlite3
import re
import requests
import time
import logging

# --- LOGGING ---
logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# --- ENV ---
TOKEN = os.getenv("BOT_TOKEN")
POSTER_TOKEN = os.getenv("POSTER_TOKEN")
POSTER_API_URL = "https://joinposter.com/api"

if not TOKEN:
    raise Exception("❌ BOT_TOKEN не заданий")

if not POSTER_TOKEN:
    raise Exception("❌ POSTER_TOKEN не заданий")

bot = telebot.TeleBot(TOKEN)

# --- DB ---
def init_db():
    with sqlite3.connect("pink_fix.db") as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                phone TEXT
            )
        """)

def db_manage_user(user_id, phone=None):
    with sqlite3.connect("pink_fix.db") as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        if phone:
            c.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
        conn.commit()
        return c.execute("SELECT phone FROM users WHERE user_id = ?", (user_id,)).fetchone()

# --- UTILS ---
def normalize_phone(phone):
    clean = re.sub(r'\D', '', phone)

    if clean.startswith("380"):
        return clean
    elif clean.startswith("0"):
        return "380" + clean[1:]
    return clean

# --- POSTER API CORE ---
def poster_request(endpoint, method="GET", data=None, retries=3):
    url = f"{POSTER_API_URL}/{endpoint}"

    for attempt in range(retries):
        try:
            if method == "GET":
                res = requests.get(url, params=data, timeout=10)
            else:
                res = requests.post(url, data=data, timeout=10)

            if res.status_code != 200:
                logging.error(f"HTTP {res.status_code}: {res.text}")
                time.sleep(1)
                continue

            return res.json()

        except Exception as e:
            logging.error(f"Request error: {e}")
            time.sleep(1)

    return None

# --- HEALTH CHECK ---
def check_poster():
    res = poster_request("clients.getGroups", "GET", {"token": POSTER_TOKEN})

    if not res:
        return False

    if "error" in res:
        logging.error(f"Poster error: {res}")
        return False

    return True

# --- CLIENT CREATE ---
def create_poster_client(phone, name, chat_id):
    phone = normalize_phone(phone)

    payload = {
        "token": POSTER_TOKEN,
        "client_name": name or "Telegram Client",
        "phone": phone,
        "client_sex": 0
    }

    res = poster_request("clients.setClient", "POST", payload)

    if not res:
        bot.send_message(chat_id, "❌ Poster не відповідає")
        return

    logging.info(f"Poster response: {res}")

    if "error" in res:
        code = res["error"]

        if code == 34:
            bot.send_message(chat_id, "✅ Ви вже є в системі")
            return True

        bot.send_message(chat_id, f"⚠️ Poster error: {code}")
        return

    bot.send_message(chat_id, "✅ Реєстрація успішна!")

# --- HANDLERS ---
@bot.message_handler(commands=['start'])
def start(message):
    db_manage_user(message.chat.id)

    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.add(types.KeyboardButton("👤 Мій профіль"))

    bot.send_message(message.chat.id, "🚀 Бот працює", reply_markup=m)

@bot.message_handler(commands=['health'])
def health(message):
    if check_poster():
        bot.send_message(message.chat.id, "🟢 Poster OK")
    else:
        bot.send_message(message.chat.id, "🔴 Poster DOWN")

@bot.message_handler(commands=['reset'])
def reset(message):
    with sqlite3.connect("pink_fix.db") as conn:
        conn.execute("UPDATE users SET phone = NULL WHERE user_id = ?", (message.chat.id,))

    bot.send_message(message.chat.id, "♻️ Дані очищено")

@bot.message_handler(func=lambda m: m.text == "👤 Мій профіль")
def profile(message):
    user = db_manage_user(message.chat.id)

    if not user or not user[0]:
        m = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        m.add(types.KeyboardButton("📱 Поділитися контактом", request_contact=True))

        bot.send_message(message.chat.id, "📲 Надішліть номер", reply_markup=m)
        return

    create_poster_client(user[0], message.from_user.first_name, message.chat.id)

@bot.message_handler(content_types=['contact'])
def contact(message):
    phone = message.contact.phone_number

    db_manage_user(message.chat.id, phone)
    create_poster_client(phone, message.from_user.first_name, message.chat.id)

# --- STARTUP ---
if __name__ == "__main__":
    init_db()

    print("🚀 Запуск бота...")

    if not check_poster():
        print("❌ Poster API недоступний або токен неправильний")
    else:
        print("✅ Poster OK")

    bot.infinity_polling()
