import telebot
from telebot import types
import os
import sqlite3
import re
import requests

# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv("BOT_TOKEN")
POSTER_TOKEN = os.getenv("POSTER_TOKEN")
POSTER_API_URL = "https://joinposter.com/api"

bot = telebot.TeleBot(TOKEN)

# --- БАЗА ДАНИХ ---
def init_db():
    with sqlite3.connect("pink_fix.db") as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                phone TEXT
            )
        ''')

def db_manage_user(user_id, phone=None):
    with sqlite3.connect("pink_fix.db") as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        if phone:
            c.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
        conn.commit()
        return c.execute("SELECT phone FROM users WHERE user_id = ?", (user_id,)).fetchone()

# --- УТИЛІТИ ---
def normalize_phone(phone):
    clean = re.sub(r'\D', '', phone)

    if clean.startswith("380"):
        return clean
    elif clean.startswith("0"):
        return "380" + clean[1:]
    elif clean.startswith("80"):
        return "3" + clean
    return clean

# --- POSTER API ---
def get_client_group():
    try:
        res = requests.get(
            f"{POSTER_API_URL}/clients.getGroups",
            params={"token": POSTER_TOKEN},
            timeout=10
        ).json()

        if res.get("response"):
            return res["response"][0]["client_groups_id_client"]
    except Exception as e:
        print("Group error:", e)

    return 1


def create_poster_client(phone_number, name, chat_id):
    if not POSTER_TOKEN:
        bot.send_message(chat_id, "❌ POSTER_TOKEN відсутній")
        return

    phone = normalize_phone(phone_number)
    group_id = get_client_group()

    payload = {
        "token": POSTER_TOKEN,
        "client_name": name or "Telegram Client",
        "phone": phone,
        "client_groups_id_client": group_id,
        "client_sex": 0
    }

    try:
        response = requests.post(
            f"{POSTER_API_URL}/clients.setClient",
            data=payload,
            timeout=10
        )

        if response.status_code != 200:
            bot.send_message(chat_id, f"❌ HTTP {response.status_code}\n{response.text}")
            return

        res = response.json()

        print("Poster response:", res)

        # --- ОБРОБКА ---
        if "error" in res:
            error_code = res["error"]

            if error_code == 34:
                bot.send_message(chat_id, "✅ Ви вже є в системі")
                return True

            bot.send_message(chat_id, f"⚠️ Poster error: {error_code}")
            return

        bot.send_message(chat_id, "✅ Реєстрація успішна!")
        return res.get("response")

    except requests.exceptions.Timeout:
        bot.send_message(chat_id, "⏱ Таймаут запиту до Poster")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Помилка: {e}")

# --- ХЕНДЛЕРИ ---
@bot.message_handler(commands=['start'])
def start(message):
    db_manage_user(message.chat.id)

    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.add(types.KeyboardButton("👤 Мій профіль"))

    bot.send_message(
        message.chat.id,
        "Вітаємо! Натисніть кнопку нижче 👇",
        reply_markup=m
    )

@bot.message_handler(commands=['reset'])
def reset(message):
    with sqlite3.connect("pink_fix.db") as conn:
        conn.execute(
            "UPDATE users SET phone = NULL WHERE user_id = ?",
            (message.chat.id,)
        )

    bot.send_message(message.chat.id, "♻️ Дані очищено")

@bot.message_handler(func=lambda m: m.text == "👤 Мій профіль")
def profile(message):
    user = db_manage_user(message.chat.id)

    if not user or not user[0]:
        m = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        m.add(types.KeyboardButton("📱 Поділитися контактом", request_contact=True))

        bot.send_message(
            message.chat.id,
            "📲 Надішліть номер телефону",
            reply_markup=m
        )
        return

    bot.send_message(message.chat.id, "🔍 Перевіряю в Poster...")
    create_poster_client(user[0], message.from_user.first_name, message.chat.id)

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    phone = message.contact.phone_number

    db_manage_user(message.chat.id, phone=phone)

    bot.send_message(message.chat.id, "📥 Номер отримано")
    create_poster_client(phone, message.from_user.first_name, message.chat.id)

# --- ЗАПУСК ---
if __name__ == "__main__":
    init_db()
    print("Бот працює...")
    bot.infinity_polling()
