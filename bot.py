import telebot
from telebot import types
import time

# Твій токен
TOKEN = '8713738567:AAFguIBEPRlUKTfoshUEhHBD9nGGEaCJMPE'
bot = telebot.TeleBot(TOKEN)

# Функція для створення головного меню (кнопки)
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_catalog = types.KeyboardButton("📂 Каталог")
    btn_cart = types.KeyboardButton("🛒 Кошик")
    btn_order = types.KeyboardButton("📦 Мої замовлення")
    btn_news = types.KeyboardButton("📰 Новини")
    btn_settings = types.KeyboardButton("⚙️ Налаштування")
    markup.add(btn_catalog, btn_cart, btn_order, btn_news, btn_settings)
    return markup

# --- ОБРОБНИКИ КОМАНД ---

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id, 
        "🚀 Бот успішно запущений на сервері!\nВиберіть потрібний розділ:", 
        reply_markup=main_menu()
    )

@bot.message_handler(commands=['news'])
def news_command(message):
    bot.send_message(message.chat.id, "📰 **Останні новини:**\nБот тепер працює на Render 24/7!")

@bot.message_handler(commands=['cart'])
def cart_command(message):
    bot.send_message(message.chat.id, "🛒 **Ваш кошик:**\nНаразі порожньо.")

@bot.message_handler(commands=['settings'])
def settings_command(message):
    bot.send_message(message.chat.id, "⚙️ **Налаштування:**\nТут будуть ваші опції.")

@bot.message_handler(commands=['myorder'])
def myorder_command(message):
    bot.send_message(message.chat.id, "📦 **Ваші замовлення:**\nІсторія замовлень порожня.")

@bot.message_handler(commands=['catalog'])
def catalog_command(message):
    bot.send_message(message.chat.id, "📂 **Каталог:**\nТовари в розробці...")

# --- ОБРОБКА ТЕКСТУ З КНОПОК ---

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    # Логіка для кнопок, щоб вони дублювали команди
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
        bot.reply_to(message, "Скористайтеся меню або командами /help")

# --- ЗАПУСК І ВИРАІШЕННЯ КОНФЛІКТУ 409 ---

if __name__ == "__main__":
    print("--- ЗАПУСК БОТА ---")
    
    # Видаляємо вебхук, якщо він залишився від попередніх сесій
    bot.remove_webhook()
    time.sleep(1) # Невелика пауза для синхронізації з серверами Telegram
    
    print("Бот онлайн. Очікування повідомлень...")
    
    # skip_pending=True дозволяє ігнорувати повідомлення, 
    # які прийшли, поки бот був офлайн (щоб не було спаму при запуску)
    bot.infinity_polling(skip_pending=True)
