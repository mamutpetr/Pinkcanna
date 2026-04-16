import telebot
from telebot import types
import os
import sqlite3
import re
from openai import OpenAI

# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_ID = os.getenv("ADMIN_ID") # Ваш ID для сповіщень
WEB_APP_URL = "https://mamutpetr.github.io/Pinkcanna/"

bot = telebot.TeleBot(TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# Словник для збереження знижок з тапалки
user_tapped_discounts = {}

# --- БАЗА ДАНИХ ---
def init_db():
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS carts (user_id INTEGER, product_key TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
        conn.commit()

init_db()

def add_user(user_id):
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()

def db_add_to_cart(user_id, product_key):
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute("INSERT INTO carts (user_id, product_key) VALUES (?, ?)", (user_id, product_key))
        conn.commit()

def db_get_cart(user_id):
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute("SELECT product_key FROM carts WHERE user_id = ?", (user_id,))
        return [row[0] for row in c.fetchall()]

def db_clear_cart(user_id):
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute("DELETE FROM carts WHERE user_id = ?", (user_id,))
        conn.commit()

# --- КАТЕГОРІЇ ТА ТОВАРИ ---
CATEGORIES = {
    "kanna": "🌿 Екстракти Канни",
    "cbd": "🍬 СБД та Релакс",
    "wellness": "🧠 Сон та Енергія",
    "topical": "🧴 Вейпи та Догляд"
}

PRODUCTS = {
    "kanna10x": {"name": "Канна 10х", "price": 2500, "image": "kanna10x.jpg", "category": "kanna", "short": "Екстракт для настрою.", "info": "🌿 **Канна 10х:** Потужний SRI-ефект для ейфорії та зняття тривоги."},
    "crystal": {"name": "Канна Crystal", "price": 3000, "image": "kannacrystal.jpg", "category": "kanna", "short": "Чистий ізолят.", "info": "💎 **Crystal:** 98% чистих алкалоїдів для ідеального фокусу."},
    "strong": {"name": "Канна Strong", "price": 3000, "image": "kannastrong.jpg", "category": "kanna", "short": "Максимальна сила.", "info": "🔥 **Strong:** Найшвидша дія для досвідчених користувачів."},
    "jelly": {"name": "СБД Желе", "price": 1900, "image": "Cbdgele.jpg", "category": "cbd", "short": "Смачний релакс.", "info": "🍬 **CBD Jelly:** Зручний формат для підтримки спокою протягом дня."},
    "sleep": {"name": "Happy caps sleep", "price": 2000, "image": "sleep.jpg", "category": "wellness", "short": "Для засинання.", "info": "💤 **Sleep:** Глибокий сон та швидке відновлення."},
    "gaba": {"name": "Габа #9", "price": 400, "image": "gaba9.jpg", "category": "wellness", "short": "Спокій мозку.", "info": "🧠 **GABA:** Природне гальмо для зайвих думок та стресу."},
    "energy": {"name": "Happy caps energy", "price": 2000, "image": "energy.jpg", "category": "wellness", "short": "Бадьорість.", "info": "⚡ **Energy:** Енергія без кави та тремору."},
    "vape": {"name": "Вейп CBD", "price": 3000, "image": "blackvape.jpg", "category": "topical", "short": "Миттєвий релакс.", "info": "💨 **Vape:** Найшвидша доставка CBD в організм."},
    "cream": {"name": "СБД Крем", "price": 1600, "image": "cream.jpg", "category": "topical", "short": "Для м'язів.", "info": "🧴 **Cream:** Локальне зняття болю та запалень."}
}

# --- ДАНІ КАЛЬКУЛЯТОРА ДОЗИ ---
DOSAGE_DATA = {
    "ptsd_insomnia": {"name": "ПТСР / Безсоння / Артрит", "doses": {50: 78, 60: 85, 70: 93, 80: 100, 90: 108, 100: 115, 110: 123, 120: 130}},
    "pain": {"name": "Хронічний біль", "doses": {50: 91, 60: 99, 70: 106, 80: 113, 90: 120, 100: 128, 110: 135, 120: 142}},
    "stress": {"name": "Стрес / Фобії", "doses": {50: 64, 60: 68, 70: 73, 80: 77, 90: 82, 100: 87, 110: 91, 120: 95}},
    "depression": {"name": "Депресія", "doses": {50: 76, 60: 88, 70: 99, 80: 111, 90: 122, 100: 133, 110: 145, 120: 156}},
    "migraine": {"name": "Мігрень", "doses": {50: 85, 60: 87, 70: 90, 80: 93, 90: 96, 100: 99, 110: 102, 120: 105}},
    "epilepsy": {"name": "Епілепсія", "doses": {50: 174, 60: 210, 70: 245, 80: 280, 90: 315, 100: 350, 110: 385, 120: 420}}
}

# Дані про вміст CBD в 1 піпетці
CONC_DATA = {
    5: {"10ml": 35, "30ml": 50},
    10: {"10ml": 70, "30ml": 100},
    15: {"10ml": 105, "30ml": 150},
    20: {"10ml": 140, "30ml": 200},
    30: {"10ml": 210, "30ml": 300}
}

# --- ФУНКЦІЯ ВІДПРАВКИ КАРТКИ ТОВАРУ ---
def send_product_card(chat_id, key):
    item = PRODUCTS[key]
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(f"🛒 Купити за {item['price']} грн", callback_data=f"buy_{key}"),
        types.InlineKeyboardButton("🔍 Дізнатись більше", callback_data=f"info_{key}")
    )
    caption = f"🏷 **{item['name']}**\n\n📝 {item['short']}\n\n💰 **Ціна: {item['price']} грн**"
    try:
        if os.path.exists(item['image']):
            with open(item['image'], 'rb') as photo:
                bot.send_photo(chat_id, photo, caption=caption, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, caption, reply_markup=markup, parse_mode="Markdown")
    except:
        bot.send_message(chat_id, caption, reply_markup=markup, parse_mode="Markdown")

# --- ГОЛОВНЕ МЕНЮ ---
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.row("📂 Каталог", "🛒 Кошик")
    m.row("🧮 Підбір дози CBD")
    m.row(types.KeyboardButton("🍀 Натапати знижку", web_app=types.WebAppInfo(url=WEB_APP_URL)))
    m.row("📞 Консультант", "📰 Новини")
    return m

@bot.message_handler(commands=['start'])
def start(message):
    add_user(message.chat.id)
    bot.send_message(message.chat.id, "🌿 Вітаємо у Pink Canna!", reply_markup=main_menu())

# --- КАЛЬКУЛЯТОР ДОЗИ (ІНТЕРАКТИВНИЙ) ---
@bot.message_handler(func=lambda m: m.text == "🧮 Підбір дози CBD")
def calculator_start(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, data in DOSAGE_DATA.items():
        markup.add(types.InlineKeyboardButton(data["name"], callback_data=f"calc_diag_{key}"))
    bot.send_message(message.chat.id, "🩺 **Крок 1/3:** Оберіть ваш основний симптом або діагноз:", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("calc_diag_"))
def calculator_weight(call):
    diag_key = call.data.replace("calc_diag_", "")
    markup = types.InlineKeyboardMarkup(row_width=4)
    buttons = [types.InlineKeyboardButton(f"{w} кг", callback_data=f"calc_weight_{diag_key}_{w}") for w in range(50, 130, 10)]
    markup.add(*buttons)
    markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="calc_back"))
    bot.edit_message_text("⚖️ **Крок 2/3:** Оберіть вашу вагу тіла:", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("calc_weight_"))
def calculator_concentration(call):
    parts = call.data.split("_")
    diag_key = parts[2]
    weight = int(parts[3])
    dose = DOSAGE_DATA[diag_key]["doses"][weight]

    markup = types.InlineKeyboardMarkup(row_width=5)
    conc_buttons = [types.InlineKeyboardButton(f"{c}%", callback_data=f"calc_res_{diag_key}_{weight}_{c}") for c in [5, 10, 15, 20, 30]]
    markup.add(*conc_buttons)
    markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data=f"calc_diag_{diag_key}"))

    text = f"🎯 Ваша орієнтовна норма: **{dose} мг** CBD на добу.\n\n🧪 **Крок 3/3:** Оберіть концентрацію олії CBD, щоб розрахувати об'єм в піпетках:"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("calc_res_"))
def calculator_result(call):
    parts = call.data.split("_")
    diag_key = parts[2]
    weight = int(parts[3])
    conc = int(parts[4])
    
    dose = DOSAGE_DATA[diag_key]["doses"][weight]
    diag_name = DOSAGE_DATA[diag_key]["name"]
    
    pipette_10ml = CONC_DATA[conc]["10ml"]
    pipette_30ml = CONC_DATA[conc]["30ml"]
    
    amt_10ml = round(dose / pipette_10ml, 1)
    amt_30ml = round(dose / pipette_30ml, 1)

    text = (
        f"📊 **Ваш індивідуальний розрахунок:**\n\n"
        f"🩺 Симптом: **{diag_name}**\n"
        f"⚖️ Вага: **{weight} кг**\n"
        f"🧪 Концентрація: **{conc}%**\n"
        f"🎯 Добова норма: **{dose} мг** CBD\n\n"
        f"💧 **Як приймати (в піпетках на добу):**\n"
        f"• Якщо флакон **10 мл** (1 піпетка = {pipette_10ml} мг):\n  Вам потрібно `~ {amt_10ml} піпетки`\n"
        f"• Якщо флакон **30 мл** (1 піпетка = {pipette_30ml} мг):\n  Вам потрібно `~ {amt_30ml} піпетки`\n\n"
        f"💡 *Порада: розділіть цю дозу на ранковий та вечірній прийом.*\n"
        f"*(Даний розрахунок базується на стандартних протоколах дозування)*"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔄 Розрахувати заново", callback_data="calc_back"))
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "calc_back")
def calc_back(call):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, data in DOSAGE_DATA.items():
        markup.add(types.InlineKeyboardButton(data["name"], callback_data=f"calc_diag_{key}"))
    bot.edit_message_text("🩺 **Крок 1/3:** Оберіть ваш основний симптом або діагноз:", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")


# --- КАТАЛОГ ---
@bot.message_handler(func=lambda m: m.text == "📂 Каталог")
def show_categories(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for cat_id, cat_name in CATEGORIES.items():
        markup.add(types.InlineKeyboardButton(cat_name, callback_data=f"cat_{cat_id}"))
    bot.send_message(message.chat.id, "Оберіть категорію:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("cat_"))
def show_category_items(call):
    cat_id = call.data.split("_")[1]
    bot.answer_callback_query(call.id)
    for key, item in PRODUCTS.items():
        if item["category"] == cat_id:
            send_product_card(call.message.chat.id, key)

# --- ОБРОБКА ДАНИХ З ТАПАЛКИ ---
@bot.message_handler(content_types=['web_app_data'])
def get_discount_from_webapp(message):
    try:
        data = message.web_app_data.data
        discount_amount = int(re.search(r'\d+', data).group())
        user_tapped_discounts[message.chat.id] = discount_amount
        bot.send_message(message.chat.id, f"🍀 Супер! Знижка **{discount_amount} грн** активована. Перейдіть до кошика для оформлення.", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, "⚠️ Не вдалося розпізнати знижку. Спробуйте ще раз.")

# --- ОБРОБКА КНОПОК ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_") or call.data.startswith("info_"))
def handle_actions(call):
    action, key = call.data.split("_")
    
    if action == "buy":
        db_add_to_cart(call.message.chat.id, key)
        bot.answer_callback_query(call.id, f"✅ {PRODUCTS[key]['name']} додано!")
        
    elif action == "info":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, PRODUCTS[key]['info'], parse_mode="Markdown")
        send_product_card(call.message.chat.id, key)

# --- КОШИК ---
@bot.message_handler(func=lambda m: m.text == "🛒 Кошик")
def show_cart(message):
    chat_id = message.chat.id
    items = db_get_cart(chat_id)
    
    if not items:
        bot.send_message(chat_id, "🛒 Ваш кошик порожній.")
        return
        
    total = sum(PRODUCTS[k]['price'] for k in items)
    discount = user_tapped_discounts.get(chat_id, 0)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Оформити", callback_data="checkout"))
    markup.add(types.InlineKeyboardButton("🗑 Очистити", callback_data="clear_cart"))
    
    summary = "\n".join([f"• {PRODUCTS[k]['name']} x{items.count(k)}" for k in set(items)])
    
    text = f"**Ваш кошик:**\n{summary}\n\n"
    if discount > 0:
        final_total = total - discount if discount < total else 1
        text += f"🎁 Знижка з тапалки: -{discount} грн\n💰 **До сплати: {final_total} грн**"
    else:
        text += f"💰 **Разом: {total} грн**"
        
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "clear_cart")
def clear(call):
    db_clear_cart(call.message.chat.id)
    if call.message.chat.id in user_tapped_discounts:
        user_tapped_discounts[call.message.chat.id] = 0
    bot.edit_message_text("🗑 Кошик очищено.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "checkout")
def pay(call):
    chat_id = call.message.chat.id
    items = db_get_cart(chat_id)
    
    if not items:
        bot.answer_callback_query(call.id, "Кошик порожній!")
        return

    total_price = sum(PRODUCTS[k]['price'] for k in items)
    prices = [types.LabeledPrice(f"{PRODUCTS[k]['name']} x{items.count(k)}", PRODUCTS[k]['price'] * items.count(k) * 100) for k in set(items)]
    
    discount = user_tapped_discounts.get(chat_id, 0)
    if discount > 0:
        if discount >= total_price: 
            discount = total_price - 1
        prices.append(types.LabeledPrice("🍀 Знижка", -int(discount * 100)))

    bot.send_invoice(
        chat_id, "Pink Canna", "Оплата замовлення", "payload", PAYMENT_TOKEN, "UAH", prices, 
        need_phone_number=True, need_shipping_address=True
    )

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(q): 
    bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def success(message):
    bot.send_message(message.chat.id, "✅ Дякуємо за оплату! Ваше замовлення прийнято в обробку.")
    
    if ADMIN_ID:
        try:
            items = db_get_cart(message.chat.id)
            summary = ", ".join([f"{PRODUCTS[k]['name']} (x{items.count(k)})" for k in set(items)])
            order_info = (
                f"🚨 **НОВЕ ЗАМОВЛЕННЯ ОПЛАЧЕНО!**\n\n"
                f"👤 Клієнт: @{message.from_user.username}\n"
                f"📦 Товари: {summary}\n"
                f"💰 Сума: {message.successful_payment.total_amount / 100} {message.successful_payment.currency}"
            )
            bot.send_message(ADMIN_ID, order_info)
        except Exception as e:
            pass

    db_clear_cart(message.chat.id)
    if message.chat.id in user_tapped_discounts:
        user_tapped_discounts[message.chat.id] = 0

# --- АДМІН ПАНЕЛЬ ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if str(message.chat.id) != str(ADMIN_ID): return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📢 Зробити розсилку", callback_data="admin_broadcast"))
    bot.send_message(message.chat.id, "👨‍💻 **Панель адміністратора**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast")
def admin_broadcast_req(call):
    if str(call.message.chat.id) != str(ADMIN_ID): return
    msg = bot.send_message(call.message.chat.id, "Надішліть текст для розсилки всім користувачам:")
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(message):
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        users = c.fetchall()
    count = 0
    for u in users:
        try:
            bot.send_message(u[0], f"📢 **Новина від Pink Canna:**\n\n{message.text}", parse_mode="Markdown")
            count += 1
        except: pass
    bot.send_message(ADMIN_ID, f"✅ Розсилку завершено. Отримали: {count} користувачів.")

# --- AI-КОНСУЛЬТАНТ ТА НОВИНИ ---
@bot.message_handler(func=lambda m: m.text == "📰 Новини")
def news_section(message):
    bot.send_message(message.chat.id, "🌿 Всі наші продукти легальні згідно з Постановою КМУ №324.")

@bot.message_handler(func=lambda m: True)
def ai_consultant(message):
    if message.text in ["📂 Каталог", "🛒 Кошик", "📞 Консультант", "🍀 Натапати знижку", "📰 Новини", "🧮 Підбір дози CBD"]: return
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "Ти експерт Pink Canna."}, {"role": "user", "content": message.text}]
        )
        bot.send_message(message.chat.id, response.choices[0].message.content)
    except: 
        bot.send_message(message.chat.id, "⚠️ Консультант тимчасово недоступний.")

if __name__ == "__main__":
    bot.infinity_polling()

