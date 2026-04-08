import telebot
from telebot import types

# Твій токен
TOKEN = '8713738567:AAFguIBEPRlUKTfoshUEhHBD9nGGEaCJMPE'
bot = telebot.TeleBot(TOKEN)

# Головне меню з кнопками
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_catalog = types.KeyboardButton("📂 Каталог")
    btn_cart = types.KeyboardButton("🛒 Кошик")
    btn_order = types.KeyboardButton("📦 Мої замовлення")
    btn_news = types.KeyboardButton("📰 Новини")
    btn_settings = types.KeyboardButton("⚙️ Налаштування")
    markup.add(btn_catalog, btn_cart, btn_order, btn_news, btn_settings)
    return markup

# Команда /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id, 
        "Привіт! Я твій бот. Використовуй меню або команди нижче.", 
        reply_markup=main_menu()
    )

# --- ОБРОБКА КОМАНД ---

@bot.message_handler(commands=['news'])
def news_command(message):
    bot.send_message(message.chat.id, "📰 **Останні новини:**\nСьогодні все спокійно, працюємо над оновленнями!")

@bot.message_handler(commands=['cart'])
def cart_command(message):
    bot.send_message(message.chat.id, "🛒 **Ваш кошик:**\nНаразі тут порожньо. Оберіть щось у каталозі.")

@bot.message_handler(commands=['settings'])
def settings_command(message):
    bot.send_message(message.chat.id, "⚙️ **Налаштування:**\nТут можна змінити мову або налаштувати сповіщення.")

@bot.message_handler(commands=['myorder'])
def myorder_command(message):
    bot.send_message(message.chat.id, "📦 **Ваші замовлення:**\nУ вас поки немає активних замовлень.")

@bot.message_handler(commands=['catalog'])
def catalog_command(message):
    bot.send_message(message.chat.id, "📂 **Каталог:**\nСписок товарів завантажується...")

# --- ОБРОБКА ТЕКСТУ З КНОПОК ---

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    if message.text == "📰 Новини":
        news_command(message)
    elif message.text == "🛒 Кошик":
        cart_command(message)
    elif message.text == "⚙️ Налаштування":
        settings_command(message)
    elif message.text == "📦 Мої замовлення":
        myorder_command(message)
    elif message.text == "📂 Каталог":
        catalog_command(message)
    else:
        bot.reply_to(message, "Я не розумію цей текст. Скористайся кнопками або командами.")

# Запуск
if __name__ == "__main__":
    print("Бот працює...")
    bot.infinity_polling()
