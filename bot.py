import telebot
from telebot import types
import os
import sqlite3
import re
import qrcode
from io import BytesIO
from datetime import datetime, timedelta
from openai import OpenAI

# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_ID = os.getenv("ADMIN_ID") 
WEB_APP_URL = "https://mamutpetr.github.io/Pinkcanna/"

bot = telebot.TeleBot(TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# --- БАЗА ДАНИХ (Кошик, Знижки, Пам'ять, Склад, Лояльність) ---
def init_db():
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS carts_v2 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_key TEXT, expires_at DATETIME)''')
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (user_id INTEGER PRIMARY KEY, discount INTEGER DEFAULT 0, balance REAL DEFAULT 0, referred_by INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS ai_history 
                     (user_id INTEGER, role TEXT, content TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS inventory 
                     (product_key TEXT PRIMARY KEY, total_qty INTEGER DEFAULT 0)''')
        
        for key in PRODUCTS.keys():
            c.execute("INSERT OR IGNORE INTO inventory (product_key, total_qty) VALUES (?, 20)", (key,))
        conn.commit()

def db_cleanup_expired():
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("DELETE FROM carts_v2 WHERE expires_at < ?", (now_str,))
        conn.commit()

def db_get_stock(product_key):
    db_cleanup_expired()
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute("SELECT total_qty FROM inventory WHERE product_key = ?", (product_key,))
        res = c.fetchone()
        total = res[0] if res else 0
        c.execute("SELECT COUNT(*) FROM carts_v2 WHERE product_key = ?", (product_key,))
        reserved = c.fetchone()[0]
        return max(0, total - reserved)

def db_set_stock(product_key, qty):
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE inventory SET total_qty = ? WHERE product_key = ?", (qty, product_key))
        conn.commit()

def db_add_to_cart_with_reserve(user_id, product_key):
    if db_get_stock(product_key) > 0:
        with sqlite3.connect("pinkcanna.db") as conn:
            c = conn.cursor()
            expires = datetime.now() + timedelta(minutes=15)
            c.execute("INSERT INTO carts_v2 (user_id, product_key, expires_at) VALUES (?, ?, ?)", 
                      (user_id, product_key, expires.strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
        return True
    return False

def db_get_cart_with_expiry(user_id):
    db_cleanup_expired()
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute("SELECT product_key, expires_at FROM carts_v2 WHERE user_id = ?", (user_id,))
        return c.fetchall()

def db_remove_one_from_cart(user_id, product_key):
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute("DELETE FROM carts_v2 WHERE id = (SELECT id FROM carts_v2 WHERE user_id = ? AND product_key = ? LIMIT 1)", (user_id, product_key))
        conn.commit()

def db_clear_cart(user_id):
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute("DELETE FROM carts_v2 WHERE user_id = ?", (user_id,))
        conn.commit()

def db_confirm_purchase(user_id):
    items = [row[0] for row in db_get_cart_with_expiry(user_id)]
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        for key in items:
            c.execute("UPDATE inventory SET total_qty = total_qty - 1 WHERE product_key = ?", (key,))
        c.execute("DELETE FROM carts_v2 WHERE user_id = ?", (user_id,))
        c.execute("UPDATE users SET discount = 0, balance = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
    return items

def db_manage_user(user_id, discount=None):
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)", (user_id,))
        if discount is not None:
            c.execute("UPDATE users SET discount = ? WHERE user_id = ?", (discount, user_id))
        conn.commit()
        c.execute("SELECT discount, balance FROM users WHERE user_id = ?", (user_id,))
        return c.fetchone()

def db_add_referral_bonus(referrer_id):
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET balance = balance + 50 WHERE user_id = ?", (referrer_id,))
        conn.commit()

def db_manage_history(user_id, role=None, content=None):
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        if role and content:
            c.execute("INSERT INTO ai_history VALUES (?, ?, ?)", (user_id, role, content))
            c.execute("DELETE FROM ai_history WHERE rowid NOT IN (SELECT rowid FROM ai_history WHERE user_id = ? ORDER BY rowid DESC LIMIT 10)", (user_id,))
            conn.commit()
        c.execute("SELECT role, content FROM ai_history WHERE user_id = ? ORDER BY rowid ASC", (user_id,))
        return [{"role": row[0], "content": row[1]} for row in c.fetchall()]

# --- ТОВАРИ ---
CATEGORIES = {"kanna": "🌿 Екстракти Канни", "cbd": "💧 Олії та Релакс", "wellness": "🧠 Сон та Енергія", "topical": "🧴 Вейпи та Догляд"}

PRODUCTS = {
    "kanna10x": {"name": "Канна 10х", "price": 2500, "image": "kanna10x.jpg", "category": "kanna", "short": "Екстракт для настрою.", "info": "🌿 **Канна 10х:** Потужний SRI-ефект для ейфорії та зняття тривоги."},
    "crystal": {"name": "Канна Crystal", "price": 3000, "image": "kannacrystal.jpg", "category": "kanna", "short": "Чистий ізолят.", "info": "💎 **Crystal:** 98% чистих алкалоїдів для ідеального фокусу."},
    "strong": {"name": "Канна Strong", "price": 3000, "image": "kannastrong.jpg", "category": "kanna", "short": "Максимальна сила.", "info": "🔥 **Strong:** Найшвидша дія для досвідчених користувачів."},
    "jelly": {"name": "СБД Желе", "price": 1900, "image": "Cbdgele.jpg", "category": "cbd", "short": "Смачний релакс.", "info": "🍬 **CBD Jelly:** Зручний формат для підтримки спокою протягом дня."},
    "cbd_5_10": {"name": "Олія CBD 5% (10мл)", "price": 800, "image": "cbd_5_10.jpg", "category": "cbd", "short": "35мг в піпетці", "info": "💧 **Олія CBD 5%:** Ідеально для легкого стресу та профілактики."},
    "cbd_10_10": {"name": "Олія CBD 10% (10мл)", "price": 1300, "image": "cbd_10_10.jpg", "category": "cbd", "short": "70мг в піпетці", "info": "💧 **Олія CBD 10%:** Універсальна концентрація для сну та спокою."},
    "cbd_15_10": {"name": "Олія CBD 15% (10мл)", "price": 1800, "image": "cbd_15_10.jpg", "category": "cbd", "short": "105мг в піпетці", "info": "💧 **Олія CBD 15%:** Для хронічного болю та підвищеної тривожності."},
    "cbd_20_10": {"name": "Олія CBD 20% (10мл)", "price": 2100, "image": "cbd_20_10.jpg", "category": "cbd", "short": "140мг в піпетці", "info": "💧 **Олія CBD 20%:** Сильна дія для серйозних симптомів."},
    "cbd_30_10": {"name": "Олія CBD 30% (10мл)", "price": 3400, "image": "cbd_30_10.jpg", "category": "cbd", "short": "210мг в піпетці", "info": "💧 **Олія CBD 30%:** Максимальна концентрація."},
    "cbd_5_30": {"name": "Олія CBD 5% (30мл)", "price": 2000, "image": "cbd_5_30.jpg", "category": "cbd", "short": "Економ формат", "info": "💧 **Олія CBD 5% (30мл):** Вигідний формат."},
    "cbd_10_30": {"name": "Олія CBD 10% (30мл)", "price": 3400, "image": "cbd_10_30.jpg", "category": "cbd", "short": "Економ формат", "info": "💧 **Олія CBD 10% (30мл):** Вигідний формат."},
    "cbd_15_30": {"name": "Олія CBD 15% (30мл)", "price": 4500, "image": "cbd_15_30.jpg", "category": "cbd", "short": "Економ формат", "info": "💧 **Олія CBD 15% (30мл):** Вигідний формат."},
    "cbd_20_30": {"name": "Олія CBD 20% (30мл)", "price": 5200, "image": "cbd_20_30.jpg", "category": "cbd", "short": "Економ формат", "info": "💧 **Олія CBD 20% (30мл):** Вигідний формат."},
    "cbd_30_30": {"name": "Олія CBD 30% (30мл)", "price": 8200, "image": "cbd_30_30.jpg", "category": "cbd", "short": "Економ формат", "info": "💧 **Олія CBD 30% (30мл):** Вигідний формат."},
    "sleep": {"name": "Happy caps sleep", "price": 2000, "image": "sleep.jpg", "category": "wellness", "short": "Для засинання.", "info": "💤 **Sleep:** Глибокий сон та швидке відновлення."},
    "gaba": {"name": "Габа #9", "price": 400, "image": "gaba9.jpg", "category": "wellness", "short": "Спокій мозку.", "info": "🧠 **GABA:** Природне гальмо для зайвих думок та стресу."},
    "energy": {"name": "Happy caps energy", "price": 2000, "image": "energy.jpg", "category": "wellness", "short": "Бадьорість.", "info": "⚡ **Energy:** Енергія без кави та тремору."},
    "vape": {"name": "Вейп CBD", "price": 3000, "image": "blackvape.jpg", "category": "topical", "short": "Миттєвий релакс.", "info": "💨 **Vape:** Найшвидша доставка CBD в організм."},
    "cream": {"name": "СБД Крем", "price": 1600, "image": "cream.jpg", "category": "topical", "short": "Для м'язів.", "info": "🧴 **Cream:** Локальне зняття болю та запалень."}
}

DOSAGE_DATA = {
    "ptsd_insomnia": {"name": "ПТСР / Безсоння / Артрит", "doses": {50: 78, 60: 85, 70: 93, 80: 100, 90: 108, 100: 115, 110: 123, 120: 130}},
    "pain": {"name": "Хронічний біль", "doses": {50: 91, 60: 99, 70: 106, 80: 113, 90: 120, 100: 128, 110: 135, 120: 142}},
    "stress": {"name": "Стрес / Фобії", "doses": {50: 64, 60: 68, 70: 73, 80: 77, 90: 82, 100: 87, 110: 91, 120: 95}},
    "depression": {"name": "Депресія", "doses": {50: 76, 60: 88, 70: 99, 80: 111, 90: 122, 100: 133, 110: 145, 120: 156}},
    "migraine": {"name": "Мігрень", "doses": {50: 85, 60: 87, 70: 90, 80: 93, 90: 96, 100: 99, 110: 102, 120: 105}},
    "epilepsy": {"name": "Епілепсія", "doses": {50: 174, 60: 210, 70: 245, 80: 280, 90: 315, 100: 350, 110: 385, 120: 420}}
}
CONC_DATA = {5: {"10ml": 35, "30ml": 50}, 10: {"10ml": 70, "30ml": 100}, 15: {"10ml": 105, "30ml": 150}, 20: {"10ml": 140, "30ml": 200}, 30: {"10ml": 210, "30ml": 300}}

init_db()

# --- ВІДПРАВКА КАРТКИ ТОВАРУ ---
def send_product_card(chat_id, key):
    item = PRODUCTS[key]
    stock = db_get_stock(key)
    markup = types.InlineKeyboardMarkup(row_width=1)
    if stock > 0:
        stock_text = f"🟢 В наявності: {stock} шт"
        markup.add(
            types.InlineKeyboardButton(f"🛒 Додати в кошик ({item['price']} грн)", callback_data=f"buy_{key}"),
            types.InlineKeyboardButton("🔍 Дізнатись більше", callback_data=f"info_{key}")
        )
    else:
        stock_text = "🔴 Немає в наявності"
        markup.add(types.InlineKeyboardButton("🔍 Дізнатись більше", callback_data=f"info_{key}"))
    caption = f"🏷 **{item['name']}**\n\n📝 {item['short']}\n📦 {stock_text}\n💰 **Ціна: {item['price']} грн**"
    try:
        if os.path.exists(item['image']):
            with open(item['image'], 'rb') as photo: bot.send_photo(chat_id, photo, caption=caption, reply_markup=markup, parse_mode="Markdown")
        else: bot.send_message(chat_id, caption, reply_markup=markup, parse_mode="Markdown")
    except: bot.send_message(chat_id, caption, reply_markup=markup, parse_mode="Markdown")

# --- ДОДАТКОВІ ФУНКЦІЇ (QR) ---
def generate_customer_qr(user_id):
    qr_data = f"https://t.me/{bot.get_me().username}?start=scan_{user_id}"
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = BytesIO()
    img.save(bio, 'PNG')
    bio.seek(0)
    return bio

# --- МЕНЮ ---
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.row("📂 Каталог", "🛒 Кошик")
    m.row("🧮 Підбір дози CBD", "👤 Профіль")
    m.row(types.KeyboardButton("🍀 Натапати знижку", web_app=types.WebAppInfo(url=WEB_APP_URL)))
    m.row("📞 Консультант", "📰 Новини")
    return m

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    db_manage_user(user_id)
    args = message.text.split()
    if len(args) > 1:
        # Рефералка
        if args[1].isdigit():
            referrer_id = int(args[1])
            if referrer_id != user_id:
                with sqlite3.connect("pinkcanna.db") as conn:
                    c = conn.cursor()
                    c.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,))
                    res = c.fetchone()
                    if res and res[0] is None:
                        c.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer_id, user_id))
                        conn.commit()
                        db_add_referral_bonus(referrer_id)
                        bot.send_message(referrer_id, "🎁 Твій друг приєднався! Тобі нараховано **50 грн** бонусу!")
        # Скан для адміна
        elif args[1].startswith("scan_"):
            if str(user_id) != str(ADMIN_ID):
                bot.send_message(user_id, "❌ Доступ лише для персоналу магазину.")
                return
            scanned_id = args[1].split("_")[1]
            discount, balance = db_manage_user(scanned_id)
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(f"✅ Списати {int(balance)} грн", callback_data=f"off_pay_{scanned_id}"))
            bot.send_message(ADMIN_ID, f"👤 **Карта клієнта розпізнана!**\nID: `{scanned_id}`\n💰 Бонуси: **{int(balance)} грн**\n\nСписати при покупці?", 
                             reply_markup=markup, parse_mode="Markdown")
    bot.send_message(user_id, "🌿 Вітаємо у Pink Canna! Оберіть пункт меню:", reply_markup=main_menu())

# --- ПРОФІЛЬ ТА КАРТА ---
@bot.message_handler(func=lambda m: m.text == "👤 Профіль")
def profile_cmd(message):
    user_id = message.chat.id
    discount, balance = db_manage_user(user_id)
    bot_name = bot.get_me().username
    ref_link = f"https://t.me/{bot_name}?start={user_id}"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🪪 Моя карта (QR)", callback_data="show_qr"))
    text = (f"👤 **Твій кабінет Pink Canna**\n\n💰 Бонусний рахунок: **{int(balance)} грн**\n🍀 Знижка з тапалки: **{discount} грн**\n\n🔗 **Реферальне посилання:**")
    bot.send_message(user_id, text, reply_markup=markup, parse_mode="Markdown")
    bot.send_message(user_id, f"`{ref_link}`", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "show_qr")
def show_qr_callback(call):
    user_id = call.message.chat.id
    _, balance = db_manage_user(user_id)
    qr = generate_customer_qr(user_id)
    caption = f"🪪 **Твоя цифрова карта**\n💰 Баланс: **{int(balance)} грн**\n\nПокажи цей код продавцю для списання бонусів."
    bot.send_photo(user_id, qr, caption=caption, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("off_pay_"))
def off_pay_confirm(call):
    if str(call.message.chat.id) != str(ADMIN_ID): return
    client_id = call.data.split("_")[2]
    with sqlite3.connect("pinkcanna.db") as conn:
        conn.cursor().execute("UPDATE users SET balance = 0 WHERE user_id = ?", (client_id,))
    bot.edit_message_text(f"✅ Бонуси клієнта {client_id} успішно використані в офлайні.", call.message.chat.id, call.message.message_id)
    bot.send_message(client_id, "🎁 Ваші бонуси були успішно списані в магазині. Дякуємо за візит!")

# --- КАЛЬКУЛЯТОР ДОЗИ ---
@bot.message_handler(func=lambda m: m.text == "🧮 Підбір дози CBD")
def calc_start(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, data in DOSAGE_DATA.items(): markup.add(types.InlineKeyboardButton(data["name"], callback_data=f"calc_diag_{key}"))
    bot.send_message(message.chat.id, "🩺 **Крок 1/3:** Оберіть ваш симптом:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("calc_diag_"))
def calc_weight(call):
    bot.answer_callback_query(call.id)
    diag_key = call.data.replace("calc_diag_", "")
    markup = types.InlineKeyboardMarkup(row_width=4)
    markup.add(*[types.InlineKeyboardButton(f"{w} кг", callback_data=f"calc_weight_{diag_key}_{w}") for w in range(50, 130, 10)])
    markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="calc_back"))
    bot.edit_message_text("⚖️ **Крок 2/3:** Оберіть вашу вагу тіла:", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("calc_weight_"))
def calc_conc(call):
    bot.answer_callback_query(call.id)
    parts = call.data.split("_")
    diag_key, weight = parts[2], int(parts[3])
    dose = DOSAGE_DATA[diag_key]["doses"][weight]
    markup = types.InlineKeyboardMarkup(row_width=5)
    markup.add(*[types.InlineKeyboardButton(f"{c}%", callback_data=f"calc_res_{diag_key}_{weight}_{c}") for c in [5, 10, 15, 20, 30]])
    markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"calc_diag_{diag_key}"))
    text = f"🎯 Ваша орієнтовна норма: **{dose} мг** CBD на добу.\n\n🧪 **Крок 3/3:** Оберіть концентрацію олії CBD:"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("calc_res_"))
def calc_result(call):
    bot.answer_callback_query(call.id)
    parts = call.data.split("_")
    diag_key, weight, conc = parts[2], int(parts[3]), int(parts[4])
    dose = DOSAGE_DATA[diag_key]["doses"][weight]
    text = (f"📊 **Ваш розрахунок:**\n🩺 Симптом: **{DOSAGE_DATA[diag_key]['name']}**\n⚖️ Вага: **{weight} кг**\n🎯 Добова норма: **{dose} мг** CBD\n\n"
            f"💧 **Як приймати ({conc}%):**\n• Флакон 10 мл: `~ {round(dose / CONC_DATA[conc]['10ml'], 1)} піпетки`\n"
            f"• Флакон 30 мл: `~ {round(dose / CONC_DATA[conc]['30ml'], 1)} піпетки`\n\n💡 *Порада: розділіть дозу на ранок та вечір.*")
    markup = types.InlineKeyboardMarkup(row_width=1)
    if db_get_stock(f"cbd_{conc}_10") > 0: markup.add(types.InlineKeyboardButton(f"🛒 Додати {conc}% (10мл)", callback_data=f"buy_cbd_{conc}_10"))
    if db_get_stock(f"cbd_{conc}_30") > 0: markup.add(types.InlineKeyboardButton(f"🛒 Додати {conc}% (30мл)", callback_data=f"buy_cbd_{conc}_30"))
    markup.add(types.InlineKeyboardButton("🔄 Розрахувати заново", callback_data="calc_back"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "calc_back")
def calc_back(call):
    bot.answer_callback_query(call.id); calc_start(call.message)

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
            bot.answer_callback_query(call.id, f"✅ {PRODUCTS[key]['name']} заброньовано!")
        else:
            bot.answer_callback_query(call.id, "❌ Недостатньо товару!", show_alert=True)
    elif action == "info":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, PRODUCTS[key]['info'], parse_mode="Markdown")

# --- КОШИК ---
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
    discount, balance = db_manage_user(chat_id)
    total_benefit = discount + balance
    markup = types.InlineKeyboardMarkup(row_width=3)
    item_counts = {k: items.count(k) for k in set(items)}
    summary = ""
    for k, count in item_counts.items():
        summary += f"• {PRODUCTS[k]['name']} x{count} = {PRODUCTS[k]['price'] * count} грн\n"
        markup.row(types.InlineKeyboardButton("➖", callback_data=f"crem_{k}"), types.InlineKeyboardButton(f"{count} шт", callback_data="ignore"), types.InlineKeyboardButton("➕", callback_data=f"cadd_{k}"))
    markup.row(types.InlineKeyboardButton("💳 Оформити замовлення", callback_data="checkout"))
    markup.row(types.InlineKeyboardButton("🗑 Очистити кошик", callback_data="clear_cart"))
    final_total = total - total_benefit if total_benefit < total else 1
    text = f"**Ваш кошик:**\n\n{summary}\n💰 **До сплати: {final_total} грн**"
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

@bot.callback_query_handler(func=lambda call: call.data == "checkout")
def pay(call):
    chat_id = call.message.chat.id
    items = [row[0] for row in db_get_cart_with_expiry(chat_id)]
    if not items: return
    total_price = sum(PRODUCTS[k]['price'] for k in items)
    prices = [types.LabeledPrice(f"{PRODUCTS[k]['name']} x{items.count(k)}", PRODUCTS[k]['price'] * items.count(k) * 100) for k in set(items)]
    discount, balance = db_manage_user(chat_id)
    benefit = discount + balance
    if benefit > 0:
        prices.append(types.LabeledPrice("🎁 Бонуси", -int((total_price - 1 if benefit >= total_price else benefit) * 100)))
    bot.send_invoice(chat_id, "Pink Canna", "Оплата", "payload", PAYMENT_TOKEN, "UAH", prices, need_phone_number=True, need_shipping_address=True)

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def success(message):
    bot.send_message(message.chat.id, "✅ Дякуємо за оплату!")
    db_confirm_purchase(message.chat.id)

# --- АДМІНКА ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if str(message.chat.id) != str(ADMIN_ID): return
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("📦 Склад", callback_data="admin_stock"), types.InlineKeyboardButton("📢 Розсилка", callback_data="admin_broadcast"))
    bot.send_message(message.chat.id, "👨‍💻 **Адмін-панель**", reply_markup=m, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "admin_stock")
def admin_stock_cats(call):
    m = types.InlineKeyboardMarkup(row_width=1)
    for cat_id, cat_name in CATEGORIES.items(): m.add(types.InlineKeyboardButton(cat_name, callback_data=f"astockcat_{cat_id}"))
    bot.edit_message_text("📦 Категорія складу:", call.message.chat.id, call.message.message_id, reply_markup=m)

@bot.callback_query_handler(func=lambda call: call.data.startswith("astockcat_"))
def admin_stock_items(call):
    cat_id = call.data.split("_")[1]
    m = types.InlineKeyboardMarkup(row_width=1)
    for key, item in PRODUCTS.items():
        if item["category"] == cat_id: m.add(types.InlineKeyboardButton(f"{item['name']} ({db_get_stock(key)} шт)", callback_data=f"astockedit_{key}"))
    bot.edit_message_text("📦 Оберіть товар:", call.message.chat.id, call.message.message_id, reply_markup=m)

@bot.callback_query_handler(func=lambda call: call.data.startswith("astockedit_"))
def admin_stock_edit(call):
    key = call.data.split("_")[1]
    msg = bot.send_message(call.message.chat.id, f"Введіть кількість для **{PRODUCTS[key]['name']}**:")
    bot.register_next_step_handler(msg, process_stock_update, key)

def process_stock_update(message, key):
    try:
        qty = int(message.text); db_set_stock(key, qty)
        bot.send_message(message.chat.id, f"✅ Оновлено: {qty} шт.")
    except: bot.send_message(message.chat.id, "⚠️ Помилка.")

# --- AI КОНСУЛЬТАНТ ---
@bot.message_handler(func=lambda m: True)
def ai_consultant(message):
    if message.text in ["📂 Каталог", "🛒 Кошик", "📞 Консультант", "🍀 Натапати знижку", "📰 Новини", "🧮 Підбір дози CBD", "👤 Профіль"]: return
    if message.text == "📰 Новини": return bot.send_message(message.chat.id, "🌿 СБД легальний (Постанова №324).")
    try:
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": message.text}])
        bot.send_message(message.chat.id, response.choices[0].message.content)
    except: pass

if __name__ == "__main__":
    bot.infinity_polling()

