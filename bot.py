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

# --- ГОЛОВНЕ МЕНЮ ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📂 Каталог", "🛒 Кошик")
    markup.add("📦 Мої замовлення", "📰 Новини")
    markup.add("📞 Виклик консультанта")
    return markup

# --- КОМАНДИ ТА НАВІГАЦІЯ ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "👋 Вітаємо у Happy Caps! Я твій смарт-помічник на базі GPT-4o-mini. Запитуй що завгодно або обирай товар:", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "📂 Каталог")
def show_catalog(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, item in PRODUCTS.items():
        markup.add(types.InlineKeyboardButton(item["name"], callback_data=f"show_{key}"))
    bot.send_message(message.chat.id, "✨ Оберіть цікаву вам категорію:", reply_markup=markup)

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

@bot.message_handler(func=lambda m: m.text == "📰 Новини")
def show_news(message):
    bot.send_message(message.chat.id, "📰 **Новини:** Ми перейшли на нову інтелектуальну модель ШІ. Тепер консультації стали ще точнішими!")

@bot.message_handler(func=lambda m: m.text == "📦 Мої замовлення")
def show_orders(message):
    bot.send_message(message.chat.id, "📦 Ваша історія замовлень обробляється менеджером. Ми зателефонуємо вам після кожного нового замовлення.")

@bot.message_handler(func=lambda m: m.text == "📞 Виклик консультанта")
def call_consultant(message):
    user = message.from_user
    username = f"@{user.username}" if user.username else "прихований"
    admin_msg = f"🚨 **ВИКЛИК КОНСУЛЬТАНТА!**\n👤 Клієнт: {user.first_name}\n📞 Юзернейм: {username}\n🆔 ID: {user.id}\n\nНапишіть йому: tg://user?id={user.id}"
    bot.send_message(ADMIN_ID, admin_msg)
    bot.send_message(message.chat.id, "🔔 Менеджер отримав ваш запит! Очікуйте повідомлення у приватні чати.")

# --- ОБРОБКА ТОВАРІВ (Inline кнопки) ---
@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    if call.data.startswith("show_"):
        key = call.data.split("_", 1)[1]
        item = PRODUCTS[key]
        photo_path = os.path.join(os.path.dirname(__file__), item["file"])
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"➕ Додати {item['price']} грн", callback_data=f"buy_{key}"))
        markup.add(types.InlineKeyboardButton("🔙 Назад до каталогу", callback_data="back_to_catalog"))
        try:
            with open(photo_path, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption=f"🌟 **{item['name']}**\n\nЦіна: {item['price']} грн", reply_markup=markup)
            bot.delete_message(chat_id, call.message.message_id)
        except:
            bot.send_message(chat_id, f"📦 **{item['name']}**\nЦіна: {item['price']} грн\n(Фото завантажується менеджером...)", reply_markup=markup)

    elif call.data.startswith("buy_"):
        key = call.data.split("_", 1)[1]
        if chat_id not in user_carts: user_carts[chat_id] = []
        user_carts[chat_id].append(key)
        bot.answer_callback_query(call.id, "✅ Додано у кошик!")

    elif call.data == "checkout":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(types.KeyboardButton("📱 Надіслати номер телефону", request_contact=True))
        bot.send_message(chat_id, "Для завершення замовлення, будь ласка, надішліть номер телефону:", reply_markup=markup)

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
        report = f"🛍 **ЗАМОВЛЕННЯ!**\n👤: {message.from_user.first_name}\n📞: {message.contact.phone_number}\n📦:\n{items}\n💰 Разом: {total} грн"
        bot.send_message(ADMIN_ID, report)
        bot.send_message(chat_id, "✅ Дякуємо! Ваше замовлення прийнято. Менеджер зв'яжеться з вами найближчим часом.", reply_markup=main_menu())
        user_carts[chat_id] = []

# --- ШІ КОНСУЛЬТАНТ (GPT-4o-mini) ---
@bot.message_handler(func=lambda m: True)
def chat_with_ai(message):
    nav_buttons = ["📂 Каталог", "🛒 Кошик", "📦 Мої замовлення", "📰 Новини", "📞 Виклик консультанта"]
    if message.text in nav_buttons:
        return

    # Робимо 2 спроби запиту на випадок збою мережі
    for attempt in range(2):
        try:
            ai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
            catalog_info = ", ".join([f"{p['name']} ({p['price']} грн)" for p in PRODUCTS.values()])
            
            response = ai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"Ти професійний консультант магазину Happy Caps. Ми продаємо: {catalog_info}. Відповідай дружньо, коротко, українською мовою. Якщо клієнт запитує про покупку, направляй у 'Каталог'."},
                    {"role": "user", "content": message.text}
                ],
                timeout=20.0
            )
            bot.reply_to(message, response.choices[0].message.content)
            break
        except Exception as e:
            if attempt == 0:
                time.sleep(1)
                continue
            
            error_str = str(e).lower()
            if "insufficient_quota" in error_str:
                bot.reply_to(message, "🤖 Поповніть баланс OpenAI для роботи ШІ.")
            else:
                bot.reply_to(message, "🤖 Виникла помилка з'єднання з ШІ. Спробуйте ще раз за хвилину або покличте консультанта.")
            print(f"DEBUG: {e}")

# --- ЗАПУСК ---
if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(1)
    bot.infinity_polling(skip_pending=True)
