import telebot
from telebot import types
import os
import sqlite3
import re
import qrcode
import requests
from io import BytesIO
from datetime import datetime, timedelta
from openai import OpenAI

# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_ID = os.getenv("ADMIN_ID") 
WEB_APP_URL = "https://mamutpetr.github.io/Pinkcanna/"

# --- POSTER API ---
POSTER_TOKEN = os.getenv("POSTER_TOKEN")
POSTER_API_URL = "https://joinposter.com/api"

bot = telebot.TeleBot(TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# --- РОБОТА З POSTER API ---
def get_poster_client(phone_number):
    if not POSTER_TOKEN: return None
    url = f"{POSTER_API_URL}/clients.getClients"
    clean_phone = re.sub(r'\D', '', phone_number)
    params = {"token": POSTER_TOKEN, "search": clean_phone}
    try:
        res = requests.get(url, params=params).json()
        if res.get("response") and len(res["response"]) > 0:
            return res["response"][0]
    except: pass
    return None

def create_poster_client(phone_number, name, chat_id):
    if not POSTER_TOKEN: return None
    group_id = 1
    try:
        groups_res = requests.get(f"{POSTER_API_URL}/clients.getGroups", params={"token": POSTER_TOKEN}).json()
        if groups_res.get("response"): group_id = groups_res["response"][0]["client_groups_id_client"]
    except: pass

    url = f"{POSTER_API_URL}/clients.setClient"
    clean_phone = re.sub(r'\D', '', phone_number)
    params = {
        "token": POSTER_TOKEN,
        "client_name": name or "Клієнт Telegram",
        "phone": clean_phone,
        "client_groups_id_client": group_id,
        "client_sex": 0,
        "bonus": 0
    }
    try:
        res = requests.post(url, params=params).json()
        if res.get("error") == 34: return get_poster_client(phone_number)
        return res.get("response")
    except: return None

def update_poster_bonus(client_id, current_bonus, add_amount):
    if not POSTER_TOKEN: return
    url = f"{POSTER_API_URL}/clients.setClient"
    params = {"token": POSTER_TOKEN, "client_id": client_id, "bonus": float(current_bonus) + float(add_amount)}
    requests.post(url, params=params)

# --- БАЗА ДАНИХ ---
def init_db():
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS carts_v2 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_key TEXT, expires_at DATETIME)''')
        c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, phone TEXT, discount INTEGER DEFAULT 0, referred_by INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS ai_history (user_id INTEGER, role TEXT, content TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS inventory (product_key TEXT PRIMARY KEY, total_qty INTEGER DEFAULT 0)''')
        try: c.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        except: pass
        for key in PRODUCTS.keys():
            c.execute("INSERT OR IGNORE INTO inventory (product_key, total_qty) VALUES (?, 20)", (key,))
        conn.commit()

def db_manage_user(user_id, discount=None, phone=None):
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        if discount is not None: c.execute("UPDATE users SET discount = ? WHERE user_id = ?", (discount, user_id))
        if phone is not None: c.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
        conn.commit()
        return c.execute("SELECT phone, discount, referred_by FROM users WHERE user_id = ?", (user_id,)).fetchone()

def db_get_stock(product_key):
    with sqlite3.connect("pinkcanna.db") as conn:
        total = (conn.cursor().execute("SELECT total_qty FROM inventory WHERE product_key = ?", (product_key,)).fetchone() or [0])[0]
        reserved = conn.cursor().execute("SELECT COUNT(*) FROM carts_v2 WHERE product_key = ? AND expires_at > ?", (product_key, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))).fetchone()[0]
        return max(0, total - reserved)

def db_add_to_cart(user_id, product_key):
    if db_get_stock(product_key) > 0:
        with sqlite3.connect("pinkcanna.db") as conn:
            exp = (datetime.now() + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
            conn.cursor().execute("INSERT INTO carts_v2 (user_id, product_key, expires_at) VALUES (?, ?, ?)", (user_id, product_key, exp))
            conn.commit()
        return True
    return False

def db_confirm_purchase(user_id):
    items = [row[0] for row in sqlite3.connect("pinkcanna.db").cursor().execute("SELECT product_key FROM carts_v2 WHERE user_id = ?", (user_id,)).fetchall()]
    with sqlite3.connect("pinkcanna.db") as conn:
        for k in items: conn.cursor().execute("UPDATE inventory SET total_qty = total_qty - 1 WHERE product_key = ?", (k,))
        conn.cursor().execute("DELETE FROM carts_v2 WHERE user_id = ?", (user_id,))
        conn.cursor().execute("UPDATE users SET discount = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
    return items

# --- ТОВАРИ ТА ДАНІ ---
CATEGORIES = {"kanna": "🌿 Екстракти Канни", "cbd": "💧 Олії та Релакс", "wellness": "🧠 Сон та Енергія", "topical": "🧴 Вейпи та Догляд"}
PRODUCTS = {
    "kanna10x": {"name": "Канна 10х", "price": 2500, "image": "kanna10x.jpg", "category": "kanna", "short": "Екстракт для настрою.", "info": "🌿 Потужний SRI-ефект."},
    "jelly": {"name": "СБД Желе", "price": 1900, "image": "Cbdgele.jpg", "category": "cbd", "short": "Смачний релакс.", "info": "🍬 CBD Jelly для спокою."},
    "cbd_10_10": {"name": "Олія CBD 10%", "price": 1300, "image": "cbd_10_10.jpg", "category": "cbd", "short": "70мг в піпетці", "info": "💧 Універсальна концентрація."},
    "vape": {"name": "Вейп CBD", "price": 3000, "image": "blackvape.jpg", "category": "topical", "short": "Миттєвий релакс.", "info": "💨 Найшвидша дія."}
}
DOSAGE_DATA = {
    "stress": {"name": "Стрес / Фобії", "doses": {50: 64, 60: 68, 70: 73, 80: 77, 90: 82, 100: 87, 110: 91, 120: 95}},
    "pain": {"name": "Хронічний біль", "doses": {50: 91, 60: 99, 70: 106, 80: 113, 90: 120, 100: 128, 110: 135, 120: 142}}
}
CONC_DATA = {10: {"10ml": 70, "30ml": 100}, 5: {"10ml": 35, "30ml": 50}}

init_db()

# --- МЕНЮ ТА ХЕНДЛЕРИ ---
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.row("📂 Каталог", "🛒 Кошик", "👤 Профіль")
    m.row("🧮 Підбір дози CBD", "📞 Консультант")
    return m

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    user_data = db_manage_user(user_id)
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        ref_id = int(args[1])
        if ref_id != user_id and user_data[2] is None:
            with sqlite3.connect("pinkcanna.db") as conn:
                conn.cursor().execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (ref_id, user_id))
                conn.commit()
            ref_data = db_manage_user(ref_id)
            if ref_data[0]:
                poster = get_poster_client(ref_data[0])
                if poster: 
                    update_poster_bonus(poster['client_id'], poster['bonus'], 50)
                    bot.send_message(ref_id, "🎁 Друг приєднався! +50 грн нараховано!")
    bot.send_message(user_id, "🌿 Вітаємо у Pink Canna!", reply_markup=main_menu())

@bot.message_handler(commands=['reset'])
def reset_cmd(message):
    with sqlite3.connect("pinkcanna.db") as conn:
        conn.cursor().execute("UPDATE users SET phone = NULL WHERE user_id = ?", (message.chat.id,))
    bot.send_message(message.chat.id, "♻️ Номер скинуто для тесту.")

@bot.message_handler(func=lambda m: m.text == "👤 Профіль")
def profile_cmd(message):
    user_id = message.chat.id
    user_data = db_manage_user(user_id)
    if not user_data[0]:
        m = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        m.add(types.KeyboardButton("📱 Надіслати номер", request_contact=True), "⬅️ Назад")
        return bot.send_message(user_id, "Для карти лояльності потрібен номер:", reply_markup=m)
    
    bot.send_chat_action(user_id, 'typing')
    poster = get_poster_client(user_data[0])
    bonus = int(float(poster['bonus'])) if poster else 0
    ref = f"https://t.me/{bot.get_me().username}?start={user_id}"
    markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🪪 Моя карта (QR)", callback_data="show_qr"))
    text = f"👤 **Профіль**\n📱 `{user_data[0]}`\n💰 Бонуси: **{bonus} грн**\n🍀 Знижка: **{user_data[1]} грн**\n\n🔗 Рефералка: `{ref}`"
    bot.send_message(user_id, text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    phone = message.contact.phone_number
    if not phone.startswith('+'): phone = '+' + phone
    db_manage_user(message.chat.id, phone=phone)
    bot.send_message(message.chat.id, "⏳ Синхронізація...", reply_markup=main_menu())
    create_poster_client(phone, message.from_user.first_name, message.chat.id)
    profile_cmd(message)

@bot.callback_query_handler(func=lambda c: c.data == "show_qr")
def show_qr(call):
    user = db_manage_user(call.message.chat.id)
    qr = qrcode.make(user[0])
    bio = BytesIO()
    qr.save(bio, 'PNG')
    bio.seek(0)
    bot.send_photo(call.message.chat.id, bio, caption="🪪 Покажіть код на касі")

# --- КАТАЛОГ ТА КОШИК ---
@bot.message_handler(func=lambda m: m.text == "📂 Каталог")
def catalog(message):
    m = types.InlineKeyboardMarkup()
    for k, v in CATEGORIES.items(): m.add(types.InlineKeyboardButton(v, callback_data=f"cat_{k}"))
    bot.send_message(message.chat.id, "Оберіть категорію:", reply_markup=m)

@bot.callback_query_handler(func=lambda c: c.data.startswith("cat_"))
def cat_items(call):
    cat = call.data.split("_")[1]
    for k, p in PRODUCTS.items():
        if p['category'] == cat:
            stock = db_get_stock(k)
            m = types.InlineKeyboardMarkup()
            if stock > 0: m.add(types.InlineKeyboardButton(f"🛒 В кошик ({p['price']} грн)", callback_data=f"buy_{k}"))
            m.add(types.InlineKeyboardButton("🔍 Детальніше", callback_data=f"info_{k}"))
            bot.send_message(call.message.chat.id, f"🏷 **{p['name']}**\n📦 В наявності: {stock}\n💰 Ціна: {p['price']} грн", reply_markup=m, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
def buy(call):
    if db_add_to_cart(call.message.chat.id, call.data.split("_")[1]):
        bot.answer_callback_query(call.id, "✅ Додано!")
    else:
        bot.answer_callback_query(call.id, "❌ Немає", show_alert=True)

@bot.message_handler(func=lambda m: m.text == "🛒 Кошик")
def view_cart(message):
    raw = [r[0] for r in sqlite3.connect("pinkcanna.db").cursor().execute("SELECT product_key FROM carts_v2 WHERE user_id = ?", (message.chat.id,)).fetchall()]
    if not raw: return bot.send_message(message.chat.id, "🛒 Порожньо.")
    total = sum(PRODUCTS[k]['price'] for k in raw)
    user = db_manage_user(message.chat.id)
    poster = get_poster_client(user[0]) if user[0] else None
    bonus = float(poster['bonus']) if poster else 0
    final = max(1, total - user[1] - bonus)
    m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("💳 Оплатити", callback_data="checkout"))
    bot.send_message(message.chat.id, f"Разом: {total} грн\n🎁 Знижки: -{int(user[1] + bonus)} грн\n**До сплати: {int(final)} грн**", reply_markup=m, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "checkout")
def checkout(call):
    raw = [r[0] for r in sqlite3.connect("pinkcanna.db").cursor().execute("SELECT product_key FROM carts_v2 WHERE user_id = ?", (call.message.chat.id,)).fetchall()]
    total = sum(PRODUCTS[k]['price'] for k in raw)
    user = db_manage_user(call.message.chat.id)
    poster = get_poster_client(user[0]) if user[0] else None
    bonus = float(poster['bonus']) if poster else 0
    final = int(max(1, total - user[1] - bonus))
    bot.send_invoice(call.message.chat.id, "Pink Canna", "Оплата", f"pay_{bonus}", PAYMENT_TOKEN, "UAH", [types.LabeledPrice("Замовлення", final * 100)])

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_check(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def pay_ok(message):
    db_confirm_purchase(message.chat.id)
    bonus_used = float(message.successful_payment.invoice_payload.replace("pay_", ""))
    user = db_manage_user(message.chat.id)
    poster = get_poster_client(user[0])
    if poster and bonus_used > 0: update_poster_bonus(poster['client_id'], poster['bonus'], -bonus_used)
    bot.send_message(message.chat.id, "✅ Оплачено!")

# --- КАЛЬКУЛЯТОР ---
@bot.message_handler(func=lambda m: m.text == "🧮 Підбір дози CBD")
def calc_start(message):
    m = types.InlineKeyboardMarkup(row_width=1)
    for k, v in DOSAGE_DATA.items(): m.add(types.InlineKeyboardButton(v["name"], callback_data=f"calc_{k}"))
    bot.send_message(message.chat.id, "🩺 Оберіть симптом:", reply_markup=m)

@bot.callback_query_handler(func=lambda c: c.data.startswith("calc_"))
def calc_res(call):
    sym = call.data.split("_")[1]
    text = f"📊 Норма для {DOSAGE_DATA[sym]['name']}:\n"
    for w, d in DOSAGE_DATA[sym]['doses'].items(): text += f"• {w} кг: {d} мг/день\n"
    bot.send_message(call.message.chat.id, text)

# --- AI ТА АДМІНКА ---
@bot.message_handler(commands=['admin'])
def admin(message):
    if str(message.chat.id) == str(ADMIN_ID):
        m = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("📢 Розсилка", callback_data="adm_bc"))
        bot.send_message(message.chat.id, "👨‍💻 Адмінка", reply_markup=m)

@bot.message_handler(func=lambda m: True)
def ai_chat(message):
    if message.text in ["📂 Каталог", "🛒 Кошик", "👤 Профіль", "🧮 Підбір дози CBD", "📞 Консультант"]: return
    try:
        res = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": message.text}])
        bot.send_message(message.chat.id, res.choices[0].message.content)
    except: pass

if __name__ == "__main__":
    bot.infinity_polling()

