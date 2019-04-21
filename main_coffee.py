#!/usr/bin/python
# -*- coding: utf-8 -*-
import argparse
import telebot
import os
import pymongo
import random
import re
from datetime import datetime
from collections import defaultdict
from flask import Flask, request
from pymongo import MongoClient
from telebot import types

ON_HEROKU = os.environ.get('ON_HEROKU')
TOKEN = os.environ['TOKEN']
bot = telebot.TeleBot(TOKEN)

server = Flask(__name__)
TELEBOT_URL = 'telebot_webhook/'
BASE_URL = 'https://kappa-vedi-bot.herokuapp.com/'


MONGO_URL = os.environ.get('MONGODB_URI')
mongo_client = MongoClient(MONGO_URL)
mongo_db = mongo_client.get_default_database()
mongo_users = mongo_db.get_collection('users')
mongo_messages = mongo_db.get_collection('messages')
mongo_coffee_pairs = mongo_db.get_collection('coffee_pairs')


class LoggedMessage:
    def __init__(self, text, user_id, from_user):
        self.text = text
        self.user_id = user_id
        self.from_user = from_user
        self.timestamp = str(datetime.utcnow())

        self.mongo_collection = mongo_messages

    def save(self):
        self.mongo_collection.insert_one(self.to_dict())

    def to_dict(self):
        return {
            'text': self.text,
            'user_id': self.user_id,
            'from_user': self.from_user,
            'timestamp': self.timestamp
        }


def get_or_insert_user(tg_user=None, tg_uid=None):
    if tg_user is not None:
        uid = tg_user.id
    elif tg_uid is not None:
        uid = tg_uid
    else:
        return None
    found = mongo_users.find_one({'tg_id': uid})
    if found is not None:
        return found
    if tg_user is None:
        return ValueError('User should be created, but telegram user object was not provided.')
    new_user = dict(
        tg_id=tg_user.id,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
        username=tg_user.username,
        wants_next_coffee=False
    )
    mongo_users.insert_one(new_user)
    return new_user


@server.route("/" + TELEBOT_URL)
def web_hook():
    bot.remove_webhook()
    bot.set_webhook(url=BASE_URL + TELEBOT_URL + TOKEN)
    return "!", 200


@server.route("/wakeup/")
def wake_up():
    web_hook()
    if datetime.today().weekday() == 5:  # on saturday, we recalculate the matches
        active_users = mongo_users.find({'wants_next_coffee': True})
        print('active users: {}'.format(active_users))
        free_users = [user['username'] for user in active_users]
        random.shuffle(free_users)
        user_to_matches = defaultdict(list)
        for i in range(0, len(free_users)-1, 2):
            user_to_matches[free_users[i]] = [free_users[i + 1]]
            user_to_matches[free_users[i + 1]] = [free_users[i]]
        if len(free_users) % 2 == 1:
            user_to_matches[free_users[0]].append(free_users[-1])
            user_to_matches[free_users[-1]].append(free_users[0])
        mongo_coffee_pairs.insert_one({'date': str(datetime.utcnow()), 'matches': user_to_matches})

    last_matches = mongo_coffee_pairs.find_one({}, sort=[('_id', pymongo.DESCENDING)])
    if last_matches is None:
        bot.send_message(71034798, 'я не нашёл матчей, посмотри логи плз')
    else:
        bot.send_message(71034798, 'вот какие матчи сегодня: {}'.format(last_matches))
        for username, matches in last_matches['matches'].items():
            user_obj = mongo_users.find_one({'username': username})
            if user_obj is None:
                bot.send_message(71034798, 'юзер {} не был найден!'.format(username))
            else:
                response = 'На этой неделе вы пьёте кофе с @{}'.format(matches[0])
                for next_match in matches[1:]:
                    response = response + ' и c @{}'.format(next_match)
                response = response + ' . Если вы есть, будьте первыми!'
                user_id = user_obj['tg_id']
                if datetime.today().weekday() == 5:  # todo: maybe, send reminder on other days of week
                    bot.send_message(user_id, response)
                    LoggedMessage(text=response, user_id=user_id, from_user=False).save()
    return "Маам, ну ещё пять минуточек!", 200


TAKE_PART = 'Участвовать в следующем кофе'
NOT_TAKE_PART = 'Не участвовать в следующем кофе'

HELP = """Я бот, который пока что умеет только назначать random coffee. 
Это значит, что я каждую субботу в 8 вечера выбираю вам в пару случайного члена клуба. 
После этого у вас есть неделя, чтобы встретиться, выпить вместе кофе и поговорить о жизни.
(Неделя считается до следующих выходных включительно.)
Если вы есть, будьте первыми!"""


@bot.message_handler(func=lambda message: True)
def process_message(message):
    user_object = get_or_insert_user(message.from_user)
    user_id = message.chat.id
    the_update = None
    LoggedMessage(text=message.text, user_id=user_id, from_user=True).save()
    text_normalized = re.sub('[.,!?:;()\s]+', ' ', message.text.lower()).strip()
    if re.match('привет', text_normalized):
        intent = 'HELLO'
        response = random.choice(
            'Приветствую! \U0001f60a',
            'Дратути!\U0001f643',
            'Привет!',
            'Привет-привет',
            'Рад вас видеть!',
            'Здравствуйте, сударь! \U0001f60e'
        )
    elif message.text == TAKE_PART:
        the_update = {"$set": {'wants_next_coffee': True}}
        response = 'Окей, на следующей неделе вы будете участвовать в random coffee!'
        intent = 'TAKE_PART'
    elif message.text == NOT_TAKE_PART:
        the_update = {"$set": {'wants_next_coffee': False}}
        response = 'Окей, на следующей неделе вы не будете участвовать в random coffee!'
        intent = 'NOT_TAKE_PART'
    else:
        response = HELP
        intent = 'OTHER'
    if the_update is None:
        the_update = {}
    if '$set' not in the_update:
        the_update['$set'] = {}
    the_update['$set']['last_intent'] = intent
    mongo_users.update_one({'tg_id': message.from_user.id}, the_update)
    user_object = get_or_insert_user(tg_uid=message.from_user.id)
    markup = types.ReplyKeyboardMarkup()
    markup.add(TAKE_PART if not user_object.get('wants_next_coffee') else NOT_TAKE_PART)

    LoggedMessage(text=response, user_id=user_id, from_user=False).save()

    bot.reply_to(message, response, reply_markup=markup)


@server.route('/' + TELEBOT_URL + TOKEN, methods=['POST'])
def get_message():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200


parser = argparse.ArgumentParser(description='Run the bot')
parser.add_argument('--poll', action='store_true')


def main_new():
    args = parser.parse_args()
    if args.poll:
        bot.remove_webhook()
        bot.polling()
    else:
        web_hook()
        server.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))


if __name__ == '__main__':
    main_new()
