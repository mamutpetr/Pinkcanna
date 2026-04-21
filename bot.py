import telebot
from telebot import types
import os
import sqlite3
import re
import requests
import time

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

# --- POSTER REQUEST (MAX DEBUG) ---
def poster_request(endpoint, method="GET", data=None):
    url = f"{POSTER_API_URL}/{endpoint}"

    if not data:
        data = {}

    # Токен завжди передається в URL (query parameters)
    params = {"token": POSTER_TOKEN}

    try:
        print("\n===== POSTER REQUEST =====")
        print("URL:", url)
        print("METHOD:", method)
        print("PARAMS:", params)
        print("DATA (JSON):", data)

        if method == "GET":
            # Для GET запитів об'єднуємо токен та інші параметри в URL
            merged_params = {**params, **data}
            res = requests.get(url, params=merged_params, timeout=10)
        else:
            # Для POST запитів токен в URL, а дані - в тілі як JSON
            res = requests.post(url, params=params, json=data, timeout=10)

        print("STATUS:", res.status_code)
        print("TEXT:", res.text)

        try:
            return res.json()
        except:
            print("❌ НЕ JSON ВІДПОВІДЬ")
            return None

    except Exception as e:
        print("❌ EXCEPTION:", e)
        return None

# --- CLIENT CREATE ---
def create_poster_client(phone, name, chat_id):
    phone = normalize_phone(phone)

    payload = {
        "client_name": name or "Telegram Client",
        "phone": phone,
        "client_groups_id_client": 1, # Група за замовчуванням
        "client_sex": 0
    }

    # Використовуємо clients.createClient для REST API
    res = poster_request("clients.createClient", "POST", payload)

    if not res:
        bot.send_message(chat_id, "❌ Poster не відповідає (дивись консоль)")
        return

    if "error" in res:
        error_data = res["error"]
        
        # Обробка формату помилки Poster (може бути dict або int)
        if isinstance(error_data, dict):
            code = error_data.get("code")
            message = error_data.get("message", "Невідома помилка")
        else:
            code = error_data
            message = "Клієнт з таким телефоном вже існує або помилка валідації"

        if code == 34:
            bot.send_message(chat_id, "✅ Ви вже є в системі")
            return

        bot.send_message(chat_id, f"⚠️ Poster error {code}: {message}")
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
    res = poster_request("clients.getGroups", "GET")

    if res and "error" not in res:
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
    bot.send_message(message.chat.id, "📥 Номер отримано")

    create_poster_client(phone, message.from_user.first_name, message.chat.id)

# --- START ---
if __name__ == "__main__":
    init_db()
    print("🚀 Бот запущений")
    bot.infinity_polling()

