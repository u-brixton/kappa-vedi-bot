import telebot
import os
from utils.database import DBConnector, DBLogger, GroupManager

TOKEN = os.environ['TOKEN']
bot = telebot.TeleBot(TOKEN)

connector = DBConnector(os.environ['DATABASE_URL'])
dblogger = DBLogger(connector)
group_manager = GroupManager(connector)

HELP_MSG = """Я бот Каппа Веди, буду тебе рассказывать о предстоящих мероприятиях Клуба и держать в курсе прочих новостей.
Список команд:
/format - пока не готово
/timeplace - пока не готово 
/feedback - пока не готово
/feedbackde - пока не готово
/return - пока не готово
/club - пока не готово
/team - пока не готово
"""

def authorized_only(handler_function):
    def wrapper(message):
        if message.chat.username in group_manager.users:
            handler_function(message)
        else:
            bot.reply_to(message, "Привет! Я чатбот Каппа Веди. Я не разговариваю с незнакомцами - попроси админов клуба добавить твой аккаунт в список.")
    return wrapper
    
def admins_only(handler_function):
    def wrapper(message):
        if message.chat.username in group_manager.users:
            handler_function(message)
        else:
            bot.reply_to(message, "Привет! Я чатбот Каппа Веди. Вы просите меня совершить админское действие, но вы делаете это без админских прав.")
    return wrapper

@bot.message_handler(commands=['start', 'help'])
@authorized_only
def send_welcome(message):
	bot.reply_to(message, HELP_MSG)

@bot.message_handler(func=lambda message: True)
@authorized_only
def echo_all(message):
    response = "Если вы есть – будьте первыми!"
    dblogger.log_message(message, response)
    bot.reply_to(message, response)

bot.polling()
