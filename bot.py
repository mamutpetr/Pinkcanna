import telebot
import os

# Рекомендую токен брати з "Environment Variables", але для початку можна вставити сюди
TOKEN = '8713738567:AAFguIBEPRlUKTfoshUEhHBD9nGGEaCJMPE'
bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Бот успішно задеплоєний і готовий до роботи! 🚀")

@bot.message_handler(commands=['catalog'])
def catalog(message):
    bot.send_message(message.chat.id, "📂 Каталог товарів")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    bot.send_message(message.chat.id, "❓ Я працюю 24/7 на сервері!")

# Цей блок потрібен, щоб бот не падав
if __name__ == "__main__":
    print("Бот запускається...")
    bot.infinity_polling()
