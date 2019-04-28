#!/usr/bin/python
# -*- coding: utf-8 -*-
import telebot
import os
from utils.database import DBConnector, DBLogger, GroupManager, EventManager
from workflow import SessionManager
from flask import Flask, request
from utils.telegram_api import surrogate_message
import argparse

TOKEN = os.environ['TOKEN']
bot = telebot.TeleBot(TOKEN)

connector = DBConnector(os.environ['DATABASE_URL'])
dblogger = DBLogger(connector)
group_manager = GroupManager(connector)
event_manager = EventManager(connector)
session_manager = SessionManager(connector, group_manager=group_manager, event_manager=event_manager)

server = Flask(__name__)
TELEBOT_URL = 'telebot_webhook/'
BASE_URL = 'https://kappa-vedi-bot.herokuapp.com/'

HELP_MSG = """
Я бот Каппа Веди, буду тебе рассказывать о предстоящих мероприятиях Клуба и держать в курсе прочих новостей.
Список команд:
/format - пока не готово
/timeplace - пока не готово 
/feedback - пока не готово
/feedbackde - пока не готово
/return - пока не готово
/club - пока не готово
/team - пока не готово
/reset - прервать текущий диалог с ботом (пока не готово)
"""


def authorized_only(handler_function):
    def wrapper(message):
        if message.chat.username in group_manager.users:
            handler_function(message)
        else:
            bot.reply_to(message, "Привет! Я чатбот Каппа Веди. Я не разговариваю с незнакомцами"
                         + " - попроси админов клуба добавить твой аккаунт в список.")
    return wrapper


def admins_only(handler_function):
    def wrapper(message):
        if message.chat.username in group_manager.users:
            handler_function(message)
        else:
            bot.reply_to(message, "Привет! Я чатбот Каппа Веди. Вы просите меня совершить админское действие,"
                         + " но вы делаете это без админских прав.")
    return wrapper


def answer_with_log(message, response, reply=True, **kwargs):
    dblogger.log_message(message, response)
    if reply and message.message_id != 'DUMMY':
        reply_to_message_id = message.message_id
    else:
        reply_to_message_id = None
    bot.send_message(message.chat.id, response, reply_to_message_id=reply_to_message_id, **kwargs)


session_manager.send_function = answer_with_log


@bot.message_handler(commands=['start', 'help'])
@authorized_only
def send_welcome(message):
    answer_with_log(message, HELP_MSG)


@bot.message_handler(func=lambda message: True)
@authorized_only
def echo_all(message):
    response, callback = session_manager.process_message(message)
    response = response or "Если вы есть – будьте первыми!"
    answer_with_log(message, response)
    # callback is the action that must be performed just after the message is sent
    if callback is not None:
        callback()


# bot.polling()

# trying to use the webhook example instead of polling - in this case, the bot will answer even after idling shutdown
# https://github.com/eternnoir/pyTelegramBotAPI/blob/master/examples/webhook_examples/webhook_flask_heroku_echo.py


@server.route('/' + TELEBOT_URL + TOKEN, methods=['POST'])
def get_message():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200


@server.route("/" + TELEBOT_URL)
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=BASE_URL + TELEBOT_URL + TOKEN)
    return "!", 200


@server.route("/wakeup/")
def wakeup():
    # todo: check last visit time
    # todo: perform jobs (e.g. remind about events)
    # todo: update the visit time
    answer_with_log(surrogate_message('71034798', 'cointegrated'), "Я жив и напоминаю о себе!", reply=False)
    return "Маам, ну ещё пять минуточек!", 200


parser = argparse.ArgumentParser(description='Run the bot')
parser.add_argument('--poll', action='store_true')
parser.add_argument('--logs', action='store_true')
if __name__ == "__main__":
    args = parser.parse_args()
    if args.logs:
        for row in dblogger.get_tail(50):
            print(row)
    elif args.poll:
        bot.remove_webhook()
        bot.polling()
    else:
        server.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
        webhook()
