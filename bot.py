import telebot
from telebot import types
import time
import os

# --- НАЛАШТУВАННЯ ---
TOKEN = '8713738567:AAFguIBEPRlUKTfoshUEhHBD9nGGEaCJMPE'
ADMIN_ID = 6887361815  # Твій ID для отримання замовлень
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

# Кошики користувачів (у пам'яті)
user_carts = {}

# --- КЛАВІАТУРИ ---

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📂 Каталог", "🛒 Кошик")
    markup.add("📦 Мої замовлення", "📰 Новини")
    return markup

# --- ОБРОБНИКИ ТЕКСТОВИХ КОМАНД (МЕНЮ) ---

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id, 
        "👋 Вітаємо у нашому магазині!\nВикористовуйте меню нижче для навігації:", 
        reply_markup=main_menu()
    )

@bot.message_handler(func=lambda m: m.text == "📂 Каталог")
def show_catalog(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key, item in PRODUCTS.items():
        markup.add(types.InlineKeyboardButton(item["name"], callback_data=f"show_{key}"))
    bot.send_message(message.chat.id, "✨ Оберіть товар для перегляду:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🛒 Кошик")
def show_cart(message):
    chat_id = message.chat.id
    if chat_id not in user_carts or not user_carts[chat_id]:
        bot.send_message(chat_id, "🛒 Ваш кошик порожній.")
    else:
        cart_text = "🛍 **Ваш кошик:**\n\n"
        total = 0
        for item_key in user_carts[chat_id]:
            item = PRODUCTS[item_key]
            cart_text += f"• {item['name']} — {item['price']} грн\n"
            total += item['price']
        cart_text += f"\n💰 **Разом: {total} грн**"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🚀 Оформити замовлення", callback_data="checkout"))
        markup.add(types.InlineKeyboardButton("🗑 Очистити кошик", callback_data="clear_cart"))
        bot.send_message(chat_id, cart_text, reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📰 Новини")
def show_news(message):
    news_text = (
        "📰 **Останні новини магазину:**\n\n"
        "✅ Ми офіційно запустили нашого Telegram-бота!\n"
        "🚚 Доставка працює у штатному режимі.\n"
        "✨ Всі товари з каталогу є в наявності."
    )
    bot.send_message(message.chat.id, news_text)

@bot.message_handler(func=lambda m: m.text == "📦 Мої замовлення")
def show_orders(message):
    bot.send_message(
        message.chat.id, 
        "📦 **Ваші замовлення:**\n\n"
        "Наразі ваша історія замовлень доступна у менеджера. "
        "Після оформлення замовлення ми зателефонуємо вам для підтвердження!"
    )

# --- ОБРОБКА ІНЛАЙН-КНОПОК ТА КАТАЛОГУ ---

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    
    # Показ товару
    if call.data.startswith("show_"):
        key = call.data.split("_", 1)[1]
        item = PRODUCTS[key]
        photo_path = os.path.join(os.path.dirname(__file__), item["file"])
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"➕ Додати в кошик {item['price']} грн", callback_data=f"buy_{key}"))
        markup.add(types.InlineKeyboardButton("🔙 Назад до каталогу", callback_data="back_to_catalog"))
        
        try:
            with open(photo_path, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption=f"🌟 **{item['name']}**\n\nНайкраща якість!\nЦіна: {item['price']} грн", reply_markup=markup)
            bot.delete_message(chat_id, call.message.message_id)
        except:
            bot.send_message(chat_id, f"📦 **{item['name']}**\nЦіна: {item['price']} грн\n(Фото не знайдено на сервері)", reply_markup=markup)

    # Купівля
    elif call.data.startswith("buy_"):
        key = call.data.split("_", 1)[1]
        if chat_id not in user_carts: user_carts[chat_id] = []
        user_carts[chat_id].append(key)
        bot.answer_callback_query(call.id, f"✅ {PRODUCTS[key]['name']} додано!")

    # Крок оформлення
    elif call.data == "checkout":
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add(types.KeyboardButton("📱 Надіслати номер телефону", request_contact=True))
        bot.send_message(chat_id, "Натисніть кнопку нижче, щоб ми отримали ваш контакт для зв'язку:", reply_markup=markup)

    # Повернення та очищення
    elif call.data == "back_to_catalog":
        bot.delete_message(chat_id, call.message.message_id)
        show_catalog(call.message)

    elif call.data == "clear_cart":
        user_carts[chat_id] = []
        bot.edit_message_text("🛒 Кошик очищено.", chat_id, call.message.message_id)

# --- ОБРОБКА КОНТАКТУ ТА ВІДПРАВКА АДМІНУ ---

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    chat_id = message.chat.id
    if chat_id in user_carts and user_carts[chat_id]:
        phone = message.contact.phone_number
        username = f"@{message.from_user.username}" if message.from_user.username else "Прихований"
        items = "\n".join([PRODUCTS[k]['name'] for k in user_carts[chat_id]])
        total = sum([PRODUCTS[k]['price'] for k in user_carts[chat_id]])

        order_report = (
            f"🔔 **НОВЕ ЗАМОВЛЕННЯ!**\n\n"
            f"👤 Клієнт: {message.from_user.first_name} ({username})\n"
            f"📞 Тел: {phone}\n"
            f"📦 Товари:\n{items}\n"
            f"💰 Сума: {total} грн"
        )
        
        try:
            bot.send_message(ADMIN_ID, order_report)
            bot.send_message(chat_id, "✅ Дякуємо! Ваше замовлення прийнято. Менеджер скоро зв'яжеться з вами.", reply_markup=main_menu())
            user_carts[chat_id] = []
        except Exception as e:
            bot.send_message(chat_id, "⚠️ Помилка оформлення. Зв'яжіться з нами напряму.")
            print(f"Error: {e}")

# --- ЗАПУСК ---
if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(1)
    print("Бот працює...")
    bot.infinity_polling(skip_pending=True)
