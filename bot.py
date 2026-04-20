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
    with sqlite3.connect("diagnostic.db") as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, phone TEXT)''')
        conn.commit()

def db_manage_user(user_id, phone=None):
    with sqlite3.connect("diagnostic.db") as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        if phone:
            c.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
        conn.commit()
        return c.execute("SELECT phone FROM users WHERE user_id = ?", (user_id,)).fetchone()

# --- РОБОТА З POSTER API (ЗМІНЕНО НА GET) ---

def create_poster_client(phone_number, name, chat_id):
    if not POSTER_TOKEN:
        bot.send_message(chat_id, "❌ POSTER_TOKEN пустий!")
        return None

    # Очищуємо номер до формату 380...
    clean_phone = re.sub(r'\D', '', phone_number)
    
    # 1. Спершу дізнаємось ID групи
    group_id = 1
    try:
        g_res = requests.get(f"{POSTER_API_URL}/clients.getGroups", params={"token": POSTER_TOKEN}).json()
        if g_res.get("response") and len(g_res["response"]) > 0:
            group_id = g_res["response"][0]["client_groups_id_client"]
    except: pass

    # 2. Використовуємо GET запит для setClient (вирішення помилки 30)
    url = f"{POSTER_API_URL}/clients.setClient"
    
    payload = {
        "token": POSTER_TOKEN,
        "client_name": name or "Клієнт Telegram",
        "phone": clean_phone,
        "client_groups_id_client": group_id,
        "client_sex": 0,
        "bonus": 0
    }

    try:
        # ВАЖЛИВО: requests.get замість post
        response = requests.get(url, params=payload)
        res = response.json()
        
        bot.send_message(chat_id, f"🛠 Debug (GET method): `{res}`", parse_mode="Markdown")

        if res.get("error"):
            # Якщо клієнт вже є
            if res["error"] == 34 or (isinstance(res["error"], dict) and res["error"].get("code") == 34):
                bot.send_message(chat_id, "ℹ️ Клієнт уже був у базі Poster, просто підключили.")
                return True
            return None
        
        return res.get("response")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Помилка: {e}")
    return None

# --- КОМАНДИ ---

@bot.message_handler(commands=['reset'])
def reset(message):
    with sqlite3.connect("diagnostic.db") as conn:
        conn.cursor().execute("UPDATE users SET phone = NULL WHERE user_id = ?", (message.chat.id,))
    bot.send_message(message.chat.id, "♻️ Номер скинуто. Спробуйте 'Профіль' знову.")

@bot.message_handler(func=lambda m: m.text == "👤 Профіль")
def profile(message):
    user = db_manage_user(message.chat.id)
    if not user[0]:
        m = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        m.add(types.KeyboardButton("📱 Надіслати контакт", request_contact=True))
        return bot.send_message(message.chat.id, "Надішліть контакт:", reply_markup=m)
    
    bot.send_message(message.chat.id, "🔍 Перевірка в Poster...")
    # Шукаємо клієнта для виводу балансу
    clean_phone = re.sub(r'\D', '', user[0])
    res = requests.get(f"{POSTER_API_URL}/clients.getClients", params={"token": POSTER_TOKEN, "search": clean_phone}).json()
    
    if res.get("response") and len(res["response"]) > 0:
        c = res["response"][0]
        bot.send_message(message.chat.id, f"✅ Твій кабінет!\n👤 {c['client_name']}\n💰 Бонуси: {int(float(c['bonus']))} грн")
    else:
        bot.send_message(message.chat.id, "❌ Не знайдено в Poster. Натисни /reset")

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    phone = message.contact.phone_number
    db_manage_user(message.chat.id, phone=phone)
    bot.send_message(message.chat.id, "⏳ Реєстрація (Метод GET)...")
    create_poster_client(phone, message.from_user.first_name, message.chat.id)
    profile(message)

@bot.message_handler(commands=['start'])
def start(message):
    db_manage_user(message.chat.id)
    bot.send_message(message.chat.id, "Діагностика Poster (GET). Натисни Профіль.", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("👤 Профіль"))

if __name__ == "__main__":
    init_db()
    bot.infinity_polling()

