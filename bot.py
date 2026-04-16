import telebot
from telebot import types
import os
import sqlite3
from openai import OpenAI

# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_ID = os.getenv("ADMIN_ID")
WEB_APP_URL = "https://mamutpetr.github.io/Pinkcanna/"

bot = telebot.TeleBot(TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# --- БАЗА ДАНИХ ---
def init_db():
    with sqlite3.connect("pinkcanna.db") as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS carts (user_id INTEGER, product_key TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
        conn.commit()

init_db()

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
        # Дублюємо картку товару (як ви і просили)
        send_product_card(call.message.chat.id, key)

# --- КОШИК ---
@bot.message_handler(func=lambda m: m.text == "🛒 Кошик")
def show_cart(message):
    items = db_get_cart(message.chat.id)
    if not items:
        bot.send_message(message.chat.id, "🛒 Кошик порожній.")
        return
    total = sum(PRODUCTS[k]['price'] for k in items)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Оформити", callback_data="checkout"))
    markup.add(types.InlineKeyboardButton("🗑 Очистити", callback_data="clear_cart"))
    summary = "\n".join([f"• {PRODUCTS[k]['name']} x{items.count(k)}" for k in set(items)])
    bot.send_message(message.chat.id, f"**Кошик:**\n{summary}\n\n💰 **Разом: {total} грн**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "clear_cart")
def clear(call):
    db_clear_cart(call.message.chat.id)
    bot.edit_message_text("🗑 Кошик очищено.", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "checkout")
def pay(call):
    items = db_get_cart(call.message.chat.id)
    prices = [types.LabeledPrice(f"{PRODUCTS[k]['name']} x{items.count(k)}", PRODUCTS[k]['price'] * items.count(k) * 100) for k in set(items)]
    bot.send_invoice(call.message.chat.id, "Pink Canna", "Оплата", "payload", PAYMENT_TOKEN, "UAH", prices)

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def success(message):
    bot.send_message(message.chat.id, "✅ Оплачено!")
    db_clear_cart(message.chat.id)

if __name__ == "__main__":
    bot.infinity_polling()

