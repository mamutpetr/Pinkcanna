import telebot
from telebot import types
import os

# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")
WEB_APP_URL = "https://mamutpet.github.io/Pinkcanna/" 

bot = telebot.TeleBot(TOKEN)

# ТОВАРИ
PRODUCTS = {
    "sleep": {"name": "Happy caps sleep 💤", "price": 400},
    "gaba": {"name": "Габа #9 🧠", "price": 450},
    "energy": {"name": "Happy caps energy ⚡", "price": 350},
    "cream": {"name": "СБД Крем 🧴", "price": 600},
    "vape": {"name": "Вейп 💨", "price": 850},
    "jelly": {"name": "СБД Желе 🍬", "price": 500}
}

# СЛОВНИКИ ДЛЯ ДАНИХ
user_carts = {}
user_tapped_discounts = {} # ТУТ ЗБЕРІГАЄМО ЗНИЖКИ (chat_id: сума_в_грн)

# --- МЕНЮ ---
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("📂 Каталог", "🛒 Кошик")
    m.add(types.KeyboardButton("🍀 Натапати знижку", web_app=types.WebAppInfo(url=WEB_APP_URL)))
    m.add("📞 Консультант")
    return m

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🌿 Вітаємо у Pink Canna! Натапай собі знижку!", reply_markup=main_menu())

# --- ОБРОБКА ДАНИХ З ТАПАЛКИ ---
@bot.message_handler(content_types=['web_app_data'])
def handle_tap_result(message):
    try:
        coins = int(message.web_app_data.data)
        # 1,000,000 коїнів = 100 грн => ділимо на 10,000
        discount_uah = round(coins / 10000, 2)
        
        # ЗАПИСУЄМО В ПАМ'ЯТЬ БОТА
        user_tapped_discounts[message.chat.id] = discount_uah
        
        bot.send_message(message.chat.id, f"✅ Успішно! Твої {coins} коїнів конвертовано.\n"
                                          f"💰 Знижка **{discount_uah} грн** активована для твого наступного замовлення!")
    except:
        bot.send_message(message.chat.id, "⚠️ Сталася помилка при отриманні коїнів.")

# --- КАТАЛОГ ---
@bot.message_handler(func=lambda m: m.text == "📂 Каталог")
def catalog(message):
    markup = types.InlineKeyboardMarkup()
    for key, item in PRODUCTS.items():
        markup.add(types.InlineKeyboardButton(f"{item['name']} - {item['price']} грн", callback_data=f"buy_{key}"))
    bot.send_message(message.chat.id, "📦 Що бажаєте замовити?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def add_to_cart(call):
    key = call.data.split("_")[1]
    user_carts.setdefault(call.message.chat.id, []).append(key)
    bot.answer_callback_query(call.id, "✅ Додано в кошик")

# --- КОШИК ---
@bot.message_handler(func=lambda m: m.text == "🛒 Кошик")
def show_cart(message):
    chat_id = message.chat.id
    if chat_id not in user_carts or not user_carts[chat_id]:
        bot.send_message(chat_id, "🛒 Кошик порожній. Час щось натапати! 🍀")
        return

    items = user_carts[chat_id]
    total = sum(PRODUCTS[k]['price'] for k in items)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Оформити замовлення", callback_data="checkout"))
    markup.add(types.InlineKeyboardButton("🗑 Очистити", callback_data="clear_cart"))
    
    bot.send_message(chat_id, f"Твій кошик:\n- " + "\n- ".join([PRODUCTS[k]['name'] for k in items]) + f"\n\n💰 Сума: {total} грн", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "clear_cart")
def clear(call):
    user_carts[call.message.chat.id] = []
    bot.edit_message_text("🗑 Кошик порожній", call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "checkout")
def checkout(call):
    send_invoice(call.message.chat.id)

# --- ФІНАЛЬНИЙ РАХУНОК (ІНВОЙС) ---
def send_invoice(chat_id):
    items = user_carts.get(chat_id, [])
    prices = []
    total_price = 0

    for key in set(items):
        count = items.count(key)
        p = PRODUCTS[key]['price']
        total_price += p * count
        prices.append(types.LabeledPrice(f"{PRODUCTS[key]['name']} x{count}", p * count * 100))

    # ДОДАЄМО ЗНИЖКУ З ТАПАЛКИ
    discount = user_tapped_discounts.get(chat_id, 0)
    if discount > 0:
        if discount >= total_price: discount = total_price - 1 # Щоб не було 0 грн
        prices.append(types.LabeledPrice("🍀 Знижка з гри", -int(discount * 100)))

    bot.send_invoice(
        chat_id, title="Pink Canna", description="Оплата замовлення",
        invoice_payload="order", provider_token=PAYMENT_TOKEN,
        currency="UAH", prices=prices, start_parameter="pay",
        need_phone_number=True, need_shipping_address=True
    )

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(q):
    bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def success(message):
    bot.send_message(message.chat.id, "✅ Оплата пройшла успішно! Чекайте на доставку.")
    user_carts[message.chat.id] = []
    user_tapped_discounts[message.chat.id] = 0 # Скидаємо знижку після використання

if __name__ == "__main__":
    bot.infinity_polling()
