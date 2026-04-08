import telebot
from telebot import types
import time
import os

TOKEN = '8713738567:AAFguIBEPRlUKTfoshUEhHBD9nGGEaCJMPE'
bot = telebot.TeleBot(TOKEN)

# Твій ID для отримання замовлень
ADMIN_ID = 5605273934 # Переконайся, що тут твій ID

user_carts = {}

# Оновлений список товарів з твоїми назвами
PRODUCTS = {
    "sleep": {"name": "Happy capps sleep 💤", "price": 400, "file": "sleep.jpg"},
    "gaba": {"name": "Габа #9 🧠", "price": 450, "file": "gaba9.jpg"},
    "energy": {"name": "Happy caps energy ⚡", "price": 350, "file": "energy.jpg"},
    "cream": {"name": "СБД Крем 🧴", "price": 600, "file": "cream.jpg"},
    "vape": {"name": "Вейп 💨", "price": 850, "file": "blackvape.jpg"},
    "jelly": {"name": "СБД Желе 🍬", "price": 500, "file": "Cbdgele.jpg"}
}

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📂 Каталог", "🛒 Кошик", "📦 Мої замовлення", "📰 Новини")
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "👋 Вітаємо! Магазин оновлено.", reply_markup=main_menu())

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
        cart_text = "🛍 **Ваш кошик:**\n\n"
        total = 0
        for item_key in user_carts[chat_id]:
            item = PRODUCTS[item_key]
            cart_text += f"• {item['name']} — {item['price']} грн\n"
            total += item['price']
        cart_text += f"\n💰 **Разом: {total} грн**"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🚀 Оформити замовлення", callback_data="checkout"))
        markup.add(types.InlineKeyboardButton("🗑 Очистити", callback_data="clear_cart"))
        bot.send_message(chat_id, cart_text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    data = call.data

    if data.startswith("show_"):
        key = data.split("_", 1)[1]
        item = PRODUCTS[key]
        photo_path = os.path.join(os.path.dirname(__file__), item["file"])
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"➕ Додати за {item['price']} грн", callback_data=f"buy_{key}"))
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_catalog"))
        
        try:
            with open(photo_path, 'rb') as photo:
                bot.send_photo(chat_id, photo, caption=f"🌟 **{item['name']}**\n\nНайкраща якість!\nЦіна: {item['price']} грн", reply_markup=markup)
            bot.delete_message(chat_id, call.message.message_id)
        except:
            bot.send_message(chat_id, f"⚠️ Фото {item['file']} не завантажилось. Товар: {item['name']}", reply_markup=markup)

    elif data.startswith("buy_"):
        key = data.split("_", 1)[1]
        if chat_id not in user_carts: user_carts[chat_id] = []
        user_carts[chat_id].append(key)
        bot.answer_callback_query(call.id, f"✅ Додано: {PRODUCTS[key]['name']}")

    elif data == "checkout":
        items_list = "\n".join([PRODUCTS[k]['name'] for k in user_carts[chat_id]])
        username = call.from_user.username if call.from_user.username else "Без юзернейму"
        order_msg = f"🔔 **ЗАМОВЛЕННЯ!**\n👤 Клієнт: @{username}\n📦 Товари:\n{items_list}"
        bot.send_message(ADMIN_ID, order_msg)
        bot.edit_message_text("🙏 Замовлення надіслано! Менеджер зв'яжеться з вами.", chat_id, call.message.message_id)
        user_carts[chat_id] = []

    elif data == "clear_cart":
        user_carts[chat_id] = []
        bot.edit_message_text("🛒 Кошик очищено.", chat_id, call.message.message_id)

    elif data == "back_to_catalog":
        bot.delete_message(chat_id, call.message.message_id)
        show_catalog(call.message)

if __name__ == "__main__":
    bot.remove_webhook()
    time.sleep(1)
    bot.infinity_polling(skip_pending=True)
