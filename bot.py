import telebot
from telebot import types
import time
import os
from openai import OpenAI

# --- ENV ---
TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")

if not TOKEN or not OPENAI_API_KEY or not PAYMENT_TOKEN:
    raise ValueError("ENV variables missing")

bot = telebot.TeleBot(TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

ADMIN_ID = 6887361815

# --- ТОВАРИ ---
PRODUCTS = {
    "sleep": {"name": "Happy caps sleep 💤", "price": 400},
    "gaba": {"name": "Габа #9 🧠", "price": 450},
    "energy": {"name": "Happy caps energy ⚡", "price": 350},
    "cream": {"name": "СБД Крем 🧴", "price": 600},
    "vape": {"name": "Вейп 💨", "price": 850},
    "jelly": {"name": "СБД Желе 🍬", "price": 500}
}

user_carts = {}

# --- МЕНЮ ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📂 Каталог", "🛒 Кошик")
    markup.add("📞 Консультант")
    return markup

# --- START ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "👋 Вітаю! Обери дію:", reply_markup=main_menu())

# --- КАТАЛОГ ---
@bot.message_handler(func=lambda m: m.text == "📂 Каталог")
def catalog(message):
    markup = types.InlineKeyboardMarkup()
    for key, item in PRODUCTS.items():
        markup.add(types.InlineKeyboardButton(item["name"], callback_data=f"show_{key}"))

    bot.send_message(message.chat.id, "📦 Обери товар:", reply_markup=markup)

# --- КОШИК ---
@bot.message_handler(func=lambda m: m.text == "🛒 Кошик")
def cart(message):
    chat_id = message.chat.id

    if chat_id not in user_carts or not user_carts[chat_id]:
        bot.send_message(chat_id, "🛒 Кошик порожній")
        return

    items = "\n".join([f"• {PRODUCTS[k]['name']} — {PRODUCTS[k]['price']} грн" for k in user_carts[chat_id]])
    total = sum(PRODUCTS[k]['price'] for k in user_carts[chat_id])

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Оплатити", callback_data="checkout"))
    markup.add(types.InlineKeyboardButton("🗑 Очистити", callback_data="clear"))

    bot.send_message(chat_id, f"{items}\n\n💰 {total} грн", reply_markup=markup)

# --- CALLBACK ---
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    chat_id = call.message.chat.id

    # ПОКАЗ ТОВАРУ
    if call.data.startswith("show_"):
        key = call.data.split("_")[1]
        item = PRODUCTS[key]

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"➕ Купити {item['price']} грн", callback_data=f"buy_{key}"))
        markup.add(types.InlineKeyboardButton("⬅ Назад", callback_data="back"))

        bot.send_message(chat_id, f"{item['name']}\n💰 {item['price']} грн", reply_markup=markup)
        bot.delete_message(chat_id, call.message.message_id)

    # ДОДАТИ В КОШИК
    elif call.data.startswith("buy_"):
        key = call.data.split("_")[1]
        user_carts.setdefault(chat_id, []).append(key)
        bot.answer_callback_query(call.id, "✅ Додано")

    # ОЧИСТИТИ
    elif call.data == "clear":
        user_carts[chat_id] = []
        bot.edit_message_text("🗑 Кошик очищено", chat_id, call.message.message_id)

    # НАЗАД
    elif call.data == "back":
        bot.delete_message(chat_id, call.message.message_id)
        catalog(call.message)

    # 💳 ОПЛАТА
    elif call.data == "checkout":
        if chat_id not in user_carts or not user_carts[chat_id]:
            bot.send_message(chat_id, "🛒 Кошик порожній")
            return

        prices = []
        total = 0

        for key in user_carts[chat_id]:
            item = PRODUCTS[key]
            prices.append(types.LabeledPrice(item["name"], item["price"] * 100))
            total += item["price"]

        try:
            bot.send_invoice(
                chat_id=chat_id,
                title="🛍 Happy Caps",
                description=f"До оплати: {total} грн",
                invoice_payload=f"order_{chat_id}",
                provider_token=PAYMENT_TOKEN,
                currency="UAH",
                prices=prices,
                start_parameter="pay",
                need_phone_number=True,
                need_shipping_address=True,
                is_flexible=True
            )
        except Exception as e:
            print("PAY ERROR:", e)
            bot.send_message(chat_id, "❌ Помилка оплати")

# --- ДОСТАВКА ---
@bot.shipping_query_handler(func=lambda query: True)
def shipping(shipping_query):
    options = [
        types.ShippingOption("nova", "Нова Пошта")
        .add_price(types.LabeledPrice("Доставка", 8000))
    ]

    bot.answer_shipping_query(
        shipping_query.id,
        ok=True,
        shipping_options=options
    )

# --- ПЕРЕД ОПЛАТОЮ ---
@bot.pre_checkout_query_handler(func=lambda query: True)
def pre_checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

# --- УСПІШНА ОПЛАТА ---
@bot.message_handler(content_types=['successful_payment'])
def success_payment(message):
    chat_id = message.chat.id
    total = message.successful_payment.total_amount / 100

    bot.send_message(chat_id, f"✅ Оплата пройшла!\n💰 {total} грн")

    bot.send_message(
        ADMIN_ID,
        f"""
💰 НОВА ОПЛАТА

👤 {message.from_user.first_name}
📞 {message.successful_payment.order_info.phone_number}

💵 {total} грн
"""
    )

    user_carts[chat_id] = []

# --- КОНСУЛЬТАНТ ---
@bot.message_handler(func=lambda m: m.text == "📞 Консультант")
def consultant(message):
    bot.send_message(message.chat.id, "📞 Менеджер відповість")

# --- ШІ ---
@bot.message_handler(func=lambda m: True)
def ai(message):
    if message.text in ["📂 Каталог", "🛒 Кошик", "📞 Консультант"]:
        return

    try:
        catalog_text = ", ".join([f"{p['name']} ({p['price']} грн)" for p in PRODUCTS.values()])

        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": f"Ти продавець. Товари: {catalog_text}"},
                {"role": "user", "content": message.text}
            ]
        )

        bot.reply_to(message, response.choices[0].message.content)

    except Exception as e:
        print("AI ERROR:", e)
        bot.reply_to(message, "⚠️ ШІ не відповідає")

# --- START ---
if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(1)
    bot.infinity_polling(skip_pending=True)
