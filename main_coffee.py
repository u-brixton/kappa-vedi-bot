#!/usr/bin/python
# -*- coding: utf-8 -*-
import argparse
import telebot
import os
import peoplebook
import pymongo
import random
import re
from datetime import datetime, timedelta
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
mongo_events = mongo_db.get_collection('events')
mongo_participations = mongo_db.get_collection('event_participations')


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


def is_admin(user_object):
    if user_object.get('username') in {'cointegrated', 'Stepan_Ivanov', 'JonibekOrtikov', 'love_buh', 'helmeton'}:
        return True
    return False


def is_member(user_object):
    # todo: lookup for the list of members
    return True


def is_guest(user_object):
    # todo: lookup for the list of guests
    return True


@bot.message_handler(func=lambda message: True)
def process_message(message):
    user_object = get_or_insert_user(message.from_user)
    user_id = message.chat.id
    the_update = None
    LoggedMessage(text=message.text, user_id=user_id, from_user=True).save()
    text_normalized = re.sub('[.,!?:;()\s]+', ' ', message.text.lower()).strip()
    last_intent = user_object.get('last_intent', '')
    if is_admin(user_object) and text_normalized == 'созда(ть|й) встречу':
        intent = 'EVENT_CREATE_INIT'
        response = 'Придумайте название встречи (например, Встреча Каппа Веди 27 апреля):'
        the_update = {'$set': {'event_to_create': {}}}
    elif is_admin(user_object) and last_intent == 'EVENT_CREATE_INIT':
        intent = 'EVENT_CREATE_SET_TITLE'
        event_to_create = user_object.get('event_to_create', {})
        # todo: validate that event title is not empty and long enough
        event_to_create['title'] = message.text
        the_update = {'$set': {'event_to_create': event_to_create}}
        response = 'Хорошо, назовём встречу "{}".'.format(message.text)
        response = response + '\nТеперь придумайте название встречи из латинских букв и цифр (например, april2019):'
    elif is_admin(user_object) and last_intent == 'EVENT_CREATE_SET_TITLE':
        intent = 'EVENT_CREATE_SET_CODE'
        event_to_create = user_object.get('event_to_create', {})
        # todo: validate that event code is indeed alphanumeric
        # todo: validate that event code is not equal to any of the reserved commands
        event_to_create['code'] = message.text
        the_update = {'$set': {'event_to_create': event_to_create}}
        response = 'Хорошо, код встречи будет "{}". '.format(message.text)
        response = response + '\nТеперь введите дату встречи в формате ГГГГ.ММ.ДД:'
    elif is_admin(user_object) and last_intent == 'EVENT_CREATE_SET_CODE':
        intent = 'EVENT_CREATE_SET_DATE'
        event_to_create = user_object.get('event_to_create', {})
        # todo: validate that event date is indeed yyyy.mm.dd
        event_to_create['date'] = message.text
        the_update = {'$set': {'event_to_create': event_to_create}}
        response = 'Хорошо, дата встречи будет "{}". '.format(message.text)
        mongo_events.insert_one(event_to_create)
        response = response + '\nВстреча успешно создана!'
        # todo: propose sending invitations
    elif is_member(user_object) and re.match('най[тд]и встреч[уи]', text_normalized):
        intent = 'EVENT_GET_LIST'
        all_events = mongo_events.find({})
        # todo: compare with more exact time (or maybe just add a day buffer)
        future_events = [
            e for e in all_events if datetime.strptime(e['date'], '%Y.%m.%d') + timedelta(days=1) > datetime.utcnow()
        ]
        if len(future_events) > 0:
            response = 'Найдены предстоящие события:\n'
            for e in future_events:
                response = response + '/{}: "{}", {}'.format(e['code'], e['title'], e['date'])
        else:
            response = 'Предстоящих событий не найдено'
    elif is_member(user_object) and last_intent == 'EVENT_GET_LIST':
        event_code = message.text.lstrip('/')
        the_event = mongo_events.find_one({'code': event_code})
        if the_event is not None:
            intent = 'EVENT_CHOOSE_SUCCESS'
            the_update = {'$set': {'event_code': event_code}}
            response = 'Событие "{}" {}'.format(the_event['title'], the_event['date'])
            # todo: check if the user participates
            the_participation = mongo_participations.find_one(
                {'username': user_object['username'], 'code': the_event['code']}
            )
            if the_participation is None or not the_participation.get('engaged'):
                response = response + '\n /engage - участвовать'
            else:
                response = response + '\n /unengage - отказаться от участия'
                response = response + '\n /invite - пригласить гостя (пока не работает)'
                # todo: add the option to invite everyone
        else:
            intent = 'EVENT_CHOOSE_FAIL'
            response = 'Такое событие не найдено'
    elif is_member(user_object) and last_intent == 'EVENT_CHOOSE_SUCCESS' and message.text == '/engage':
        intent = 'EVENT_ENGAGE'
        event_code = user_object.get('event_code')
        if event_code is None:
            response = 'почему-то не удалось получить код события, сообщите @cointegrated'
        else:
            mongo_participations.update_one(
                {'username': user_object['username'], 'code': event_code},
                {'$set': {'engaged': True}}, upsert=True
            )
            response = 'Теперь вы участвуете в мероприятии {}!'.format(event_code)
    elif is_member(user_object) and last_intent == 'EVENT_CHOOSE_SUCCESS' and message.text == '/unengage':
        intent = 'EVENT_UNENGAGE'
        event_code = user_object.get('event_code')
        if event_code is None:
            response = 'почему-то не удалось получить код события, сообщите @cointegrated'
        else:
            mongo_participations.update_one(
                {'username': user_object['username'], 'code': event_code},
                {'$set': {'engaged': False}}, upsert=True
            )
            response = 'Теперь вы не участвуете в мероприятии {}!'.format(event_code)
    elif is_member(user_object) and last_intent == 'EVENT_CHOOSE_SUCCESS' and message.text == '/invite':
        intent = 'EVENT_INVITE'
        # todo: process the invitation
        response = 'Пока что я не научилась приглашать гостей'
    elif is_guest(user_object) and re.match('мой пиплбук', message.text):
        mongo_peoplebook = mongo_db.get_collection('peoplebook')
        the_profile = mongo_peoplebook.find_one({'username': user_object['username']})
        if the_profile is None:
            intent = 'PEOPLEBOOK_GET_FAIL'
            response = 'У вас ещё нет профиля в пиплбуке. Завести?'
        else:
            intent = 'PEOPLEBOOK_GET_SUCCESS'
            response = 'Ваш профиль:\n'
            response = response + peoplebook.render_text_profile(the_profile)
    elif is_guest(user_object) and last_intent == 'PEOPLEBOOK_GET_FAIL' and re.match('да', text_normalized):
        intent = 'PEOPLEBOOK_CREATE_PROFILE'
        mongo_peoplebook = mongo_db.get_collection('peoplebook')
        mongo_peoplebook.insert_one({'username': user_object['username']})
        response = 'Создаём профиль в пиплбуке. Пожалуйста, введите ваше имя (без фамилии):'
    elif is_guest(user_object) and last_intent == 'PEOPLEBOOK_CREATE_PROFILE':
        intent = 'PEOPLEBOOK_SET_FIRST_NAME'
        mongo_peoplebook = mongo_db.get_collection('peoplebook')
        mongo_peoplebook.update_one({'username': user_object['username']}, {'$set': {'first_name': message.text}})
        response = 'Отлично! Теперь введите вашу фамилию:'
    elif is_guest(user_object) and last_intent == 'PEOPLEBOOK_SET_FIRST_NAME':
        intent = 'PEOPLEBOOK_SET_ACTIVITY'
        mongo_peoplebook = mongo_db.get_collection('peoplebook')
        mongo_peoplebook.update_one({'username': user_object['username']}, {'$set': {'last_name': message.text}})
        response = 'Отлично! Теперь расскажите, чем вы занимаетесь:'
    elif is_guest(user_object) and last_intent == 'PEOPLEBOOK_SET_ACTIVITY':
        intent = 'PEOPLEBOOK_SET_TOPICS'
        mongo_peoplebook = mongo_db.get_collection('peoplebook')
        mongo_peoplebook.update_one({'username': user_object['username']}, {'$set': {'activity': message.text}})
        response = 'Отлично! Теперь расскажите, о каких темах вы могли бы рассказать:'
    elif is_guest(user_object) and last_intent == 'PEOPLEBOOK_SET_TOPICS':
        intent = 'PEOPLEBOOK_SET_CONTACTS'
        mongo_peoplebook = mongo_db.get_collection('peoplebook')
        mongo_peoplebook.update_one({'username': user_object['username']}, {'$set': {'topics': message.text}})
        response = 'Отлично! Теперь перечислите ваши контакты:'
    elif is_guest(user_object) and last_intent == 'PEOPLEBOOK_SET_CONTACTS':
        intent = 'PEOPLEBOOK_SET_CONTACTS'
        mongo_peoplebook = mongo_db.get_collection('peoplebook')
        mongo_peoplebook.update_one({'username': user_object['username']}, {'$set': {'contacts': message.text}})
        # todo: ask about photo
        response = 'Отлично! Ваш профайл создан. Выглядит примерно так:'
        the_profile = mongo_peoplebook.find_one({'username': user_object['username']})
        response = response + '\n' + peoplebook.render_text_profile(the_profile)
    elif re.match('привет', text_normalized):
        intent = 'HELLO'
        response = random.choice([
            'Приветствую! \U0001f60a',
            'Дратути!\U0001f643',
            'Привет!',
            'Привет-привет',
            'Рад вас видеть!',
            'Здравствуйте, сударь! \U0001f60e'
        ])
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

    bot.reply_to(message, response, reply_markup=markup, parse_mode='html')


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
