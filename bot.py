import telebot
from telebot import types
import time
import os
import openai

# --- НАЛАШТУВАННЯ ---
TOKEN = '8713738567:AAFguIBEPRlUKTfoshUEhHBD9nGGEaCJMPE'
ADMIN_ID = 6887361815
OPENAI_API_KEY = "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"

bot = telebot.TeleBot(TOKEN)
client = openai.OpenAI(api_key=OPENAI_API_KEY)

# --- БАЗА ТОВАРІВ ---
PRODUCTS = {
    "sleep": {"name": "Happy capps sleep 💤", "price": 400, "file": "sleep.jpg"},
    "gaba": {"name": "Габа #9 🧠", "price": 450, "file": "gaba9.jpg"},
    "energy": {"name": "Happy caps energy ⚡", "price": 350, "file": "energy.jpg"},
    "cream": {"name": "СБД Крем 🧴", "price": 600, "file": "cream.jpg"},
    "vape": {"name": "Вейп 💨", "price": 850, "file": "blackvape.jpg"},
    "jelly": {"name": "СБД Желе 🍬", "price": 500, "file": "Cbdgele.jpg"}
}

user_carts = {}

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📂 Каталог", "🛒 Кошик")
    markup.add("📦 Мої замовлення", "📰 Новини")
    markup.add("📞 Виклик консультанта")
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Привіт! Я твій смарт-помічник. Можеш запитати мене про наші товари або обрати щось у каталозі.", reply_markup=main_menu())

# --- КАТАЛОГ ТА КОШИК (Без змін) ---
@bot.message_handler(func=lambda m: m.text == "📂 Каталог")
def show_catalog(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, item in PRODUCTS.items():
        markup.add(types.InlineKeyboardButton(item["name"], callback_data=f"show_{key}"))
    bot.send_message(message.chat.id, "✨ Оберіть товар:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🛒 Кошик")
def show_cart(message):
    chat_id = message.chat.id
    if chat_id not in user_carts or not user_carts[chat_id]:
        bot.send_message(chat_id, "🛒 Ваш кошик порожній.")
    else:
        items = "\n".join([f"• {PRODUCTS[k]['name']} - {PRODUCTS[k]['price']} грн" for k in user_carts[chat_id]])
        total = sum([PRODUCTS[k]['price'] for k in user_carts[chat_id]])
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🚀 Оформити замовлення", callback_data="checkout"))
        markup.add(types.InlineKeyboardButton("🗑 Очистити кошик", callback_data="clear_cart"))
        bot.send_message(chat_id, f"🛍 **Ваш кошик:**\n\n{items}\n\n💰 Разом: {total} грн", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📞 Виклик консультанта")
def call_consultant(message):
    user = message.from_user
    username = f"@{user.username}" if user.username else "без юзернейму"
    admin_msg = f"🚨 **ВИКЛИК КОНСУЛЬТАНТА!**\n\n👤 Клієнт: {user.first_name} ({username})\n🆔 ID: {user.id}\n\nНапиши йому: tg://user?id={user.id}"
    bot.send_message(ADMIN_ID, admin_msg)
    bot.send_message(message.chat.id, "🔔 Сигнал надіслано! Менеджер скоро відповість вам у приватні повідомлення.")

# --- ОБРОБКА ІНЛАЙН-КНОПОК (SHOW, BUY, CHECKOUT) ---
@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    if call.data.startswith("show_"):
        key = call.data.split("_", 1)[1]
        item = PRODUCTS[key]
        photo_path = os.path.join(os.path.dirname(__file__), item["file"])
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"➕ Додати {item['price']} грн", callback_data=f"buy_{key}"))
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_catalog"))
        try:
            with open(photo_path, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption=f"🌟 **{item['name']}**\n\nЦіна: {item['price']} грн", reply_markup=markup)
            bot.delete_message(chat_id, call.message.message_id)
        except:
            bot.send_message(chat_id, f"📦 **{item['name']}**\nЦіна: {item['price']} грн", reply_markup=markup)

    elif call.data.startswith("buy_"):
        key = call.data.split("_", 1)[1]
        if chat_id not in user_carts: user_carts[chat_id] = []
        user_carts[chat_id].append(key)
        bot.answer_callback_query(call.id, "✅ Додано в кошик!")

    elif call.data == "checkout":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(types.KeyboardButton("📱 Надіслати номер телефону", request_contact=True))
        bot.send_message(chat_id, "Натисніть кнопку нижче, щоб ми зв'язалися з вами:", reply_markup=markup)

    elif call.data == "back_to_catalog":
        bot.delete_message(chat_id, call.message.message_id)
        show_catalog(call.message)

    elif call.data == "clear_cart":
        user_carts[chat_id] = []
        bot.edit_message_text("🛒 Кошик очищено.", chat_id, call.message.message_id)

# --- ПРИЙОМ КОНТАКТУ ---
@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    chat_id = message.chat.id
    if chat_id in user_carts and user_carts[chat_id]:
        items = "\n".join([PRODUCTS[k]['name'] for k in user_carts[chat_id]])
        total = sum([PRODUCTS[k]['price'] for k in user_carts[chat_id]])
        report = f"🔔 **ЗАМОВЛЕННЯ!**\n👤: {message.from_user.first_name}\n📞: {message.contact.phone_number}\n📦:\n{items}\n💰: {total} грн"
        bot.send_message(ADMIN_ID, report)
        bot.send_message(chat_id, "✅ Дякуємо! Замовлення прийнято. Менеджер зв'яжеться з вами.", reply_markup=main_menu())
        user_carts[chat_id] = []

# --- ІНТЕГРАЦІЯ ШІ (OPENAI) ---
@bot.message_handler(func=lambda m: True)
def chat_with_ai(message):
    # Ігноруємо кнопки меню
    if message.text in ["📂 Каталог", "🛒 Кошик", "📦 Мої замовлення", "📰 Новини", "📞 Виклик консультанта"]:
        return

    try:
        # Інструкція для ШІ (System Prompt), щоб він знав, хто він
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ти помічник магазину Happy Caps. Продаєш СБД товари, вейпи, габу. Будь ввічливим, відповідай коротко. Якщо не знаєш відповіді, радь покликати консультанта."},
                {"role": "user", "content": message.text}
            ]
        )
        answer = response.choices[0].message.content
        bot.reply_to(message, answer)
    except Exception as e:
        print(f"OpenAI Error: {e}")
        bot.reply_to(message, "🤖 Вибачте, я трохи замислився. Спробуйте ще раз або зверніться до консультанта.")

if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(1)
    bot.infinity_polling(skip_pending=True)
