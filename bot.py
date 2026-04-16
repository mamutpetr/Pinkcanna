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
    # КАННА
    "kanna10x": {"name": "Канна 10х", "price": 2500, "image": "kanna10x.jpg", "category": "kanna", "short": "Екстракт для настрою.", "info": "🌿 **Канна 10х:** Потужний SRI-ефект для ейфорії та зняття тривоги."},
    "crystal": {"name": "Канна Crystal", "price": 3000, "image": "kannacrystal.jpg", "category": "kanna", "short": "Чистий ізолят.", "info": "💎 **Crystal:** 98% чистих алкалоїдів для ідеального фокусу."},
    "strong": {"name": "Канна Strong", "price": 3000, "image": "kannastrong.jpg", "category": "kanna", "short": "Максимальна сила.", "info": "🔥 **Strong:** Найшвидша дія для досвідчених користувачів."},
    # СБД
    "jelly": {"name": "СБД Желе", "price": 1900, "image": "Cbdgele.jpg", "category": "cbd", "short": "Смачний релакс.", "info": "🍬 **CBD Jelly:** Зручний формат для підтримки спокою протягом дня."},
    # WELLNESS
    "sleep": {"name": "Happy caps sleep", "price": 2000, "image": "sleep.jpg", "category": "wellness", "short": "Для засинання.", "info": "💤 **Sleep:** Глибокий сон та швидке відновлення."},
    "gaba": {"name": "Габа #9", "price": 400, "image": "gaba9.jpg", "category": "wellness", "short": "Спокій мозку.", "info": "🧠 **GABA:** Природне гальмо для зайвих думок та стресу."},
    "energy": {"name": "Happy caps energy", "price": 2000, "image": "energy.jpg", "category": "wellness", "short": "Бадьорість.", "info": "⚡ **Energy:** Енергія без кави та тремору."},
    # TOPICAL / VAPE
    "vape": {"name": "Вейп CBD", "price": 3000, "image": "blackvape.jpg", "category": "topical", "short": "Миттєвий релакс.", "info": "💨 **Vape:** Найшвидша доставка CBD в організм."},
    "cream": {"name": "СБД Крем", "price": 1600, "image": "cream.jpg", "category": "topical", "short": "Для м'язів.", "info": "🧴 **Cream:** Локальне зняття болю та запалень."}
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

# --- МЕНЮ ТА КАТАЛОГ ---
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("📂 Каталог", "🛒 Кошик")
    m.add(types.KeyboardButton("🍀 Натапати знижку", web_app=types.WebAppInfo(url=WEB_APP_URL)))
    m.add("📞 Консультант", "📰 Новини")
    return m

@bot.message_handler(commands=['start'])
def start(message):
    add_user(message.chat.id)
    bot.send_message(message.chat.id, "🌿 Вітаємо у Pink Canna!", reply_markup=main_menu())

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
        # Надсилаємо повний опис
        bot.send_message(call.message.chat.id, PRODUCTS[key]['info'], parse_mode="Markdown")
        # Дублюємо картку товару
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
            print("Не вдалося відправити сповіщення адміну:", e)

    db_clear_cart(message.chat.id)
    if message.chat.id in user_tapped_discounts:
        user_tapped_discounts[message.chat.id] = 0

# --- АДМІН ПАНЕЛЬ ---
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if str(message.chat.id) != str(ADMIN_ID):
        return
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
    if message.text in ["📂 Каталог", "🛒 Кошик", "📞 Консультант", "🍀 Натапати знижку", "📰 Новини"]: return
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

