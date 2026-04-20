import telebot
from telebot import types
import os
import re
import sqlite3
from openai import OpenAI

# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEB_APP_URL = "https://mamutpetr.github.io/Pinkcanna/"

bot = telebot.TeleBot(TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# --- БАЗА ДАНИХ ---
def init_db():
    conn = sqlite3.connect('pinkcanna.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, 
                       balance REAL DEFAULT 0, 
                       referred_by INTEGER)''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('pinkcanna.db')
    cursor = conn.cursor()
    cursor.execute("SELECT balance, referred_by FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 0)", (user_id,))
        conn.commit()
        user = (0, None)
    conn.close()
    return user

def add_bonus(user_id, amount):
    conn = sqlite3.connect('pinkcanna.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

init_db()

# --- ТОВАРИ ---
PRODUCTS = {
    "sleep": {"name": "Happy caps sleep (Інгалятор) 💤", "price": 2000, "image": "sleep.jpg"},
    "gaba": {"name": "Габа #9 🧠", "price": 400, "image": "gaba9.jpg"},
    "energy": {"name": "Happy caps energy ⚡", "price": 2000, "image": "energy.jpg"},
    "cream": {"name": "СБД Крем 🧴", "price": 1600, "image": "cream.jpg"},
    "vape": {"name": "Вейп 💨", "price": 3000, "image": "blackvape.jpg"},
    "jelly": {"name": "СБД Желе 🍬", "price": 1900, "image": "Cbdgele.jpg"}
}

user_carts = {}

# --- ГОЛОВНЕ МЕНЮ ---
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("📂 Каталог", "🛒 Кошик")
    m.add(types.KeyboardButton("🍀 Натапати знижку", web_app=types.WebAppInfo(url=WEB_APP_URL)))
    m.add("👤 Мій профіль", "📰 Новини")
    m.add("📞 Консультант")
    return m

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    get_user(user_id) # Реєструємо в БД
    
    # Реферальна система: перевірка посилання
    args = message.text.split()
    if len(args) > 1:
        referrer_id = args[1]
        if referrer_id.isdigit() and int(referrer_id) != user_id:
            conn = sqlite3.connect('pinkcanna.db')
            cursor = conn.cursor()
            cursor.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,))
            already_referred = cursor.fetchone()
            if already_referred and already_referred[0] is None:
                cursor.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer_id, user_id))
                conn.commit()
                add_bonus(int(referrer_id), 50) # +50 грн тому, хто запросив
                bot.send_message(referrer_id, "🎁 Твій друг приєднався! Тобі нараховано 50 грн бонусу!")
            conn.close()

    bot.send_message(user_id, "🌿 Вітаємо у Pink Canna! Обирай якісний CBD.", reply_markup=main_menu())

# --- ПРОФІЛЬ ТА РЕФЕРАЛКА ---
@bot.message_handler(func=lambda m: m.text == "👤 Мій профіль")
def profile(message):
    user_id = message.chat.id
    balance, _ = get_user(user_id)
    bot_username = bot.get_me().username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    
    text = (f"👤 **Твій профіль**\n\n"
            f"💰 Бонусний баланс: **{balance} грн**\n"
            f"*(Ці гроші можна використати для оплати замовлень)*\n\n"
            f"🔗 **Реферальна програма:**\n"
            f"Запроси друга за посиланням нижче та отримай **50 грн** на свій баланс, коли він перейде в бот!\n\n"
            f"`{ref_link}`")
    bot.send_message(user_id, text, parse_mode="Markdown")

# --- КАТАЛОГ ---
@bot.message_handler(func=lambda m: m.text == "📂 Каталог")
def catalog(message):
    for key, item in PRODUCTS.items():
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"➕ Купити за {item['price']} грн", callback_data=f"buy_{key}"))
        caption = f"🏷 **{item['name']}**\n💰 Ціна: {item['price']} грн"
        if os.path.exists(item['image']):
            with open(item['image'], 'rb') as photo:
                bot.send_photo(message.chat.id, photo, caption=caption, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, caption, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def add_to_cart(call):
    key = call.data.replace("buy_", "")
    user_carts.setdefault(call.message.chat.id, []).append(key)
    bot.answer_callback_query(call.id, f"✅ Додано: {PRODUCTS[key]['name']}")

# --- КОШИК ТА ОПЛАТА ---
@bot.message_handler(func=lambda m: m.text == "🛒 Кошик")
def show_cart(message):
    chat_id = message.chat.id
    items = user_carts.get(chat_id, [])
    if not items:
        bot.send_message(chat_id, "🛒 Кошик порожній.")
        return

    total = sum(PRODUCTS[k]['price'] for k in items)
    balance, _ = get_user(chat_id)
    
    summary = "\n".join([f"• {PRODUCTS[k]['name']}" for k in items])
    text = f"**Твій кошик:**\n{summary}\n\n💰 Сума: {total} грн\n✨ Твій бонусний баланс: {balance} грн"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Оформити замовлення", callback_data="checkout"))
    markup.add(types.InlineKeyboardButton("🗑 Очистити", callback_data="clear_cart"))
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "checkout")
def checkout(call):
    chat_id = call.message.chat.id
    items = user_carts.get(chat_id, [])
    total_price = sum(PRODUCTS[key]['price'] for key in items)
    balance, _ = get_user(chat_id)

    # Автоматичне списання бонусів
    use_bonus = min(balance, total_price - 1) # Залишаємо мінімум 1 грн до оплати
    final_price = total_price - use_bonus

    prices = [types.LabeledPrice("Замовлення Pink Canna", int(total_price * 100))]
    if use_bonus > 0:
        prices.append(types.LabeledPrice(f"Списано бонусів: -{use_bonus} грн", -int(use_bonus * 100)))

    bot.send_invoice(
        chat_id, title="Оплата Pink Canna", description="З урахуванням твоїх бонусів",
        invoice_payload=f"bonus_{use_bonus}", provider_token=PAYMENT_TOKEN,
        currency="UAH", prices=prices, start_parameter="pay",
        need_phone_number=True, need_shipping_address=True
    )

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(q):
    bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def success(message):
    chat_id = message.chat.id
    # Віднімаємо використані бонуси з БД
    payload = message.successful_payment.invoice_payload
    if payload.startswith("bonus_"):
        used_bonus = float(payload.split("_")[1])
        add_bonus(chat_id, -used_bonus)

    bot.send_message(chat_id, "✅ Оплата успішна! Твій баланс оновлено, чекай на доставку.")
    user_carts[chat_id] = []

# --- НОВИНИ ---
@bot.message_handler(func=lambda m: m.text == "📰 Новини")
def news(message):
    text = ("🌿 **CBD та Закон**\n\nЗгідно з Постановою КМУ №324, CBD не є наркотиком. "
            "Це легальний засіб для спокою та здоров'я. Pink Canna піклується про твою безпеку!")
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# --- AI-КОНСУЛЬТАНТ ---
@bot.message_handler(func=lambda m: True)
def ai_consultant(message):
    if message.text in ["📂 Каталог", "🛒 Кошик", "👤 Мій профіль", "📰 Новини", "📞 Консультант"]: return
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "Ти консультант магазину Pink Canna. Допомагай клієнтам."},
                      {"role": "user", "content": message.text}]
        )
        bot.send_message(message.chat.id, response.choices[0].message.content)
    except:
        bot.send_message(message.chat.id, "⚠️ Консультант зайнятий, спробуй пізніше.")

if __name__ == "__main__":
    bot.infinity_polling()
