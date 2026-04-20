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
        conn.cursor().execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, phone TEXT)')
        conn.commit()

def db_manage_user(user_id, phone=None):
    with sqlite3.connect("pink_fix.db") as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        if phone:
            c.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
        conn.commit()
        return c.execute("SELECT phone FROM users WHERE user_id = ?", (user_id,)).fetchone()

# --- РОБОТА З POSTER API (СУВОРИЙ POST) ---

def create_poster_client(phone_number, name, chat_id):
    if not POSTER_TOKEN:
        bot.send_message(chat_id, "❌ POSTER_TOKEN не знайдено!")
        return None

    # 1. Отримуємо ID групи (GET запит для отримання списку)
    group_id = 1
    try:
        g_res = requests.get(f"{POSTER_API_URL}/clients.getGroups", params={"token": POSTER_TOKEN}).json()
        if g_res.get("response"):
            group_id = g_res["response"][0]["client_groups_id_client"]
    except: pass

    # 2. Формуємо URL з токеном (Poster вимагає токен саме в URL)
    url = f"{POSTER_API_URL}/clients.setClient?token={POSTER_TOKEN}"
    
    # 3. Дані клієнта для тіла запиту
    client_data = {
        "client_name": name or "Клієнт Telegram",
        "phone": re.sub(r'\D', '', phone_number), # Тільки цифри
        "client_groups_id_client": group_id,
        "client_sex": 0
    }

    try:
        # ВАЖЛИВО: Використовуємо POST, дані передаємо через data= (application/x-www-form-urlencoded)
        # Це те, що Poster очікує за замовчуванням
        response = requests.post(url, data=client_data)
        res = response.json()
        
        bot.send_message(chat_id, f"🛠 Debug (Explicit POST): `{res}`", parse_mode="Markdown")

        if res.get("error"):
            # Помилка 34 - клієнт уже є. Це успіх для нас.
            if res["error"] == 34 or (isinstance(res["error"], dict) and res["error"].get("code") == 34):
                return True
            return None
            
        return res.get("response")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Помилка зв'язку: {e}")
    return None

# --- ХЕНДЛЕРИ ---

@bot.message_handler(commands=['start'])
def start(message):
    db_manage_user(message.chat.id)
    m = types.ReplyKeyboardMarkup(resize_keyboard=True).add("👤 Профіль")
    bot.send_message(message.chat.id, "Бот у режимі Explicit POST. Натисніть Профіль.", reply_markup=m)

@bot.message_handler(commands=['reset'])
def reset(message):
    with sqlite3.connect("pink_fix.db") as conn:
        conn.cursor().execute("UPDATE users SET phone = NULL WHERE user_id = ?", (message.chat.id,))
    bot.send_message(message.chat.id, "♻️ Номер видалено. Спробуйте ще раз.")

@bot.message_handler(func=lambda m: m.text == "👤 Профіль")
def profile(message):
    user = db_manage_user(message.chat.id)
    if not user[0]:
        m = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        m.add(types.KeyboardButton("📱 Надіслати контакт", request_contact=True))
        return bot.send_message(message.chat.id, "Надішліть номер для перевірки Poster:", reply_markup=m)
    
    bot.send_message(message.chat.id, "🔍 Роблю POST запит до Poster...")
    create_poster_client(user[0], message.from_user.first_name, message.chat.id)

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    db_manage_user(message.chat.id, phone=message.contact.phone_number)
    profile(message)

if __name__ == "__main__":
    init_db()
    bot.infinity_polling()

