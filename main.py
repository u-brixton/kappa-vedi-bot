#!/usr/bin/python
# -*- coding: utf-8 -*-
import argparse
import os
import sentry_sdk
import telebot

from flask import Flask, request

from config import ADMIN_UID
from response_logic import respond
from scenarios.coffee import daily_random_coffee
from scenarios.events import daily_event_management
from utils.database import Database
from utils.messaging import TelegramSender


ON_HEROKU = os.environ.get('ON_HEROKU')
TOKEN = os.environ['TOKEN']
bot = telebot.TeleBot(TOKEN)

server = Flask(__name__)
TELEBOT_URL = 'telebot_webhook/'
BASE_URL = 'https://kappa-vedi-bot.herokuapp.com/'

MONGO_URL = os.environ.get('MONGODB_URI')
DATABASE = Database(MONGO_URL, admins={'cointegrated', 'stepan_ivanov', 'jonibekortikov', 'dkkharlm', 'helmeton'})

if os.environ.get('SENTRY_DSN'):
    sentry_sdk.init(os.environ.get('SENTRY_DSN'))

SENDER = TelegramSender(bot, admin_uid=ADMIN_UID)


@server.route("/" + TELEBOT_URL)
def web_hook():
    bot.remove_webhook()
    bot.set_webhook(url=BASE_URL + TELEBOT_URL + TOKEN)
    return "!", 200


@server.route("/wakeup/")
def wake_up():
    web_hook()
    # todo: catch exceptions
    daily_random_coffee(database=DATABASE, sender=SENDER)
    daily_event_management(database=DATABASE, sender=SENDER)
    return "Маам, ну ещё пять минуточек!", 200


@bot.message_handler(func=lambda message: True, content_types=['document', 'text', 'photo'])
def process_message(msg):
    respond(message=msg, database=DATABASE, sender=SENDER, bot=bot)


@server.route('/' + TELEBOT_URL + TOKEN, methods=['POST'])
def get_message():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200


parser = argparse.ArgumentParser(description='Run the bot')
parser.add_argument('--poll', action='store_true')


def main():
    args = parser.parse_args()
    if args.poll:
        bot.remove_webhook()
        bot.polling()
    else:
        web_hook()
        server.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))


if __name__ == '__main__':
    main()
