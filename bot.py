import telebot
from telebot import types
import time
import os
import threading
import json
import re
from openai import OpenAI

# --- ENV ---
TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")

bot = telebot.TeleBot(TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

ADMIN_ID = 6887361815

# --- ДАНІ ---
PRODUCTS = {
    "sleep": {"name": "Happy caps sleep 💤", "price": 400},
    "gaba": {"name": "Габа #9 🧠", "price": 450},
    "energy": {"name": "Happy caps energy ⚡", "price": 350},
    "cream": {"name": "СБД Крем 🧴", "price": 600},
    "vape": {"name": "Вейп 💨", "price": 850},
    "jelly": {"name": "СБД Желе 🍬", "price": 500}
}

PROMO_CODES = {
    "SALE10": 0.1
}

user_carts = {}
users = set()
orders = []

# --- SAVE ORDERS ---
def save_orders():
    with open("orders.json", "w") as f:
        json.dump(orders, f)

# --- МЕНЮ ---
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("📂 Каталог", "🛒 Кошик")
    m.add("🎁 Промокод", "📞 Консультант")
    return m

# --- START ---
@bot.message_handler(commands=['start'])
def start(message):
    users.add(message.chat.id)
    bot.send_message(message.chat.id, "🔥 Ласкаво просимо!", reply_markup=main_menu())

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

    items = "\n".join([f"• {PRODUCTS[k]['name']} — {PRODUCTS[k]['price']} грн x {user_carts[chat_id]['items'].count(k)}" 
                       for k in set(user_carts[chat_id]["items"])])
    total = sum(PRODUCTS[k]['price'] * user_carts[chat_id]["items"].count(k) for k in set(user_carts[chat_id]["items"]))

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Оплатити", callback_data="checkout"))
    markup.add(types.InlineKeyboardButton("🗑 Очистити", callback_data="clear"))

    bot.send_message(chat_id, f"{items}\n\n💰 {total} грн", reply_markup=markup)

# --- CALLBACK ---
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    chat_id = call.message.chat.id

    if call.data.startswith("show_"):
        key = call.data.split("_")[1]
        item = PRODUCTS[key]

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"➕ Купити {item['price']} грн", callback_data=f"buy_{key}"))
        markup.add(types.InlineKeyboardButton("⬅ Назад", callback_data="back"))

        bot.send_message(chat_id, f"{item['name']}\n💰 {item['price']} грн", reply_markup=markup)
        bot.delete_message(chat_id, call.message.message_id)

    elif call.data.startswith("buy_"):
        key = call.data.split("_")[1]
        user_carts.setdefault(chat_id, {"items": [], "promo": None})
        user_carts[chat_id]["items"].append(key)
        bot.answer_callback_query(call.id, "✅ Додано")
        threading.Thread(target=reminder, args=(chat_id,)).start()

    elif call.data == "clear":
        user_carts[chat_id] = {"items": [], "promo": None}
        bot.edit_message_text("🗑 Очищено", chat_id, call.message.message_id)

    elif call.data == "back":
        bot.delete_message(chat_id, call.message.message_id)
        catalog(call.message)

    elif call.data == "checkout":
        cart_items = user_carts.get(chat_id, {}).get("items", [])
        if "energy" not in cart_items:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("⚡ Додати energy -20%", callback_data="upsell_energy"))
            markup.add(types.InlineKeyboardButton("➡ Продовжити", callback_data="checkout_final"))
            bot.send_message(chat_id, "🔥 Додай energy зі знижкою!", reply_markup=markup)
            return
        send_invoice(chat_id)

    elif call.data == "upsell_energy":
        user_carts[chat_id]["items"].append("energy")
        bot.send_message(chat_id, "⚡ Додано зі знижкою")
        send_invoice(chat_id)

    elif call.data == "checkout_final":
        send_invoice(chat_id)

# --- INVOICE ---
def send_invoice(chat_id):
    items = user_carts[chat_id]["items"]

    prices = []
    total = 0

    for key in set(items):
        qty = items.count(key)
        item = PRODUCTS[key]
        price = item["price"] * qty
        prices.append(types.LabeledPrice(f"{item['name']} x{qty}", price * 100))
        total += price

    discount = 0
    if user_carts[chat_id]["promo"]:
        discount = int(total * PROMO_CODES[user_carts[chat_id]["promo"]])
        total -= discount
        prices.append(types.LabeledPrice("Знижка", -discount * 100))

    bot.send_invoice(
        chat_id,
        title="🛍 Happy Caps",
        description=f"До оплати: {total} грн",
        invoice_payload="order",
        provider_token=PAYMENT_TOKEN,
        currency="UAH",
        prices=prices,
        start_parameter="pay",
        need_phone_number=True,
        need_shipping_address=True,
        is_flexible=True
    )

# --- ДОСТАВКА ---
@bot.shipping_query_handler(func=lambda q: True)
def shipping(q):
    options = [types.ShippingOption("nova", "Нова Пошта").add_price(types.LabeledPrice("Доставка", 8000))]
    bot.answer_shipping_query(q.id, ok=True, shipping_options=options)

# --- PRE CHECKOUT ---
@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(q):
    bot.answer_pre_checkout_query(q.id, ok=True)

# --- УСПІШНА ОПЛАТА ---
@bot.message_handler(content_types=['successful_payment'])
def success(message):
    chat_id = message.chat.id
    total = message.successful_payment.total_amount / 100

    bot.send_message(chat_id, f"✅ Оплачено {total} грн")

    orders.append({
        "user": chat_id,
        "amount": total,
        "items": user_carts[chat_id]["items"]
    })
    save_orders()

    bot.send_message(ADMIN_ID, f"💰 Нова оплата {total} грн")

    user_carts[chat_id] = {"items": [], "promo": None}

# --- ПРОМОКОД ---
@bot.message_handler(func=lambda m: m.text == "🎁 Промокод")
def promo(message):
    msg = bot.send_message(message.chat.id, "Введи код:")
    bot.register_next_step_handler(msg, apply_promo)

def apply_promo(message):
    code = message.text.strip()
    if code in PROMO_CODES:
        user_carts.setdefault(message.chat.id, {"items": [], "promo": None})
        user_carts[message.chat.id]["promo"] = code
        bot.send_message(message.chat.id, "✅ Промокод застосовано")
    else:
        bot.send_message(message.chat.id, "❌ Невірний код")

# --- РОЗСИЛКА ---
@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if message.chat.id != ADMIN_ID:
        return
    text = message.text.replace("/broadcast ", "")
    for u in users:
        try:
            bot.send_message(u, text)
        except:
            pass

# --- НАГАДУВАННЯ ---
def reminder(chat_id):
    time.sleep(600)
    if chat_id in user_carts and user_carts[chat_id]["items"]:
        bot.send_message(chat_id, "⏳ Ти забув оплатити замовлення")

# --- AI + КНОПКА ЗАМОВЛЕННЯ ---
@bot.message_handler(func=lambda m: True)
def ai(message):
    if message.text in ["📂 Каталог", "🛒 Кошик", "🎁 Промокод", "📞 Консультант"]:
        return
    try:
        catalog = ", ".join([f"{p['name']} ({p['price']} грн)" for p in PRODUCTS.values()])
        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": f"Ти продавець. Товари: {catalog}. Визначай товар і кількість у запиті користувача та пропонуй Inline-кнопку для покупки."},
                {"role": "user", "content": message.text}
            ]
        )
        ai_text = response.choices[0].message.content

        # 🔹 Визначаємо товари та кількість
        markup = types.InlineKeyboardMarkup()
        found = False
        for key, item in PRODUCTS.items():
            # Знаходимо кількість через regex (1, одну, дві, 2 тощо)
            match = re.search(rf"(\d+|одну|один|дві|два)?\s*{re.escape(item['name'].split()[0].lower())}", message.text.lower())
            if match:
                qty_text = match.group(1)
                qty = 1
                if qty_text:
                    if qty_text.isdigit():
                        qty = int(qty_text)
                    elif qty_text in ["одну", "один"]:
                        qty = 1
                    elif qty_text in ["дві", "два"]:
                        qty = 2
                # Додаємо кнопку
                markup.add(types.InlineKeyboardButton(
                    f"➕ Додати {item['name']} x{qty} ({item['price']} грн)",
                    callback_data=f"buy_{key}"  # Додаємо завжди 1 одиницю, а qty можна врахувати у AI логіці
                ))
                found = True
        if found:
            bot.send_message(message.chat.id, ai_text, reply_markup=markup)
        else:
            bot.reply_to(message, ai_text)
    except Exception as e:
        print(e)
        bot.reply_to(message, "⚠️ Помилка ШІ")

# --- START ---
if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(1)
    bot.infinity_polling(skip_pending=True)
