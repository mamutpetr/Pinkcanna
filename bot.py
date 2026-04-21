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

# --- РОБОТА З POSTER API ---

def create_poster_client(phone_number, name, chat_id):
    if not POSTER_TOKEN:
        bot.send_message(chat_id, "❌ POSTER_TOKEN не знайдено в системних змінних!")
        return None

    # Очищення номера телефону (тільки цифри)
    clean_phone = re.sub(r'\D', '', phone_number)

    # 1. Спроба отримати групу клієнтів (за замовчуванням 1)
    group_id = 1
    try:
        g_res = requests.get(f"{POSTER_API_URL}/clients.getGroups", params={"token": POSTER_TOKEN}).json()
        if g_res.get("response"):
            group_id = g_res["response"][0]["client_groups_id_client"]
    except:
        pass

    # 2. Формуємо параметри (Poster краще працює з GET параметрами для створення клієнтів)
    params = {
        "token": POSTER_TOKEN,
        "client_name": name or "Клієнт Telegram",
        "phone": clean_phone,
        "client_groups_id_client": group_id,
        "client_sex": 0
    }

    try:
        # Використовуємо GET, щоб уникнути помилки 405/Method Not Allowed
        response = requests.get(f"{POSTER_API_URL}/clients.setClient", params=params)
        res = response.json()
        
        # Дебаг повідомлення (можна закоментувати)
        bot.send_message(chat_id, f"🛠 API Response: `{res}`", parse_mode="Markdown")

        # Перевірка наявності помилки в структурі Poster
        if "error" in res:
            error_code = res.get("error")
            # Якщо клієнт вже існує, Poster повертає код 34
            if error_code == 34:
                bot.send_message(chat_id, "✅ Ви вже зареєстровані у нашій системі!")
                return True
            
            bot.send_message(chat_id, f"⚠️ Poster Error: {error_code}")
            return None
            
        bot.send_message(chat_id, "✅ Ви успішно зареєстровані в Poster!")
        return res.get("response")

    except Exception as e:
        bot.send_message(chat_id, f"❌ Помилка зв'язку: {e}")
    return None

# --- ХЕНДЛЕРИ ---

@bot.message_handler(commands=['start'])
def start(message):
    db_manage_user(message.chat.id)
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.add(types.KeyboardButton("👤 Мій профіль"))
    bot.send_message(message.chat.id, "Вітаємо! Натисніть кнопку нижче, щоб перевірити реєстрацію.", reply_markup=m)

@bot.message_handler(commands=['reset'])
def reset(message):
    with sqlite3.connect("pink_fix.db") as conn:
        conn.cursor().execute("UPDATE users SET phone = NULL WHERE user_id = ?", (message.chat.id,))
    bot.send_message(message.chat.id, "♻️ Номер видалено з бази бота. Можете спробувати заново.")

@bot.message_handler(func=lambda m: m.text == "👤 Мій профіль")
def profile(message):
    user = db_manage_user(message.chat.id)
    
    # Якщо номера немає в нашій БД — просимо контакт
    if not user or not user[0]:
        m = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        m.add(types.KeyboardButton("📱 Поділитися контактом", request_contact=True))
        return bot.send_message(message.chat.id, "Для реєстрації нам потрібен ваш номер телефону:", reply_markup=m)
    
    # Якщо номер є — відправляємо запит до Poster
    bot.send_message(message.chat.id, "🔍 Перевіряємо ваш профіль у Poster...")
    create_poster_client(user[0], message.from_user.first_name, message.chat.id)

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    # Зберігаємо отриманий номер і викликаємо профіль
    db_manage_user(message.chat.id, phone=message.contact.phone_number)
    profile(message)

if __name__ == "__main__":
    init_db()
    print("Бот запущений...")
    bot.infinity_polling()

