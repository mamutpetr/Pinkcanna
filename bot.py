import telebot
from telebot import types
import os
import sqlite3
import re
import requests
from io import BytesIO
from datetime import datetime, timedelta
from openai import OpenAI
import time
import barcode
from barcode.writer import ImageWriter

# --- НАЛАШТУВАННЯ МАГАЗИНУ ---
SHOP_NAME = "Демо Магазин" # Змінювати для кожного клієнта
SHOP_CURRENCY = "UAH"

TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_ID = os.getenv("ADMIN_ID") 
WEB_APP_URL = "https://your-web-app-url.com/" # URL міні-гри/лендінгу клієнта

# --- POSTER API ---
POSTER_TOKEN = os.getenv("POSTER_TOKEN")
POSTER_API_URL = "https://joinposter.com/api"
SPOT_ID = 1 # ID закладу клієнта в Poster

if not TOKEN:
    raise Exception("❌ BOT_TOKEN не заданий")
if not POSTER_TOKEN:
    raise Exception("❌ POSTER_TOKEN не заданий")

bot = telebot.TeleBot(TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# --- FSM СХОВИЩЕ (КЕШ) ---
user_data_cache = {}

# --- UTILS ---
def normalize_phone(phone):
    clean = re.sub(r'\D', '', phone)
    if clean.startswith("380"):
        return clean
    elif clean.startswith("0"):
        return "380" + clean[1:]
    return clean

# --- POSTER REQUEST ---
def poster_request(endpoint, method="GET", data=None):
    url = f"{POSTER_API_URL}/{endpoint}"
    if not data:
        data = {}

    params = {"token": POSTER_TOKEN}

    try:
        if method == "GET":
            merged_params = {**params, **data}
            res = requests.get(url, params=merged_params, timeout=10)
        else:
            res = requests.post(url, params=params, json=data, timeout=10)

        return res.json()
    except Exception as e:
        print(f"❌ POSTER EXCEPTION [{endpoint}]:", e)
        return None

# --- РОБОТА З POSTER API ---
def get_poster_client(phone_number):
    if not POSTER_TOKEN: return None
    phone = normalize_phone(phone_number)
    res = poster_request("clients.getClients", "GET", {"phone": phone})
    if res and res.get("response"):
        return res["response"][0]
    res_plus = poster_request("clients.getClients", "GET", {"phone": f"+{phone}"})
    if res and res_plus.get("response"):
        return res_plus["response"][0]
    return None

def add_poster_bonus(client_id, amount_uah):
    if not POSTER_TOKEN: return
    payload = {
        "client_id": client_id,
        "count": int(amount_uah * 100)
    }
    res = poster_request("clients.changeClientBonus", "POST", payload)
    return res

def reward_referrer(referrer_id):
    referrer_data = db_manage_user(referrer_id)
    if not referrer_data or not referrer_data[0]:
        return
        
    referrer_phone = referrer_data[0]
    client_poster = get_poster_client(referrer_phone)
    if client_poster:
        add_poster_bonus(client_poster['client_id'], 50)
        try:
            bot.send_message(referrer_id, f"🎁 Ваш друг щойно завершив реєстрацію! Вам нараховано **50 бонусів** на рахунок у {SHOP_NAME}!", parse_mode="Markdown")
        except: pass

def create_poster_client_full(user_id):
    if not POSTER_TOKEN: return None
    data = user_data_cache.get(user_id, {})
    phone = normalize_phone(data.get('phone', ''))
    
    payload = {
        "client_name": data.get('name', 'Клієнт Telegram'),
        "phone": phone,
        "card_number": phone, 
        "client_sex": data.get('sex', 0),
        "birthday": data.get('birthday', ''),
        "email": data.get('email', ''),
        "client_groups_id_client": 1,
        "bonus": 0
    }

    res = poster_request("clients.createClient", "POST", payload)

    if res and "error" not in res:
        user_db = db_manage_user(user_id)
        if user_db[2]: 
            reward_referrer(user_db[2])
            
        local_discount = user_db[1]
        if local_discount > 0:
            new_client = get_poster_client(phone)
            if new_client:
                add_poster_bonus(new_client['client_id'], local_discount)
                db_manage_user(user_id, discount=0)
                try:
                    bot.send_message(user_id, f"💸 Ваші акційні **{local_discount} грн** успішно перенесені на бонусну карту!", parse_mode="Markdown")
                except: pass
            
    return res

# --- БАЗА ДАНИХ (Універсальна назва) ---
DB_NAME = "shop_database.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS carts_v2 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_key TEXT, expires_at DATETIME)''')
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (user_id INTEGER PRIMARY KEY, phone TEXT, discount INTEGER DEFAULT 0, balance REAL DEFAULT 0, referred_by INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS ai_history 
                     (user_id INTEGER, role TEXT, content TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS inventory 
                     (product_key TEXT PRIMARY KEY, total_qty INTEGER DEFAULT 0)''')
        
        try: c.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        except: pass

        for key in PRODUCTS.keys():
            c.execute("INSERT OR IGNORE INTO inventory (product_key, total_qty) VALUES (?, 20)", (key,))
        conn.commit()

def db_cleanup_expired():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("DELETE FROM carts_v2 WHERE expires_at < ?", (now_str,))
        conn.commit()

def db_get_stock(product_key):
    db_cleanup_expired()
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT total_qty FROM inventory WHERE product_key = ?", (product_key,))
        res = c.fetchone()
        total = res[0] if res else 0
        c.execute("SELECT COUNT(*) FROM carts_v2 WHERE product_key = ?", (product_key,))
        reserved = c.fetchone()[0]
        return max(0, total - reserved)

def db_set_stock(product_key, qty):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("UPDATE inventory SET total_qty = ? WHERE product_key = ?", (qty, product_key))
        conn.commit()

def db_add_to_cart_with_reserve(user_id, product_key):
    if db_get_stock(product_key) > 0:
        with sqlite3.connect(DB_NAME) as conn:
            c = conn.cursor()
            expires = datetime.now() + timedelta(minutes=15)
            c.execute("INSERT INTO carts_v2 (user_id, product_key, expires_at) VALUES (?, ?, ?)", 
                      (user_id, product_key, expires.strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
        return True
    return False

def db_get_cart_with_expiry(user_id):
    db_cleanup_expired()
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT product_key, expires_at FROM carts_v2 WHERE user_id = ?", (user_id,))
        return c.fetchall()

def db_remove_one_from_cart(user_id, product_key):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM carts_v2 WHERE id = (SELECT id FROM carts_v2 WHERE user_id = ? AND product_key = ? LIMIT 1)", (user_id, product_key))
        conn.commit()

def db_clear_cart(user_id):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM carts_v2 WHERE user_id = ?", (user_id,))
        conn.commit()

def db_confirm_purchase(user_id):
    items = [row[0] for row in db_get_cart_with_expiry(user_id)]
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        for key in items:
            c.execute("UPDATE inventory SET total_qty = total_qty - 1 WHERE product_key = ?", (key,))
        c.execute("DELETE FROM carts_v2 WHERE user_id = ?", (user_id,))
        c.execute("UPDATE users SET discount = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
    return items

def db_manage_user(user_id, discount=None, phone=None):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        if discount is not None:
            c.execute("UPDATE users SET discount = ? WHERE user_id = ?", (discount, user_id))
        if phone is not None:
            c.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
        conn.commit()
        c.execute("SELECT phone, discount, referred_by FROM users WHERE user_id = ?", (user_id,))
        return c.fetchone()

def db_manage_history(user_id, role=None, content=None):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        if role and content:
            c.execute("INSERT INTO ai_history VALUES (?, ?, ?)", (user_id, role, content))
            c.execute("DELETE FROM ai_history WHERE rowid NOT IN (SELECT rowid FROM ai_history WHERE user_id = ? ORDER BY rowid DESC LIMIT 10)", (user_id,))
            conn.commit()
        c.execute("SELECT role, content FROM ai_history WHERE user_id = ? ORDER BY rowid ASC", (user_id,))
        return [{"role": row[0], "content": row[1]} for row in c.fetchall()]

# --- ТОВАРИ (Універсальні шаблони) ---
CATEGORIES = {
    "category1": "📁 Категорія 1", 
    "category2": "📁 Категорія 2", 
    "category3": "📁 Категорія 3"
}

PRODUCTS = {
    "item1": {"poster_id": 1, "name": "Тестовий Товар 1", "price": 500, "image": "product1.jpg", "category": "category1", "short": "Короткий опис першого товару.", "info": "Детальний опис першого товару з усіма характеристиками."},
    "item2": {"poster_id": 2, "name": "Тестовий Товар 2", "price": 1200, "image": "product2.jpg", "category": "category1", "short": "Короткий опис другого товару.", "info": "Детальний опис другого товару з усіма характеристиками."},
    "item3": {"poster_id": 3, "name": "Тестовий Товар 3", "price": 300, "image": "product3.jpg", "category": "category2", "short": "Короткий опис третього товару.", "info": "Детальний опис третього товару з усіма характеристиками."},
    "item4": {"poster_id": 4, "name": "Тестовий Товар 4", "price": 4500, "image": "product4.jpg", "category": "category3", "short": "Короткий опис четвертого товару.", "info": "Детальний опис четвертого товару з усіма характеристиками."}
}

init_db()

# --- ВІДПРАВКА КАРТКИ ТОВАРУ ---
def send_product_card(chat_id, key):
    item = PRODUCTS[key]
    stock = db_get_stock(key)
    markup = types.InlineKeyboardMarkup(row_width=1)
    if stock > 0:
        stock_text = f"🟢 В наявності: {stock} шт"
        markup.add(
            types.InlineKeyboardButton(f"🛒 Додати в кошик ({item['price']} {SHOP_CURRENCY})", callback_data=f"buy_{key}"),
            types.InlineKeyboardButton("🔍 Дізнатись більше", callback_data=f"info_{key}")
        )
    else:
        stock_text = "🔴 Немає в наявності"
        markup.add(types.InlineKeyboardButton("🔍 Дізнатись більше", callback_data=f"info_{key}"))

    caption = f"🏷 **{item['name']}**\n\n📝 {item['short']}\n📦 {stock_text}\n💰 **Ціна: {item['price']} {SHOP_CURRENCY}**"
    try:
        if os.path.exists(item['image']):
            with open(item['image'], 'rb') as photo: bot.send_photo(chat_id, photo, caption=caption, reply_markup=markup, parse_mode="Markdown")
        else: bot.send_message(chat_id, caption, reply_markup=markup, parse_mode="Markdown")
    except: bot.send_message(chat_id, caption, reply_markup=markup, parse_mode="Markdown")

def generate_customer_barcode(phone_number):
    code128 = barcode.get_barcode_class('code128')
    bar = code128(phone_number, writer=ImageWriter())
    bio = BytesIO()
    bar.write(bio, options={"write_text": True, "module_width": 0.3})
    bio.seek(0)
    return bio

# --- МЕНЮ ---
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.row("📂 Каталог", "🛒 Кошик")
    m.row("🎁 Акції та Інфо", "👤 Профіль")
    m.row(types.KeyboardButton("🎮 Грати та отримати знижку", web_app=types.WebAppInfo(url=WEB_APP_URL)))
    m.row("📞 Консультант", "📰 Новини")
    return m

def contact_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    m.add(types.KeyboardButton("📱 Надіслати свій номер телефону", request_contact=True))
    m.add("⬅️ Назад до меню")
    return m

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    user_data = db_manage_user(user_id)
    
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        referrer_id = int(args[1])
        if referrer_id != user_id and user_data[2] is None: 
            with sqlite3.connect(DB_NAME) as conn:
                c = conn.cursor()
                c.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer_id, user_id))
                conn.commit()

    bot.send_message(user_id, f"👋 Вітаємо у {SHOP_NAME}! Оберіть пункт меню:", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "⬅️ Назад до меню")
def back_to_menu(message):
    if message.chat.id in user_data_cache:
        del user_data_cache[message.chat.id]
    bot.send_message(message.chat.id, "Ви в головному меню:", reply_markup=main_menu())

# --- ПРОФІЛЬ ТА ІНТЕГРАЦІЯ POSTER ---
@bot.message_handler(commands=['me', 'profile'])
@bot.message_handler(func=lambda m: m.text == "👤 Профіль")
def profile_cmd(message):
    user_id = message.chat.id
    user_data = db_manage_user(user_id)
    phone = user_data[0] 
    
    if phone:
        display_profile(message, phone, user_data[1]) 
    else:
        user_data_cache[user_id] = {'step': 'register_phone'}
        bot.send_message(user_id, "👤 **Оформлення карти клієнта**\n\nЩоб отримувати кешбек та знижки, поділіться своїм номером телефону.", reply_markup=contact_menu(), parse_mode="Markdown")

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    user_id = message.chat.id
    phone = message.contact.phone_number
    if not phone.startswith('+'): phone = '+' + phone
    
    if user_id in user_data_cache and user_data_cache[user_id].get('step') == 'register_phone':
        user_data_cache[user_id]['phone'] = phone
        user_data_cache[user_id]['step'] = 'register_name'
        
        client_poster = get_poster_client(phone)
        if client_poster:
            db_manage_user(user_id, phone=phone)
            bot.send_message(user_id, f"✅ Ваш профіль знайдено в базі {SHOP_NAME}!", reply_markup=main_menu())
            
            user_db = db_manage_user(user_id)
            if user_db[1] > 0:
                add_poster_bonus(client_poster['client_id'], user_db[1])
                db_manage_user(user_id, discount=0)
                bot.send_message(user_id, f"💸 Ваші акційні **{user_db[1]} грн** автоматично перенесені на бонусну карту!", parse_mode="Markdown")
            
            display_profile(message, phone, db_manage_user(user_id)[1])
            del user_data_cache[user_id]
        else:
            bot.send_message(user_id, "Введіть ваше ПІБ (Прізвище та Ім'я):", reply_markup=types.ReplyKeyboardRemove())
    else:
        db_manage_user(user_id, phone=phone)
        client_poster = get_poster_client(phone)
        if client_poster:
            user_db = db_manage_user(user_id)
            if user_db[1] > 0:
                add_poster_bonus(client_poster['client_id'], user_db[1])
                db_manage_user(user_id, discount=0)
                bot.send_message(user_id, f"💸 Ваші акційні **{user_db[1]} грн** автоматично перенесені на бонусну карту!", parse_mode="Markdown")
        bot.send_message(user_id, "Номер збережено.", reply_markup=main_menu())

def display_profile(message, phone, game_discount):
    user_id = message.chat.id
    bot_name = bot.get_me().username
    ref_link = f"https://t.me/{bot_name}?start={user_id}"
    
    client_poster = get_poster_client(phone)
    poster_bonus = float(client_poster.get('bonus', 0)) / 100 if client_poster else 0.0
    group_name = client_poster.get('group_name', 'Постійний клієнт') if client_poster else 'Новий клієнт'
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🪪 Моя карта (Штрих-код на касу)", callback_data="show_qr"))

    text = (f"👤 **Ваш кабінет лояльності**\n\n"
            f"🏷 Статус: *{group_name}*\n"
            f"📱 Телефон: `{phone}`\n\n"
            f"💰 Баланс: **{int(poster_bonus)} {SHOP_CURRENCY}**\n"
            f"*(всі бонуси за друзів та ігри накопичуються тут)*\n\n"
            f"🔗 **Реферальна програма:**\n"
            f"Запрошуй друзів та отримуй **50 {SHOP_CURRENCY}** на рахунок!\n")
    
    if game_discount > 0:
        text += f"\n⚠️ У вас є **{game_discount} {SHOP_CURRENCY}** знижки, яка чекає на перенесення в базу."
    
    bot.send_message(user_id, text, reply_markup=markup, parse_mode="Markdown")
    bot.send_message(user_id, f"`{ref_link}`", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "show_qr")
def show_qr_callback(call):
    user_id = call.message.chat.id
    user_data = db_manage_user(user_id)
    phone = user_data[0]
    
    if not phone: return bot.answer_callback_query(call.id, "Спочатку надайте номер телефону!", show_alert=True)
    
    client_poster = get_poster_client(phone)
    poster_bonus = float(client_poster.get('bonus', 0)) / 100 if client_poster else 0.0

    img_barcode = generate_customer_barcode(phone) 
    caption = f"🪪 **Цифрова карта клієнта**\n💰 Баланс: **{int(poster_bonus)} {SHOP_CURRENCY}**\n\nПокажіть цей штрих-код касиру."
    bot.send_photo(user_id, img_barcode, caption=caption, parse_mode="Markdown")

# --- КАТАЛОГ ТА ДІЇ ---
@bot.message_handler(func=lambda m: m.text == "📂 Каталог")
def show_cats(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for cat_id, cat_name in CATEGORIES.items(): markup.add(types.InlineKeyboardButton(cat_name, callback_data=f"cat_{cat_id}"))
    bot.send_message(message.chat.id, "Оберіть категорію:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("cat_"))
def show_items(call):
    bot.answer_callback_query(call.id)
    cat_id = call.data.split("_")[1]
    for key, item in PRODUCTS.items():
        if item["category"] == cat_id: send_product_card(call.message.chat.id, key)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_") or call.data.startswith("info_"))
def item_actions(call):
    action, key = call.data.split("_", 1)
    if action == "buy":
        if db_add_to_cart_with_reserve(call.message.chat.id, key):
            bot.answer_callback_query(call.id, f"✅ {PRODUCTS[key]['name']} заброньовано на 15 хв!")
        else:
            bot.answer_callback_query(call.id, "❌ Недостатньо товару!", show_alert=True)
    elif action == "info":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, PRODUCTS[key]['info'], parse_mode="Markdown")
        send_product_card(call.message.chat.id, key)

# --- ТАПАЛКА / ІГРОВА ЗНИЖКА ---
@bot.message_handler(content_types=['web_app_data'])
def get_discount(message):
    try:
        match = re.search(r'\d+', message.web_app_data.data)
        if match:
            disc = int(match.group())
            user_id = message.chat.id
            
            user_data = db_manage_user(user_id)
            phone = user_data[0] if user_data else None
            
            if phone:
                client_poster = get_poster_client(phone)
                if client_poster:
                    add_poster_bonus(client_poster['client_id'], disc)
                    db_manage_user(user_id, discount=0)
                    bot.send_message(user_id, f"🍀 Супер! **{disc} {SHOP_CURRENCY}** успішно зараховано на твій бонусний рахунок!", parse_mode="Markdown")
                    return
            
            db_manage_user(user_id, discount=disc)
            bot.send_message(user_id, f"🍀 Супер! Знижка **{disc} {SHOP_CURRENCY}** збережена.\n\n⚠️ Обов'язково зареєструй **👤 Профіль**, щоб ці гроші перейшли на ваш рахунок і їх можна було використати на касі!", parse_mode="Markdown")
    except Exception as e:
        print("Помилка тапалки:", e)

# --- КОШИК ТА ОФОРМЛЕННЯ ЗАМОВЛЕННЯ ---
@bot.message_handler(func=lambda m: m.text == "🛒 Кошик")
def cart_cmd(message): render_cart(message.chat.id)

def render_cart(chat_id, message_id=None):
    raw_items = db_get_cart_with_expiry(chat_id)
    if not raw_items:
        text = "🛒 Ваш кошик порожній."
        if message_id: bot.edit_message_text(text, chat_id, message_id)
        else: bot.send_message(chat_id, text)
        return
        
    items = [row[0] for row in raw_items]
    total = sum(PRODUCTS[k]['price'] for k in items)
    
    user_data = db_manage_user(chat_id)
    phone = user_data[0]
    local_discount = user_data[1] 
    
    poster_bonus = 0.0
    if phone:
        client_poster = get_poster_client(phone)
        if client_poster: poster_bonus = float(client_poster.get('bonus', 0)) / 100

    total_benefit = local_discount + poster_bonus
    min_expiry_str = min([row[1] for row in raw_items])
    mins_left = max(1, int((datetime.strptime(min_expiry_str, "%Y-%m-%d %H:%M:%S") - datetime.now()).total_seconds() / 60))

    markup = types.InlineKeyboardMarkup(row_width=3)
    item_counts = {k: items.count(k) for k in set(items)}
    summary = ""
    for k, count in item_counts.items():
        summary += f"• {PRODUCTS[k]['name']} x{count} = {PRODUCTS[k]['price'] * count} {SHOP_CURRENCY}\n"
        markup.row(types.InlineKeyboardButton("➖", callback_data=f"crem_{k}"), types.InlineKeyboardButton(f"{count} шт", callback_data="ignore"), types.InlineKeyboardButton("➕", callback_data=f"cadd_{k}"))
        
    markup.row(types.InlineKeyboardButton("💳 Оформити замовлення", callback_data="start_checkout"))
    markup.row(types.InlineKeyboardButton("🗑 Очистити кошик", callback_data="clear_cart"))
    
    text = f"**Ваш кошик:**\n\n{summary}\n"
    text += f"💰 **Сума товарів: {total} {SHOP_CURRENCY}**\n"
    if total_benefit > 0: 
        text += f"🎁 Доступно бонусів: {int(total_benefit)} {SHOP_CURRENCY}\n"
        text += f"*(При доставці бонусами можна оплатити до 30% чека. При самовивозі — списання на касі)*\n"
    text += f"\n⏳ *Бронь ще на {mins_left} хв!*"
    
    if message_id: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    else: bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("cadd_") or call.data.startswith("crem_"))
def mod_cart(call):
    key = call.data.split("_", 1)[1]
    if call.data.startswith("cadd_"):
        if not db_add_to_cart_with_reserve(call.message.chat.id, key):
            bot.answer_callback_query(call.id, "❌ Немає в наявності!", show_alert=True); return
    elif call.data.startswith("crem_"): db_remove_one_from_cart(call.message.chat.id, key)
    bot.answer_callback_query(call.id); render_cart(call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "clear_cart")
def clr_cart(call):
    bot.answer_callback_query(call.id); db_clear_cart(call.message.chat.id)
    bot.edit_message_text("🗑 Кошик очищено.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "start_checkout")
def start_checkout(call):
    bot.answer_callback_query(call.id)
    m = types.InlineKeyboardMarkup()
    m.row(types.InlineKeyboardButton("🏃‍♂️ Самовивіз", callback_data="order_pickup"),
          types.InlineKeyboardButton("🚚 Доставка", callback_data="order_delivery"))
    bot.edit_message_text("📦 Оберіть спосіб отримання:", call.message.chat.id, call.message.message_id, reply_markup=m)

# --- ЛОГІКА САМОВИВОЗУ (БЕЗ ОПЛАТИ) ---
def process_pickup_order(user_id):
    items = db_get_cart_with_expiry(user_id)
    if not items:
        bot.send_message(user_id, "Ваш кошик порожній.")
        return

    purchased_items = [row[0] for row in items]
    total_price = sum(PRODUCTS[k]['price'] for k in purchased_items)

    user_data = db_manage_user(user_id)
    phone = user_data[0] if user_data else None
    local_discount = user_data[1]

    if phone and local_discount > 0:
        client_poster = get_poster_client(phone)
        if client_poster:
            add_poster_bonus(client_poster['client_id'], local_discount)
            db_manage_user(user_id, discount=0)

    products_list = []
    for k in set(purchased_items):
        count = purchased_items.count(k)
        poster_id = PRODUCTS[k].get("poster_id", 0)
        products_list.append({"product_id": poster_id, "count": count})

    order_data_poster = {
        "spot_id": SPOT_ID,
        "phone": phone if phone else "",
        "products": products_list,
        "comment": "❗️САМОВИВІЗ (Бронь на 3 години). Оплата на касі."
    }

    if phone:
        client_poster = get_poster_client(phone)
        if client_poster: order_data_poster["client_id"] = client_poster["client_id"]

    res_order = poster_request("incomingOrders.createIncomingOrder", "POST", order_data_poster)

    if res_order and "error" in res_order:
        bot.send_message(user_id, "⚠️ Сталася помилка при створенні броні. Зв'яжіться з адміністратором.")
        return
    
    db_confirm_purchase(user_id)
    
    bot.send_message(user_id, "✅ **Ваше замовлення успішно заброньовано на 3 години!**\n\nОплата та використання бонусів відбудуться на касі при отриманні. Просто покажіть касиру ваш штрих-код із розділу 👤 **Профіль**.", parse_mode="Markdown")

    if ADMIN_ID:
        try:
            summary = ", ".join([f"{PRODUCTS[k]['name']} (x{purchased_items.count(k)})" for k in set(purchased_items)])
            bot.send_message(ADMIN_ID, f"🔔 **НОВА БРОНЬ (Самовивіз)!**\n👤 Клієнт: {phone}\n📦 Товари: {summary}\n💰 Сума: {total_price} {SHOP_CURRENCY}\n*(Якщо не заберуть, поверніть залишки через меню складу)*")
        except: pass

    if user_id in user_data_cache:
        del user_data_cache[user_id]

@bot.callback_query_handler(func=lambda call: call.data.startswith("order_"))
def process_order_type(call):
    user_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    if call.data == "order_pickup":
        user_data_cache[user_id] = {'order_type': 'pickup'}
        process_pickup_order(user_id)
    else:
        user_data_cache[user_id] = {'order_type': 'delivery', 'step': 'order_city'}
        bot.send_message(user_id, "🏙 Введіть місто доставки:", reply_markup=types.ReplyKeyboardRemove())

# --- ЛОГІКА ДОСТАВКИ (ОНЛАЙН ОПЛАТА, МАКС 30% БОНУСАМИ) ---
def send_invoice(chat_id):
    items = [row[0] for row in db_get_cart_with_expiry(chat_id)]
    if not items: 
        bot.send_message(chat_id, "Ваш кошик порожній.")
        return
        
    total_price = sum(PRODUCTS[k]['price'] for k in items)
    prices = [types.LabeledPrice(f"{PRODUCTS[k]['name']} x{items.count(k)}", PRODUCTS[k]['price'] * items.count(k) * 100) for k in set(items)]
    
    user_data = db_manage_user(chat_id)
    phone = user_data[0]
    local_discount = user_data[1]
    
    poster_bonus_uah = 0.0
    if phone:
        client_poster = get_poster_client(phone)
        if client_poster: poster_bonus_uah = float(client_poster.get('bonus', 0)) / 100

    total_available_benefit = local_discount + poster_bonus_uah
    max_allowed_bonus = total_price * 0.30
    used_benefit_uah = min(total_available_benefit, max_allowed_bonus)

    if used_benefit_uah > 0:
        prices.append(types.LabeledPrice("🎁 Знижка (Макс 30%)", -int(used_benefit_uah * 100)))
    
    used_local = min(local_discount, used_benefit_uah)
    used_poster = used_benefit_uah - used_local
    
    payload = f"pay_{used_poster}_{used_local}"
    bot.send_invoice(chat_id, SHOP_NAME, "Оплата замовлення (Доставка)", payload, PAYMENT_TOKEN, SHOP_CURRENCY, prices, need_phone_number=True, need_shipping_address=False)

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def success(message):
    bot.send_message(message.chat.id, "✅ Дякуємо за оплату! Замовлення передано в обробку.")
    
    user_id = message.chat.id
    purchased_items = [row[0] for row in db_get_cart_with_expiry(user_id)]
    original_price = sum(PRODUCTS[k]['price'] for k in purchased_items)
    paid_amount = message.successful_payment.total_amount / 100
    total_discount = original_price - paid_amount
    
    used_poster_bonus_uah = 0.0
    used_local_discount = 0.0
    payload_parts = message.successful_payment.invoice_payload.split("_")
    if len(payload_parts) >= 3:
        try: 
            used_poster_bonus_uah = float(payload_parts[1])
            used_local_discount = float(payload_parts[2])
        except: pass

    user_data = db_manage_user(user_id)
    phone = user_data[0] if user_data else None
    remaining_local = user_data[1] - used_local_discount

    db_confirm_purchase(user_id) 

    order_info = user_data_cache.get(user_id, {})
    address_str = f"Доставка: м. {order_info.get('city', '')}, вул. {order_info.get('street', '')}, {order_info.get('house', '')}"

    if phone:
        products_list = []
        ratio = paid_amount / original_price if original_price > 0 else 1
        
        for k in set(purchased_items):
            count = purchased_items.count(k)
            poster_id = PRODUCTS[k].get("poster_id", 0)
            orig_price_uah = PRODUCTS[k]['price']
            final_price_uah = orig_price_uah * ratio
            
            products_list.append({
                "product_id": poster_id,
                "count": count,
                "price": int(round(final_price_uah * 100))
            })

        order_data_poster = {
            "spot_id": SPOT_ID,
            "phone": phone,
            "products": products_list,
            "comment": f"[{address_str}] ❗️ОПЛАЧЕНО В TELEGRAM: {paid_amount} {SHOP_CURRENCY}. (Знижка: {total_discount} {SHOP_CURRENCY})"
        }
        
        client_poster = get_poster_client(phone)
        if client_poster:
            order_data_poster["client_id"] = client_poster["client_id"]
            
        poster_request("incomingOrders.createIncomingOrder", "POST", order_data_poster)
        
        if client_poster:
            if used_poster_bonus_uah > 0:
                add_poster_bonus(client_poster['client_id'], -used_poster_bonus_uah)
            if remaining_local > 0:
                add_poster_bonus(client_poster['client_id'], remaining_local)

    if ADMIN_ID:
        try:
            summary = ", ".join([f"{PRODUCTS[k]['name']} (x{purchased_items.count(k)})" for k in set(purchased_items)])
            bot.send_message(ADMIN_ID, f"🚨 **ЗАМОВЛЕННЯ ОПЛАЧЕНО!**\n👤 Клієнт: @{message.from_user.username}\n📍 {address_str}\n📦 Товари: {summary}\n💰 Сума: {paid_amount} {SHOP_CURRENCY}")
        except: pass
        
    if user_id in user_data_cache:
        del user_data_cache[user_id]

# --- АДМІНКА ТА СКАНУВАННЯ QR ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if str(message.chat.id) != str(ADMIN_ID): return
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("📦 Склад", callback_data="admin_stock"), types.InlineKeyboardButton("📢 Розсилка", callback_data="admin_broadcast"))
    bot.send_message(message.chat.id, "👨‍💻 **Адмін-панель**\n\nЩоб списати бонуси клієнта на фізичній касі, просто надішліть сюди його номер телефону (або зіскануйте його штрих-код).", reply_markup=m, parse_mode="Markdown")

@bot.message_handler(func=lambda m: str(m.chat.id) == str(ADMIN_ID) and re.match(r'^\+?\d{10,15}$', m.text.strip()))
def admin_scan_qr(message):
    phone = normalize_phone(message.text.strip())
    client_poster = get_poster_client(phone)
    
    if not client_poster:
        bot.send_message(message.chat.id, f"❌ Клієнта з номером {phone} не знайдено в базі.")
        return

    bonus = float(client_poster.get('bonus', 0)) / 100
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💸 Списати бонуси", callback_data=f"admindeduct_{client_poster['client_id']}_{phone}"))
    
    text = f"👤 **Клієнт знайдений!**\n\n📱 Телефон: `{phone}`\n🧑 Ім'я: {client_poster.get('firstname', 'Невідомо')} {client_poster.get('lastname', '')}\n💰 Баланс: **{bonus} {SHOP_CURRENCY}**"
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admindeduct_"))
def admin_deduct_prompt(call):
    _, client_id, phone = call.data.split("_")
    msg = bot.send_message(call.message.chat.id, f"Скільки бонусів ви хочете списати? (Введіть суму в {SHOP_CURRENCY}):")
    bot.register_next_step_handler(msg, process_admin_deduct, client_id, phone)

def process_admin_deduct(message, client_id, phone):
    try:
        amount_uah = float(message.text.replace(',', '.'))
        client_poster = get_poster_client(phone)
        if client_poster:
            current_bonus_kopecks = int(client_poster.get('bonus', 0))
            current_bonus_uah = current_bonus_kopecks / 100
            
            if amount_uah > current_bonus_uah:
                bot.send_message(message.chat.id, f"❌ Помилка: У клієнта лише {current_bonus_uah} бонусів!")
                return

            add_poster_bonus(client_id, -amount_uah)
            bot.send_message(message.chat.id, f"✅ Успішно списано {amount_uah} бонусів. Новий баланс: {current_bonus_uah - amount_uah} {SHOP_CURRENCY}.")
            
            with sqlite3.connect(DB_NAME) as conn:
                res = conn.cursor().execute("SELECT user_id FROM users WHERE phone = ?", (phone,)).fetchone()
                if res:
                    try: bot.send_message(res[0], f"💸 З вашої карти лояльності списано {amount_uah} бонусів на касі.")
                    except: pass
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Помилка: Введіть коректне число.")

@bot.callback_query_handler(func=lambda call: call.data == "admin_stock")
def admin_stock_cats(call):
    bot.answer_callback_query(call.id)
    m = types.InlineKeyboardMarkup(row_width=1)
    for cat_id, cat_name in CATEGORIES.items(): m.add(types.InlineKeyboardButton(cat_name, callback_data=f"astockcat_{cat_id}"))
    bot.edit_message_text("📦 Категорія для складу:", call.message.chat.id, call.message.message_id, reply_markup=m)

@bot.callback_query_handler(func=lambda call: call.data.startswith("astockcat_"))
def admin_stock_items(call):
    cat_id = call.data.split("_")[1]
    m = types.InlineKeyboardMarkup(row_width=1)
    for key, item in PRODUCTS.items():
        if item["category"] == cat_id: m.add(types.InlineKeyboardButton(f"{item['name']} ({db_get_stock(key)} шт)", callback_data=f"astockedit_{key}"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_stock"))
    bot.edit_message_text("📦 Тисніть для зміни кількості:", call.message.chat.id, call.message.message_id, reply_markup=m)

@bot.callback_query_handler(func=lambda call: call.data.startswith("astockedit_"))
def admin_stock_edit(call):
    key = call.data.split("_")[1]
    msg = bot.send_message(call.message.chat.id, f"Введіть нову кількість для **{PRODUCTS[key]['name']}**:")
    bot.register_next_step_handler(msg, process_stock_update, key)

def process_stock_update(message, key):
    try:
        qty = int(message.text); db_set_stock(key, qty)
        bot.send_message(message.chat.id, f"✅ Оновлено: {qty} шт.")
    except: bot.send_message(message.chat.id, "⚠️ Тільки цифри!")

@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast")
def admin_broadcast_req(call):
    if str(call.message.chat.id) != str(ADMIN_ID): return
    msg = bot.send_message(call.message.chat.id, "Текст для розсилки:")
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(message):
    with sqlite3.connect(DB_NAME) as conn:
        users = conn.cursor().execute("SELECT user_id FROM users").fetchall()
    count = 0
    for u in users:
        try: bot.send_message(u[0], f"📢 **Новини Магазину:**\n\n{message.text}", parse_mode="Markdown"); count += 1
        except: pass
    bot.send_message(ADMIN_ID, f"✅ Отримали: {count} юзерів.")

# --- ОБРОБНИК ТЕКСТУ (FSM ТА AI) ---
@bot.message_handler(func=lambda m: True)
def handle_all_text(message):
    user_id = message.chat.id
    text = message.text

    if user_id in user_data_cache and 'step' in user_data_cache[user_id]:
        state = user_data_cache[user_id]
        step = state['step']

        if step == 'register_name':
            state['name'] = text
            state['step'] = 'register_sex'
            m = types.ReplyKeyboardMarkup(resize_keyboard=True)
            m.row("👨 Чоловіча", "👩 Жіноча")
            bot.send_message(user_id, "Оберіть стать:", reply_markup=m)
            return

        elif step == 'register_sex':
            state['sex'] = 1 if text == "👨 Чоловіча" else 2 if text == "👩 Жіноча" else 0
            state['step'] = 'register_birthday'
            bot.send_message(user_id, "Введіть дату народження (формат: ДД.ММ.РРРР):", reply_markup=types.ReplyKeyboardRemove())
            return

        elif step == 'register_birthday':
            if re.match(r'^\d{2}\.\d{2}\.\d{4}$', text):
                state['birthday'] = text
                state['step'] = 'register_email'
                m = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Пропустити ➡️")
                bot.send_message(user_id, "Введіть E-mail (або натисніть 'Пропустити'):", reply_markup=m)
            else:
                bot.send_message(user_id, "❌ Неправильний формат. Введіть дату як 31.12.1990:")
            return

        elif step == 'register_email':
            state['email'] = text if text != "Пропустити ➡️" else ""
            bot.send_message(user_id, "⏳ Зберігаємо дані...", reply_markup=types.ReplyKeyboardRemove())
            
            db_manage_user(user_id, phone=state['phone'])
            create_poster_client_full(user_id)
            
            bot.send_message(user_id, "🎉 Реєстрація успішна! Ваша карта створена.", reply_markup=main_menu())
            
            if 'order_type' not in state:
                del user_data_cache[user_id]
            else:
                del state['step']
            return

        elif step == 'order_city':
            state['city'] = text
            state['step'] = 'order_street'
            bot.send_message(user_id, "Введіть вулицю:")
            return
            
        elif step == 'order_street':
            state['street'] = text
            state['step'] = 'order_house'
            bot.send_message(user_id, "Введіть номер будинку та квартири (або номер відділення):")
            return
            
        elif step == 'order_house':
            state['house'] = text
            del state['step']
            bot.send_message(user_id, "⏳ Формуємо рахунок...")
            send_invoice(user_id)
            return

    if message.text in ["📂 Каталог", "🛒 Кошик", "📞 Консультант", "🎮 Грати та отримати знижку", "📰 Новини", "🎁 Акції та Інфо", "👤 Профіль"]: 
        if message.text == "📰 Новини": 
            return bot.send_message(message.chat.id, "Тут будуть ваші новини та оновлення асортименту.")
        if message.text == "🎁 Акції та Інфо": 
            return bot.send_message(message.chat.id, "Інформація про систему лояльності, знижки та поточні акції магазину.")
        return
        
    bot.send_chat_action(message.chat.id, 'typing')
    
    history = db_manage_history(user_id)
    db_manage_history(user_id, "user", message.text)
    avail = [f"{k}: {p['name']} ({p['price']} {SHOP_CURRENCY})" for k, p in PRODUCTS.items() if db_get_stock(k) > 0]
    
    # Універсальний промпт для AI
    system_prompt = f"Ти AI-консультант магазину {SHOP_NAME}. Допомагай клієнтам обирати товари. В наявності зараз: {', '.join(avail)}. Якщо радиш товар, вказуй його ключ у квадратних дужках, наприклад [item1]."
    
    try:
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": message.text}])
        ai_text = response.choices[0].message.content
        db_manage_history(user_id, "assistant", ai_text)
        keys = re.findall(r'\[([a-zA-Z0-9_]+)\]', ai_text)
        bot.send_message(user_id, re.sub(r'\[[a-zA-Z0-9_]+\]', '', ai_text).strip())
        for k in keys:
            if k in PRODUCTS and db_get_stock(k) > 0: send_product_card(user_id, k)
    except: bot.send_message(user_id, "⚠️ AI асистент тимчасово недоступний.")

if __name__ == "__main__":
    init_db()
    bot.infinity_polling()

