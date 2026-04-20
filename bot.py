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

# --- БАЗА ДАНИХ (Тільки користувачі) ---
def init_db():
    with sqlite3.connect("diagnostic.db") as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (user_id INTEGER PRIMARY KEY, phone TEXT)''')
        conn.commit()

def db_manage_user(user_id, phone=None):
    with sqlite3.connect("diagnostic.db") as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        if phone:
            c.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
        conn.commit()
        return c.execute("SELECT phone FROM users WHERE user_id = ?", (user_id,)).fetchone()

# --- РОБОТА З POSTER API (ВИПРАВЛЕНИЙ МЕТОД) ---

def get_poster_client(phone_number):
    """Перевірка, чи є клієнт у базі."""
    clean_phone = re.sub(r'\D', '', phone_number)
    url = f"{POSTER_API_URL}/clients.getClients"
    # Для пошуку Poster зазвичай використовує GET
    params = {"token": POSTER_TOKEN, "phone": clean_phone}
    try:
        res = requests.get(url, params=params).json()
        if res.get("response") and len(res["response"]) > 0:
            return res["response"][0]
    except: pass
    return None

def create_poster_client(phone_number, name, chat_id):
    """Створення клієнта. Використовуємо POST з токеном у параметрах URL."""
    if not POSTER_TOKEN:
        bot.send_message(chat_id, "❌ Помилка: POSTER_TOKEN не вказано в Render!")
        return None

    # Отримуємо ID групи (обов'язково)
    group_id = 1
    try:
        g_res = requests.get(f"{POSTER_API_URL}/clients.getGroups", params={"token": POSTER_TOKEN}).json()
        if g_res.get("response"):
            group_id = g_res["response"][0]["client_groups_id_client"]
    except: pass

    # ПРАВИЛЬНА АДРЕСА: Метод setClient
    url = f"{POSTER_API_URL}/clients.setClient"
    
    # ПАРАМЕТРИ АВТОРИЗАЦІЇ (підуть в URL)
    auth_params = {"token": POSTER_TOKEN}
    
    # ДАНІ КЛІЄНТА (підуть у тіло запиту як FORM DATA)
    client_data = {
        "client_name": name or "Клієнт Telegram",
        "phone": re.sub(r'\D', '', phone_number), # Тільки цифри
        "client_groups_id_client": group_id,
        "client_sex": 0,
        "bonus": 0
    }

    try:
        # ВАЖЛИВО: params=auth_params (в URL), data=client_data (в тіло запиту)
        response = requests.post(url, params=auth_params, data=client_data)
        res = response.json()
        
        # Виводимо в чат для діагностики
        bot.send_message(chat_id, f"🛠 Відповідь Poster: `{res}`", parse_mode="Markdown")

        if res.get("error") == 34:
            return get_poster_client(phone_number)
        
        return res.get("response")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Помилка запиту: {e}")
    return None

# --- КОМАНДИ ---

@bot.message_handler(commands=['start'])
def start(message):
    db_manage_user(message.chat.id)
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("👤 Профіль")
    bot.send_message(message.chat.id, "Бот запущений у режимі діагностики Poster.", reply_markup=m)

@bot.message_handler(commands=['reset'])
def reset(message):
    with sqlite3.connect("diagnostic.db") as conn:
        conn.cursor().execute("UPDATE users SET phone = NULL WHERE user_id = ?", (message.chat.id,))
    bot.send_message(message.chat.id, "♻️ Телефон скинуто. Натисніть 'Профіль' для тесту.")

@bot.message_handler(func=lambda m: m.text == "👤 Профіль")
def profile(message):
    user = db_manage_user(message.chat.id)
    if not user[0]:
        m = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        m.add(types.KeyboardButton("📱 Надіслати контакт", request_contact=True))
        return bot.send_message(message.chat.id, "Надішліть контакт для реєстрації в Poster:", reply_markup=m)
    
    # Тягнемо баланс
    bot.send_message(message.chat.id, "🔍 Перевіряю дані в Poster...")
    poster_data = get_poster_client(user[0])
    if poster_data:
        text = f"✅ Клієнта знайдено!\n👤 Ім'я: {poster_data['client_name']}\n💰 Бонуси: {poster_data['bonus']} грн"
    else:
        text = "❌ Клієнта немає в базі Poster. Спробуйте /reset і зареєструйтесь знову."
    bot.send_message(message.chat.id, text)

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    phone = message.contact.phone_number
    db_manage_user(message.chat.id, phone=phone)
    
    bot.send_message(message.chat.id, "⏳ Спроба реєстрації в Poster...")
    res = create_poster_client(phone, message.from_user.first_name, message.chat.id)
    
    if res:
        bot.send_message(message.chat.id, "🎉 Успіх! Клієнт створений або підтягнутий.")
    profile(message)

if __name__ == "__main__":
    init_db()
    bot.infinity_polling()

