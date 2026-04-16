import telebot
from telebot import types
import os
import re
from openai import OpenAI

# --- НАЛАШТУВАННЯ ---
TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEB_APP_URL = "https://mamutpetr.github.io/Pinkcanna/"

bot = telebot.TeleBot(TOKEN)
client = OpenAI(api_key=OPENAI_API_KEY)

# --- ТОВАРИ ТА ІНФОРМАЦІЯ ---
PRODUCTS = {
    "kanna10x": {
        "name": "Канна 10х (Екстракт) 🌿", 
        "price": 2500, 
        "image": "kanna10x.jpg",
        "short": "Потужний екстракт для настрою та ейфорії.",
        "info": "🌿 **Про Канну (Sceletium tortuosum):**\nЦя рослина з Південної Африки діє як природний селективний інгібітор зворотного захоплення серотоніну (SRI). \n\n🔹 **Ефект:** 10-кратний екстракт забезпечує швидкий підйом настрою, зняття соціальної тривоги та м'яку стимуляцію, яка переходить у релаксацію.\n🔹 **Для кого:** Ідеально підходить для вечірок або творчої роботи."
    },
    "crystal": {
        "name": "Канна Crystal (Чистий ізолят) 💎", 
        "price": 3000, 
        "image": "kannacrystal.jpg",
        "short": "Найчистіші алкалоїди для фокусу.",
        "info": "💎 **Про Kanna Crystal:**\nЦе ізольована форма алкалоїдів (переважно мезембрину) з чистотою понад 98%.\n\n🔹 **Ефект:** Дає максимально 'чистий' ефект без трав'яного присмаку та важкості. Покращує когнітивні здібності, дарує ясний розум та емоційну стабільність.\n🔹 **Застосування:** Найкращий вибір для тих, хто шукає точний та передбачуваний результат."
    },
    "strong": {
        "name": "Канна Strong (Максимальна сила) 🔥", 
        "price": 3000, 
        "image": "kannastrong.jpg",
        "short": "Екстремальна концентрація для досвідчених.",
        "info": "🔥 **Про Kanna Strong:**\nСпеціально розроблена суміш з підвищеним вмістом активних речовин.\n\n🔹 **Ефект:** Дуже швидка дія (вже за 5-10 хвилин). Сильна хвиля спокою, що супроводжується відчуттям впевненості та фізичного розслаблення.\n🔹 **Увага:** Рекомендується тільки тим, хто вже знайомий з дією Канни."
    },
    "sleep": {
        "name": "Happy caps sleep (Інгалятор) 💤", 
        "price": 2000, 
        "image": "sleep.jpg",
        "short": "Миттєве засинання та глибокий сон.",
        "info": "💤 **Про CBD для сну:**\nІнгаляційна форма дозволяє CBD потрапити в кров миттєво, минаючи травну систему.\n\n🔹 **Як діє:** Взаємодіє з рецепторами CB1 в мозку, заспокоюючи центральну нервову систему. Знижує рівень кортизолу (гормону стресу).\n🔹 **Результат:** Ви засинаєте швидше, а фаза глибокого сну стає довшою, що забезпечує повне відновлення."
    },
    "gaba": {
        "name": "Габа #9 🧠", 
        "price": 400, 
        "image": "gaba9.jpg",
        "short": "Природне гальмо для стресу.",
        "info": "🧠 **Про ГАМК (GABA):**\nГамма-аміномасляна кислота — це головний гальмівний нейромедіатор мозку.\n\n🔹 **Ефект:** Габа зупиняє 'перезбудження' нейронів. Це допомагає при панічних атаках, підвищеній тривожності та дратівливості.\n🔹 **Перевага:** Не викликає звикання та допомагає мозку відпочити від інформаційного перевантаження."
    },
    "energy": {
        "name": "Happy caps energy ⚡", 
        "price": 2000, 
        "image": "energy.jpg",
        "short": "Чиста енергія без тремору.",
        "info": "⚡ **Про енергетичну формулу:**\nПоєднання CBD та природних адаптогенів.\n\n🔹 **Дія:** На відміну від кави, цей продукт не виснажує наднирники. Він дає 'рівну' енергію без подальшого падіння сил.\n🔹 **Ефект:** Покращення концентрації, мотивації та фізичної бадьорості протягом 4-6 годин."
    },
    "cream": {
        "name": "СБД Крем 🧴", 
        "price": 1600, 
        "image": "cream.jpg",
        "short": "Допомога суглобам та м'язам.",
        "info": "🧴 **Про CBD крем:**\nТрансдермальний метод доставки каннабідіолу безпосередньо в тканини.\n\n🔹 **Дія:** Має потужні протизапальні властивості. Допомагає при болях у м'язах після спорту, артриті та шкірних подразненнях.\n🔹 **Особливість:** Не потрапляє в загальний кровотік, працюючи локально там, де це потрібно."
    },
    "vape": {
        "name": "Вейп 💨", 
        "price": 3000, 
        "image": "blackvape.jpg",
        "short": "Експрес-релакс у кишені.",
        "info": "💨 **Про CBD Vape:**\nНайчистіший дистилят CBD з натуральними терпенами.\n\n🔹 **Перевага:** Біодоступність при вдиханні становить до 60% (порівняно з 15% при прийомі всередину). Ефект відчувається за 1-2 хвилини.\n🔹 **Безпека:** Не містить нікотину, вітаміну Е або шкідливих розчинників."
    },
    "jelly": {
        "name": "СБД Желе 🍬", 
        "price": 1900, 
        "image": "Cbdgele.jpg",
        "short": "Смачний спосіб бути в балансі.",
        "info": "🍬 **Про CBD Jelly:**\nХарчовий продукт з каннабідіолом.\n\n🔹 **Як працює:** CBD вивільняється поступово через печінку, що забезпечує тривалий ефект (до 8 годин).\n🔹 **Для кого:** Найкращий варіант для підтримки стабільного настрою протягом всього робочого дня."
    }
}

user_carts = {}
user_tapped_discounts = {}

# --- ГОЛОВНЕ МЕНЮ ---
def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True)
    m.add("📂 Каталог", "🛒 Кошик")
    m.add(types.KeyboardButton("🍀 Натапати знижку", web_app=types.WebAppInfo(url=WEB_APP_URL)))
    m.add("📞 Консультант", "📰 Новини")
    return m

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🌿 Вітаємо у Pink Canna! Твоя територія якісного CBD та екстрактів.", reply_markup=main_menu())

# --- КАТАЛОГ ---
@bot.message_handler(func=lambda m: m.text == "📂 Каталог")
def catalog(message):
    for key, item in PRODUCTS.items():
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn_buy = types.InlineKeyboardButton(f"🛒 Купити за {item['price']} грн", callback_data=f"buy_{key}")
        btn_info = types.InlineKeyboardButton("🔍 Дізнатись більше", callback_data=f"info_{key}")
        markup.add(btn_buy, btn_info)
        
        caption = f"🏷 **{item['name']}**\n\n📝 {item['short']}\n\n💰 **Ціна: {item['price']} грн**"
        
        try:
            if os.path.exists(item['image']):
                with open(item['image'], 'rb') as photo:
                    bot.send_photo(message.chat.id, photo, caption=caption, reply_markup=markup, parse_mode="Markdown")
            else:
                bot.send_message(message.chat.id, caption, reply_markup=markup, parse_mode="Markdown")
        except:
            bot.send_message(message.chat.id, caption, reply_markup=markup, parse_mode="Markdown")

# --- ОБРОБКА КНОПОК ---
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    # Додавання в кошик
    if call.data.startswith("buy_"):
        key = call.data.split("_")[1]
        user_carts.setdefault(call.message.chat.id, []).append(key)
        bot.answer_callback_query(call.id, f"✅ {PRODUCTS[key]['name']} у кошику!")

    # Детальна інформація
    elif call.data.startswith("info_"):
        key = call.data.split("_")[1]
        text = PRODUCTS[key]['info']
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown")
        bot.answer_callback_query(call.id)

    # Очищення кошика
    elif call.data == "clear_cart":
        user_carts[call.message.chat.id] = []
        bot.edit_message_text("🗑 Кошик порожній", call.message.chat.id, call.message.message_id)

    # Оформлення
    elif call.data == "checkout":
        send_invoice(call.message.chat.id)

# --- КОШИК, ОПЛАТА ТА НОВИНИ (ЗАЛИШАЮТЬСЯ БЕЗ ЗМІН) ---
@bot.message_handler(func=lambda m: m.text == "🛒 Кошик")
def show_cart(message):
    chat_id = message.chat.id
    items = user_carts.get(chat_id, [])
    if not items:
        bot.send_message(chat_id, "🛒 Кошик порожній.")
        return
    total = sum(PRODUCTS[k]['price'] for k in items)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Оформити", callback_data="checkout"))
    markup.add(types.InlineKeyboardButton("🗑 Очистити", callback_data="clear_cart"))
    summary = "\n".join([f"• {PRODUCTS[k]['name']} x{items.count(k)}" for k in set(items)])
    bot.send_message(chat_id, f"**Твій кошик:**\n{summary}\n\n💰 **Разом: {total} грн**", reply_markup=markup, parse_mode="Markdown")

def send_invoice(chat_id):
    items = user_carts.get(chat_id, [])
    prices = [types.LabeledPrice(f"{PRODUCTS[k]['name']} x{items.count(k)}", PRODUCTS[k]['price'] * items.count(k) * 100) for k in set(items)]
    bot.send_invoice(chat_id, "Pink Canna", "Оплата замовлення", "payload", PAYMENT_TOKEN, "UAH", prices, need_phone_number=True, need_shipping_address=True)

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def success(message):
    bot.send_message(message.chat.id, "✅ Дякуємо! Замовлення прийнято.")
    user_carts[message.chat.id] = []

@bot.message_handler(func=lambda m: m.text == "📰 Новини")
def news_section(message):
    text = "🌿 **Легальність:** Згідно з Постановою КМУ №324, CBD ізолят не є наркотиком.\n\n🔥 **Новинка:** Наші екстракти Канни тепер доступні у трьох концентраціях!"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def ai_consultant(message):
    if message.text in ["📂 Каталог", "🛒 Кошик", "📞 Консультант", "🍀 Натапати знижку", "📰 Новини"]: return
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "Ти експерт Pink Canna. Відповідай ввічливо та професійно."}, {"role": "user", "content": message.text}]
        )
        bot.send_message(message.chat.id, response.choices[0].message.content)
    except: bot.send_message(message.chat.id, "⚠️ Консультант відпочиває.")

if __name__ == "__main__":
    bot.infinity_polling()

