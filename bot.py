import telebot
from telebot import types
import time
import os
from openai import OpenAI

# --- ENV ---
TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TOKEN:
    raise ValueError("BOT_TOKEN not set")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not set")

bot = telebot.TeleBot(TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# --- БАЗА ТОВАРІВ ---
PRODUCTS = {
    "sleep": {"name": "Happy caps sleep 💤", "price": 400, "file": "sleep.jpg"},
    "gaba": {"name": "Габа #9 🧠", "price": 450, "file": "gaba9.jpg"},
    "energy": {"name": "Happy caps energy ⚡", "price": 350, "file": "energy.jpg"},
    "cream": {"name": "СБД Крем 🧴", "price": 600, "file": "cream.jpg"},
    "vape": {"name": "Вейп 💨", "price": 850, "file": "blackvape.jpg"},
    "jelly": {"name": "СБД Желе 🍬", "price": 500, "file": "Cbdgele.jpg"}
}

user_carts = {}

# --- МЕНЮ ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📂 Каталог", "🛒 Кошик")
    markup.add("📦 Мої замовлення", "📞 Консультант")
    return markup

# --- START ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "👋 Вітаю! Я консультант Happy Caps. Обери дію:",
        reply_markup=main_menu()
    )

# --- КАТАЛОГ ---
@bot.message_handler(func=lambda m: m.text == "📂 Каталог")
def show_catalog(message):
    markup = types.InlineKeyboardMarkup()
    for key, item in PRODUCTS.items():
        markup.add(types.InlineKeyboardButton(item["name"], callback_data=f"show_{key}"))

    bot.send_message(message.chat.id, "📦 Обери товар:", reply_markup=markup)

# --- КОШИК ---
@bot.message_handler(func=lambda m: m.text == "🛒 Кошик")
def show_cart(message):
    chat_id = message.chat.id

    if chat_id not in user_carts or not user_carts[chat_id]:
        bot.send_message(chat_id, "🛒 Кошик порожній")
        return

    items = "\n".join([
        f"• {PRODUCTS[k]['name']} — {PRODUCTS[k]['price']} грн"
        for k in user_carts[chat_id]
    ])
    total = sum(PRODUCTS[k]['price'] for k in user_carts[chat_id])

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🚀 Оформити", callback_data="checkout"))
    markup.add(types.InlineKeyboardButton("🗑 Очистити", callback_data="clear_cart"))

    bot.send_message(chat_id, f"🛍 Кошик:\n\n{items}\n\n💰 {total} грн", reply_markup=markup)

# --- КОНСУЛЬТАНТ ---
@bot.message_handler(func=lambda m: m.text == "📞 Консультант")
def call_consultant(message):
    bot.send_message(message.chat.id, "📞 Менеджер скоро відповість")

# --- CALLBACK ---
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    chat_id = call.message.chat.id

    # --- ПОКАЗ ТОВАРУ ---
    if call.data.startswith("show_"):
        key = call.data.split("_")[1]
        item = PRODUCTS[key]

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"➕ Купити {item['price']} грн", callback_data=f"buy_{key}"))
        markup.add(types.InlineKeyboardButton("⬅ Назад", callback_data="back"))

        try:
            with open(item["file"], "rb") as photo:
                bot.send_photo(chat_id, photo, caption=f"{item['name']}\n💰 {item['price']} грн", reply_markup=markup)
        except:
            bot.send_message(chat_id, f"{item['name']}\n💰 {item['price']} грн", reply_markup=markup)

        bot.delete_message(chat_id, call.message.message_id)

    # --- КУПИТИ ---
    elif call.data.startswith("buy_"):
        key = call.data.split("_")[1]

        user_carts.setdefault(chat_id, []).append(key)
        bot.answer_callback_query(call.id, "✅ Додано")

    # --- ОФОРМЛЕННЯ ---
    elif call.data == "checkout":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(types.KeyboardButton("📱 Надіслати номер", request_contact=True))

        bot.send_message(chat_id, "Надішли номер:", reply_markup=markup)

    # --- ОЧИСТКА ---
    elif call.data == "clear_cart":
        user_carts[chat_id] = []
        bot.edit_message_text("🗑 Кошик очищено", chat_id, call.message.message_id)

    # --- НАЗАД ---
    elif call.data == "back":
        bot.delete_message(chat_id, call.message.message_id)
        show_catalog(call.message)

# --- КОНТАКТ ---
@bot.message_handler(content_types=['contact'])
def contact_handler(message):
    chat_id = message.chat.id

    if chat_id not in user_carts or not user_carts[chat_id]:
        return

    items = "\n".join(PRODUCTS[k]["name"] for k in user_carts[chat_id])
    total = sum(PRODUCTS[k]["price"] for k in user_carts[chat_id])

    report = f"""
🛍 НОВЕ ЗАМОВЛЕННЯ
👤 {message.from_user.first_name}
📞 {message.contact.phone_number}

📦:
{items}

💰 {total} грн
"""

    bot.send_message(6887361815, report)
    bot.send_message(chat_id, "✅ Замовлення прийнято!", reply_markup=main_menu())

    user_carts[chat_id] = []

# --- ШІ ---
@bot.message_handler(func=lambda m: True)
def ai_chat(message):
    if message.text in ["📂 Каталог", "🛒 Кошик", "📦 Мої замовлення", "📞 Консультант"]:
        return

    try:
        catalog = ", ".join([f"{p['name']} ({p['price']} грн)" for p in PRODUCTS.values()])

        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {
                    "role": "system",
                    "content": f"Ти Олег - консультант Pink Canna. Товари: {catalog}. Допомагай продати."
                },
                {"role": "user", "content": message.text}
            ]
        )

        bot.reply_to(message, response.choices[0].message.content)

    except Exception as e:
        print("AI ERROR:", e)
        bot.reply_to(message, "⚠️ ШІ тимчасово не працює")

# --- START BOT ---
if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(1)
    bot.infinity_polling(skip_pending=True)
