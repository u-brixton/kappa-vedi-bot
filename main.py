#!/usr/bin/python
# -*- coding: utf-8 -*-
import argparse
import logging
import os
import random
import sentry_sdk
import telebot

from flask import Flask, request

import config
from response_logic import respond
from scenarios.coffee import daily_random_coffee
from scenarios.events import daily_event_management
from utils.database import Database
from utils.messaging import TelegramSender

logging.basicConfig(level=logging.INFO)

# The API will not allow more than ~30 messages to different users per second
TIMEOUT_BETWEEN_MESSAGES = 0.2

ON_HEROKU = os.environ.get('ON_HEROKU')
TOKEN = os.environ['TOKEN']
bot = telebot.TeleBot(TOKEN)

server = Flask(__name__)

TELEBOT_URL = 'telebot_webhook/'
BASE_URL = 'https://kappa-vedi-bot.herokuapp.com/'

MONGO_URL = os.environ.get('MONGODB_URI')
DATABASE = Database(MONGO_URL, admins={
    'cointegrated', 'stepan_ivanov', 'jonibekortikov', 'dkkharlm', 'helmeton', 'kolikovnikita',
})

if os.environ.get('SENTRY_DSN'):
    sentry_sdk.init(os.environ.get('SENTRY_DSN'))

ADMIN_URL_PREFIX = os.environ.get('ADMIN_URL_PREFIX') or str(random.random())

SENDER = TelegramSender(bot, config=config, timeout=TIMEOUT_BETWEEN_MESSAGES)


ALL_CONTENT_TYPES = [
    'audio', 'channel_chat_created', 'contact', 'delete_chat_photo', 'document', 'group_chat_created',
    'left_chat_member',
    'location', 'migrate_from_chat_id', 'migrate_to_chat_id', 'new_chat_members', 'new_chat_photo', 'new_chat_title',
    'photo', 'pinned_message', 'sticker', 'supergroup_chat_created', 'text', 'video', 'video_note', 'voice'
]


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


@server.route("/{}/restart-coffee/".format(ADMIN_URL_PREFIX))
def force_restart_coffee():
    daily_random_coffee(database=DATABASE, sender=SENDER, force_restart=True)
    return "Кофе перезапущен!", 200


@server.route("/send-events/")
def do_event_management():
    daily_event_management(database=DATABASE, sender=SENDER)
    return "Сделал со встречами всё, что хотел!", 200


@bot.message_handler(func=lambda message: True, content_types=ALL_CONTENT_TYPES)
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
