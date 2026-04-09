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
# Вставте посилання на ваш хостинг, де лежить index.html та картинки
WEB_APP_URL = "https://your-domain.com/index.html" 

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

# --- МЕНЮ (Оновлено) ---
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("📂 Каталог", "🛒 Кошик")
    # Додаємо кнопку для запуску Mini App (Тапалки)
    m.add(types.KeyboardButton("🍀 Отримати знижку (Тапалка)", web_app=types.WebAppInfo(url=WEB_APP_URL)))
    m.add("🎁 Промокод", "📞 Консультант")
    return m

# --- START ---
@bot.message_handler(commands=['start'])
def start(message):
    users.add(message.chat.id)
    bot.send_message(message.chat.id, "🔥 Вітаємо у Happy Caps! Тапай коноплю та отримуй бонуси!", reply_markup=main_menu())

# --- ОБРОБКА ДАНИХ З MINI APP ---
@bot.message_handler(content_types=['web_app_data'])
def web_app_data_handler(message):
    # Якщо ви захочете передавати рахунок з JS (через Telegram.WebApp.sendData)
    data = message.web_app_data.data
    bot.send_message(message.chat.id, f"📈 Твій результат у грі: {data}! Ми нарахуємо тобі бонуси автоматично.")

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

    if chat_id not in user_carts or not user_carts[chat_id]["items"]:
        bot.send_message(chat_id, "🛒 Кошик порожній. Може, час щось натапати? 😉")
        return

    items_list = user_carts[chat_id]["items"]
    items_text = "\n".join([f"• {PRODUCTS[k]['name']} — {PRODUCTS[k]['price']} грн x {items_list.count(k)}" 
                           for k in set(items_list)])
    total = sum(PRODUCTS[k]['price'] for k in items_list)

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Оплатити", callback_data="checkout"))
    markup.add(types.InlineKeyboardButton("🗑 Очистити", callback_data="clear"))

    bot.send_message(chat_id, f"Твоє замовлення:\n\n{items_text}\n\n💰 Разом: {total} грн", reply_markup=markup)

# --- CALLBACK ---
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    chat_id = call.message.chat.id

    if call.data.startswith("show_"):
        key = call.data.split("_")[1]
        item = PRODUCTS[key]
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"➕ Додати в кошик", callback_data=f"buy_{key}"))
        markup.add(types.InlineKeyboardButton("⬅ Назад", callback_data="back"))
        bot.send_message(chat_id, f"{item['name']}\n💰 Ціна: {item['price']} грн", reply_markup=markup)

    elif call.data.startswith("buy_"):
        key = call.data.split("_")[1]
        user_carts.setdefault(chat_id, {"items": [], "promo": None})
        user_carts[chat_id]["items"].append(key)
        bot.answer_callback_query(call.id, "✅ Додано в кошик")

    elif call.data == "clear":
        user_carts[chat_id] = {"items": [], "promo": None}
        bot.edit_message_text("🗑 Кошик очищено", chat_id, call.message.message_id)

    elif call.data == "back":
        bot.delete_message(chat_id, call.message.message_id)
        catalog(call.message)

    elif call.data == "checkout":
        send_invoice(chat_id)

# --- INVOICE ---
def send_invoice(chat_id):
    items = user_carts[chat_id]["items"]
    prices = []
    total = 0

    for key in set(items):
        qty = items.count(key)
        item = PRODUCTS[key]
        prices.append(types.LabeledPrice(f"{item['name']} x{qty}", item["price"] * qty * 100))
        total += item["price"] * qty

    if user_carts[chat_id]["promo"]:
        discount = int(total * PROMO_CODES[user_carts[chat_id]["promo"]])
        prices.append(types.LabeledPrice("Знижка", -discount * 100))

    bot.send_invoice(
        chat_id,
        title="🛍 Happy Caps Order",
        description="Оплата замовлення",
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
    bot.send_message(message.chat.id, "✅ Дякуємо за покупку! Ваше замовлення прийнято.")
    user_carts[message.chat.id] = {"items": [], "promo": None}

# --- ПРОМОКОД ---
@bot.message_handler(func=lambda m: m.text == "🎁 Промокод")
def promo(message):
    msg = bot.send_message(message.chat.id, "Введіть ваш секретний код:")
    bot.register_next_step_handler(msg, apply_promo)

def apply_promo(message):
    code = message.text.strip().upper()
    if code in PROMO_CODES:
        user_carts.setdefault(message.chat.id, {"items": [], "promo": None})
        user_carts[message.chat.id]["promo"] = code
        bot.send_message(message.chat.id, f"✅ Промокод {code} активовано!")
    else:
        bot.send_message(message.chat.id, "❌ Такого коду не існує.")

# --- AI LOGIC (Спрощено для стабільності) ---
@bot.message_handler(func=lambda m: True)
def ai_handler(message):
    if message.text in ["📂 Каталог", "🛒 Кошик", "🎁 Промокод", "📞 Консультант"]:
        return
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o", # Рекомендую gpt-4o або gpt-3.5-turbo
            messages=[
                {"role": "system", "content": "Ти помічник магазину Happy Caps. Допомагай клієнтам обрати СБД товари."},
                {"role": "user", "content": message.text}
            ]
        )
        bot.reply_to(message, response.choices[0].message.content)
    except Exception as e:
        bot.reply_to(message, "Спробуйте пізніше або зверніться до консультанта.")

if __name__ == "__main__":
    print("Бот запущений...")
    bot.infinity_polling()
