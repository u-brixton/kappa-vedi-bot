import telebot
import os
from utils.heroku_logging import DBLogger

TOKEN = os.environ['TOKEN']
bot = telebot.TeleBot(TOKEN)
dblogger = DBLogger(os.environ['DATABASE_URL'])


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
	bot.reply_to(message, "Привет! Я чатбот Каппа Веди. Я пока умею очень мало, но буду учиться. ")

@bot.message_handler(func=lambda message: True)
def echo_all(message):
    response = "Если вы есть – будьте первыми!"
    dblogger.log_message(message, response)
    bot.reply_to(message, response)

bot.polling()
