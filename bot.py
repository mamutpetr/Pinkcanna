import telebot
from telebot import types
import os
import sqlite3
import re
from datetime import datetime, timedelta
from openai import OpenAI

# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_ID = os.getenv("ADMIN_ID") # Ваш ID для сповіщень та доступу в адмінку
WEB_APP_URL = "https://mamutpetr.github.io/Pinkcanna/"

bot = telebot.TeleBot(TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# --- БАЗА ДАНИХ (Кошик, Знижки, Пам'ять, Склад) ---
def init_db():
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        # Новий кошик з таймером бронювання
        c.execute('''CREATE TABLE IF NOT EXISTS carts_v2 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_key TEXT, expires_at DATETIME)''')
        c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, discount INTEGER DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS ai_history (user_id INTEGER, role TEXT, content TEXT)''')
        # Таблиця складу
        c.execute('''CREATE TABLE IF NOT EXISTS inventory (product_key TEXT PRIMARY KEY, total_qty INTEGER DEFAULT 0)''')
        
        # Заповнюємо склад тестовими 20 шт для кожного товару (якщо товару ще немає в БД)
        for key in PRODUCTS.keys():
            c.execute("INSERT OR IGNORE INTO inventory (product_key, total_qty) VALUES (?, 20)", (key,))
        conn.commit()

# Очищення прострочених бронювань
def db_cleanup_expired():
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("DELETE FROM carts_v2 WHERE expires_at < ?", (now_str,))
        conn.commit()

# Отримання реальних залишків (всього на складі МІНУС активні броні)
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

# Встановлення залишків адміном
def db_set_stock(product_key, qty):
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE inventory SET total_qty = ? WHERE product_key = ?", (qty, product_key))
        conn.commit()

# Додавання в кошик (бронювання на 15 хв)
def db_add_to_cart_with_reserve(user_id, product_key):
    if db_get_stock(product_key) > 0:
        with sqlite3.connect("pinkcanna.db") as conn:
            c = conn.cursor()
            expires = datetime.now() + timedelta(minutes=15)
            c.execute("INSERT INTO carts_v2 (user_id, product_key, expires_at) VALUES (?, ?, ?)", (user_id, product_key, expires.strftime("%Y-%m-%d %H:%M:%S")))
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

# Списання зі складу при успішній оплаті
def db_confirm_purchase(user_id):
    items = [row[0] for row in db_get_cart_with_expiry(user_id)]
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        for key in items:
            c.execute("UPDATE inventory SET total_qty = total_qty - 1 WHERE product_key = ?", (key,))
        c.execute("DELETE FROM carts_v2 WHERE user_id = ?", (user_id,))
        conn.commit()
    return items

def db_manage_user(user_id, discount=None):
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        if discount is not None:
            c.execute("UPDATE users SET discount = ? WHERE user_id = ?", (discount, user_id))
        conn.commit()
        c.execute("SELECT discount FROM users WHERE user_id = ?", (user_id,))
        res = c.fetchone()
        return res[0] if res else 0

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

# Ініціалізація БД при старті коду
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
        markup.add(
            types.InlineKeyboardButton("❌ Очікується постачання", callback_data="ignore"),
            types.InlineKeyboardButton("🔍 Дізнатись більше", callback_data=f"info_{key}")
        )

    caption = f"🏷 **{item['name']}**\n\n📝 {item['short']}\n📦 {stock_text}\n💰 **Ціна: {item['price']} грн**"
    
    try:
        if os.path.exists(item['image']):
            with open(item['image'], 'rb') as photo:
                bot.send_photo(chat_id, photo, caption=caption, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, caption, reply_markup=markup, parse_mode="Markdown")
    except:
        bot.send_message(chat_id, caption, reply_markup=markup, parse_mode="Markdown")

# --- МЕНЮ ---
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.row("📂 Каталог", "🛒 Кошик")
    m.row("🧮 Підбір дози CBD")
    m.row(types.KeyboardButton("🍀 Натапати знижку", web_app=types.WebAppInfo(url=WEB_APP_URL)))
    m.row("📞 Консультант", "📰 Новини")
    return m

@bot.message_handler(commands=['start'])
def start(message):
    db_manage_user(message.chat.id)
    bot.send_message(message.chat.id, "🌿 Вітаємо у Pink Canna! Оберіть пункт меню:", reply_markup=main_menu())

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
            bot.answer_callback_query(call.id, f"✅ {PRODUCTS[key]['name']} заброньовано на 15 хв!")
        else:
            bot.answer_callback_query(call.id, "❌ Недостатньо товару в наявності!", show_alert=True)
    elif action == "info":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, PRODUCTS[key]['info'], parse_mode="Markdown")
        send_product_card(call.message.chat.id, key)

# --- ТАПАЛКА ---
@bot.message_handler(content_types=['web_app_data'])
def get_discount(message):
    try:
        match = re.search(r'\d+', message.web_app_data.data)
        if match:
            disc = int(match.group())
            db_manage_user(message.chat.id, disc)
            bot.send_message(message.chat.id, f"🍀 Супер! Знижка **{disc} грн** збережена.", parse_mode="Markdown")
    except: pass

# --- КОШИК (З ТАЙМЕРОМ) ---
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
    discount = db_manage_user(chat_id)
    
    # Шукаємо найближчий час згоряння броні
    min_expiry_str = min([row[1] for row in raw_items])
    min_expiry = datetime.strptime(min_expiry_str, "%Y-%m-%d %H:%M:%S")
    mins_left = max(1, int((min_expiry - datetime.now()).total_seconds() / 60))

    markup = types.InlineKeyboardMarkup(row_width=3)
    item_counts = {k: items.count(k) for k in set(items)}
        
    summary = ""
    for k, count in item_counts.items():
        summary += f"• {PRODUCTS[k]['name']} x{count} = {PRODUCTS[k]['price'] * count} грн\n"
        markup.row(
            types.InlineKeyboardButton("➖", callback_data=f"crem_{k}"),
            types.InlineKeyboardButton(f"{count} шт", callback_data="ignore"),
            types.InlineKeyboardButton("➕", callback_data=f"cadd_{k}")
        )
        
    markup.row(types.InlineKeyboardButton("💳 Оформити замовлення", callback_data="checkout"))
    markup.row(types.InlineKeyboardButton("🗑 Очистити кошик", callback_data="clear_cart"))
    
    final_total = total - discount if discount < total else 1
    text = f"**Ваш кошик:**\n\n{summary}\n"
    if discount > 0: text += f"🎁 Ваша знижка: -{discount} грн\n"
    text += f"💰 **До сплати: {final_total if discount > 0 else total} грн**\n\n"
    text += f"⏳ *Товари заброньовано за вами ще на {mins_left} хв!*"
        
    if message_id: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    else: bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("cadd_") or call.data.startswith("crem_"))
def mod_cart(call):
    key = call.data.split("_", 1)[1]
    if call.data.startswith("cadd_"):
        if not db_add_to_cart_with_reserve(call.message.chat.id, key):
            bot.answer_callback_query(call.id, "❌ Немає більше в наявності!", show_alert=True)
            return
    elif call.data.startswith("crem_"): db_remove_one_from_cart(call.message.chat.id, key)
    bot.answer_callback_query(call.id)
    render_cart(call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "clear_cart")
def clr_cart(call):
    bot.answer_callback_query(call.id)
    db_clear_cart(call.message.chat.id)
    bot.edit_message_text("🗑 Кошик очищено.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "checkout")
def pay(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    items = [row[0] for row in db_get_cart_with_expiry(chat_id)]
    if not items: return bot.send_message(chat_id, "Кошик порожній!")

    total_price = sum(PRODUCTS[k]['price'] for k in items)
    prices = [types.LabeledPrice(f"{PRODUCTS[k]['name']} x{items.count(k)}", PRODUCTS[k]['price'] * items.count(k) * 100) for k in set(items)]
    
    discount = db_manage_user(chat_id)
    if discount > 0:
        prices.append(types.LabeledPrice("🍀 Знижка", -int((total_price - 1 if discount >= total_price else discount) * 100)))

    bot.send_invoice(chat_id, "Pink Canna", "Оплата", "payload", PAYMENT_TOKEN, "UAH", prices, need_phone_number=True, need_shipping_address=True)

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def success(message):
    bot.send_message(message.chat.id, "✅ Дякуємо за оплату! Ваше замовлення прийнято в обробку.")
    purchased_items = db_confirm_purchase(message.chat.id)
    db_manage_user(message.chat.id, 0) # Згорає знижка
    
    if ADMIN_ID:
        try:
            summary = ", ".join([f"{PRODUCTS[k]['name']} (x{purchased_items.count(k)})" for k in set(purchased_items)])
            order_info = f"🚨 **НОВЕ ЗАМОВЛЕННЯ ОПЛАЧЕНО!**\n\n👤 Клієнт: @{message.from_user.username}\n📦 Товари: {summary}\n💰 Сума: {message.successful_payment.total_amount / 100} UAH"
            bot.send_message(ADMIN_ID, order_info)
        except: pass

# --- АДМІН ПАНЕЛЬ ТА КЕРУВАННЯ СКЛАДОМ ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if str(message.chat.id) != str(ADMIN_ID): return
    m = types.InlineKeyboardMarkup()
    m.add(types.InlineKeyboardButton("📦 Керування складом", callback_data="admin_stock"))
    m.add(types.InlineKeyboardButton("📢 Зробити розсилку", callback_data="admin_broadcast"))
    bot.send_message(message.chat.id, "👨‍💻 **Панель адміністратора**", reply_markup=m, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "admin_stock")
def admin_stock_cats(call):
    bot.answer_callback_query(call.id)
    if str(call.message.chat.id) != str(ADMIN_ID): return
    m = types.InlineKeyboardMarkup(row_width=1)
    for cat_id, cat_name in CATEGORIES.items(): m.add(types.InlineKeyboardButton(cat_name, callback_data=f"astockcat_{cat_id}"))
    bot.edit_message_text("📦 Оберіть категорію для оновлення залишків:", call.message.chat.id, call.message.message_id, reply_markup=m)

@bot.callback_query_handler(func=lambda call: call.data.startswith("astockcat_"))
def admin_stock_items(call):
    bot.answer_callback_query(call.id)
    cat_id = call.data.split("_")[1]
    m = types.InlineKeyboardMarkup(row_width=1)
    for key, item in PRODUCTS.items():
        if item["category"] == cat_id:
            stock = db_get_stock(key)
            m.add(types.InlineKeyboardButton(f"{item['name']} ({stock} шт)", callback_data=f"astockedit_{key}"))
    m.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_stock"))
    bot.edit_message_text(f"📦 Товари в категорії. Тисніть для зміни кількості:", call.message.chat.id, call.message.message_id, reply_markup=m)

@bot.callback_query_handler(func=lambda call: call.data.startswith("astockedit_"))
def admin_stock_edit(call):
    bot.answer_callback_query(call.id)
    key = call.data.split("_")[1]
    msg = bot.send_message(call.message.chat.id, f"Введіть нову загальну кількість в наявності для **{PRODUCTS[key]['name']}** (цифрою):", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_stock_update, key)

def process_stock_update(message, key):
    try:
        qty = int(message.text)
        db_set_stock(key, qty)
        bot.send_message(message.chat.id, f"✅ Залишки **{PRODUCTS[key]['name']}** успішно оновлено! Тепер: {qty} шт.", parse_mode="Markdown")
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ Помилка: потрібно було ввести число.")

@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast")
def admin_broadcast_req(call):
    bot.answer_callback_query(call.id)
    if str(call.message.chat.id) != str(ADMIN_ID): return
    msg = bot.send_message(call.message.chat.id, "Надішліть текст для розсилки всім користувачам:")
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(message):
    with sqlite3.connect("pinkcanna.db") as conn:
        users = conn.cursor().execute("SELECT user_id FROM users").fetchall()
    count = 0
    for u in users:
        try:
            bot.send_message(u[0], f"📢 **Новина від Pink Canna:**\n\n{message.text}", parse_mode="Markdown")
            count += 1
        except: pass
    bot.send_message(ADMIN_ID, f"✅ Розсилку завершено. Отримали: {count} користувачів.")

# --- AI-КОНСУЛЬТАНТ ---
@bot.callback_query_handler(func=lambda call: call.data == "ai_more")
def ai_more_options(call):
    bot.answer_callback_query(call.id)
    bot.send_chat_action(call.message.chat.id, 'typing')
    handle_ai_conversation(call.message, "Запропонуй ще якісь цікаві варіанти.")

@bot.message_handler(func=lambda m: True)
def ai_consultant(message):
    if message.text in ["📂 Каталог", "🛒 Кошик", "📞 Консультант", "🍀 Натапати знижку", "📰 Новини", "🧮 Підбір дози CBD"]: return
    if message.text == "📰 Новини": return bot.send_message(message.chat.id, "🌿 Всі наші продукти легальні згідно з Постановою КМУ №324.")
    bot.send_chat_action(message.chat.id, 'typing')
    handle_ai_conversation(message, message.text)

def handle_ai_conversation(message, text_input):
    chat_id = message.chat.id
    history = db_manage_history(chat_id)
    db_manage_history(chat_id, "user", text_input)
    
    # ШІ бачить лише ті товари, які Є В НАЯВНОСТІ
    avail_products = [f"{k}: {p['name']} ({p['price']}грн)" for k, p in PRODUCTS.items() if db_get_stock(k) > 0]
    catalog_text = ", ".join(avail_products)
    
    system_prompt = (
        f"Ти експерт Pink Canna. Наш асортимент В НАЯВНОСТІ: {catalog_text}. Всі інші товари розпродані. "
        f"ПРАВИЛА:\n1. Пропонуй 1-2 товари за раз.\n2. Запитуй, чи показати ще варіанти.\n"
        f"3. ОБОВ'ЯЗКОВО вказуй 'Код' в квадратних дужках [код] для рекомендацій."
    )
    
    try:
        response = client.chat.completions.create(model="gpt-4o", messages=[{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": text_input}])
        ai_text = response.choices[0].message.content
        db_manage_history(chat_id, "assistant", ai_text)
        
        product_keys = re.findall(r'\[([a-zA-Z0-9_]+)\]', ai_text)
        clean_text = re.sub(r'\[[a-zA-Z0-9_]+\]', '', ai_text).strip()
        
        if clean_text:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔄 Показати ще варіанти", callback_data="ai_more"))
            bot.send_message(chat_id, clean_text, reply_markup=markup)
            
        for key in product_keys:
            if key in PRODUCTS and db_get_stock(key) > 0: send_product_card(chat_id, key)
    except: bot.send_message(chat_id, "⚠️ Консультант тимчасово недоступний.")

if __name__ == "__main__":
    bot.infinity_polling()

