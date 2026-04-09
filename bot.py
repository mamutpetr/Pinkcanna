import telebot
from telebot import types
import os
import json
import re
from openai import OpenAI

# --- КУРС ВАЛЮТ ---
COIN_RATE = 10000  # 1,000,000 коїнів = 100 грн (отже 10,000 коїнів = 1 грн)

# --- ENV ---
TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")
WEB_APP_URL = "https://mamutpet.github.io/Pinkcanna/" 

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

PROMO_CODES = {"SALE10": 0.1}

user_carts = {}
user_tapped_discounts = {} # Зберігаємо знижку в грн: {chat_id: discount_amount}

# --- МЕНЮ ---
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("📂 Каталог", "🛒 Кошик")
    m.add(types.KeyboardButton("🍀 Натапати знижку", web_app=types.WebAppInfo(url=WEB_APP_URL)))
    m.add("🎁 Промокод", "📞 Консультант")
    return m

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🔥 Вітаємо! Тапай коноплю та купуй дешевше!", reply_markup=main_menu())

# --- ОБРОБКА ДАНИХ З ТАПАЛКИ ---
@bot.message_handler(content_types=['web_app_data'])
def handle_app_data(message):
    coins = int(message.web_app_data.data)
    discount_uah = round(coins / COIN_RATE, 2)
    
    user_tapped_discounts[message.chat.id] = discount_uah
    bot.send_message(message.chat.id, f"✅ Отримано! {coins} коїнів = **{discount_uah} грн** знижки.\nМи застосуємо її до твого наступного замовлення!")

# --- КАТАЛОГ ТА КОШИК ---
@bot.message_handler(func=lambda m: m.text == "📂 Каталог")
def catalog(message):
    markup = types.InlineKeyboardMarkup()
    for key, item in PRODUCTS.items():
        markup.add(types.InlineKeyboardButton(item["name"], callback_data=f"show_{key}"))
    bot.send_message(message.chat.id, "📦 Обери товар:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🛒 Кошик")
def cart(message):
    chat_id = message.chat.id
    if chat_id not in user_carts or not user_carts[chat_id]["items"]:
        bot.send_message(chat_id, "🛒 Кошик порожній")
        return

    items = user_carts[chat_id]["items"]
    text = "\n".join([f"• {PRODUCTS[k]['name']} - {PRODUCTS[k]['price']} грн" for k in items])
    total = sum(PRODUCTS[k]['price'] for k in items)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Оплатити", callback_data="checkout"))
    markup.add(types.InlineKeyboardButton("🗑 Очистити", callback_data="clear"))
    
    bot.send_message(chat_id, f"Твоє замовлення:\n{text}\n\n💰 Разом: {total} грн", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    chat_id = call.message.chat.id
    if call.data.startswith("show_"):
        key = call.data.split("_")[1]
        item = PRODUCTS[key]
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"➕ Купити за {item['price']} грн", callback_data=f"buy_{key}"))
        bot.send_message(chat_id, f"**{item['name']}**\nКращий вибір!", reply_markup=markup)
    
    elif call.data.startswith("buy_"):
        key = call.data.split("_")[1]
        user_carts.setdefault(chat_id, {"items": [], "promo": None})
        user_carts[chat_id]["items"].append(key)
        bot.answer_callback_query(call.id, "✅ Додано")

    elif call.data == "checkout":
        send_invoice(chat_id)

# --- ОПЛАТА З УРАХУВАННЯМ ТАПАЛКИ ---
def send_invoice(chat_id):
    items = user_carts[chat_id]["items"]
    prices = []
    subtotal = sum(PRODUCTS[k]['price'] for k in items)

    for key in set(items):
        qty = items.count(key)
        prices.append(types.LabeledPrice(f"{PRODUCTS[key]['name']} x{qty}", PRODUCTS[key]['price'] * qty * 100))

    # Знижка з тапалки
    tapped_discount = user_tapped_discounts.get(chat_id, 0)
    if tapped_discount > 0:
        if tapped_discount >= subtotal: tapped_discount = subtotal - 1
        prices.append(types.LabeledPrice("🍀 Знижка з тапалки", -int(tapped_discount * 100)))

    bot.send_invoice(
        chat_id, title="Pink Canna Shop", description="Оплата замовлення",
        invoice_payload="order", provider_token=PAYMENT_TOKEN,
        currency="UAH", prices=prices, start_parameter="pay",
        need_phone_number=True, need_shipping_address=True, is_flexible=False
    )

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(q):
    bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def success(message):
    bot.send_message(message.chat.id, "✅ Оплачено! Ми вже готуємо відправку.")
    user_carts[message.chat.id] = {"items": [], "promo": None}
    user_tapped_discounts[message.chat.id] = 0 # Обнуляємо знижку після покупки

if __name__ == "__main__":
    bot.infinity_polling()
