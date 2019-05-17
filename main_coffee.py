#!/usr/bin/python
# -*- coding: utf-8 -*-
import argparse
import telebot
import os
import pymongo
import random
import re

from utils.database import Database
from utils.dialogue_management import Context

from events import try_invitation, try_event_usage, try_event_creation
from peoplebook import try_peoplebook_management

from datetime import datetime
from collections import defaultdict
from flask import Flask, request
from telebot import types

import matchers

ON_HEROKU = os.environ.get('ON_HEROKU')
TOKEN = os.environ['TOKEN']
bot = telebot.TeleBot(TOKEN)

server = Flask(__name__)
TELEBOT_URL = 'telebot_webhook/'
BASE_URL = 'https://kappa-vedi-bot.herokuapp.com/'

MONGO_URL = os.environ.get('MONGODB_URI')
DATABASE = Database(MONGO_URL, admins={'cointegrated', 'stepan_ivanov', 'jonibekortikov', 'dkkharlm', 'helmeton'})


class LoggedMessage:
    def __init__(self, text, user_id, from_user, database: Database):
        self.text = text
        self.user_id = user_id
        self.from_user = from_user
        self.timestamp = str(datetime.utcnow())

        self.mongo_collection = database.mongo_messages

    def save(self):
        self.mongo_collection.insert_one(self.to_dict())

    def to_dict(self):
        return {
            'text': self.text,
            'user_id': self.user_id,
            'from_user': self.from_user,
            'timestamp': self.timestamp
        }


def try_sending_message(bot, text, database, reply_to=None, user_id=None):
    try:
        bot.send_message(user_id, text)
        LoggedMessage(text=text, user_id=user_id, from_user=False, database=database).save()
    except Exception as e:
        error = '\n'.join([
            'Ошибка при отправке сообщения!',
            'Текст: {}'.format(text),
            'user_id: {}'.format(user_id),
            'chat_id: {}'.format(reply_to.chat.username if reply_to is not None else None),
            'error: {}'.format(e)
        ])
        bot.send_message(71034798, error)


def get_or_insert_user(tg_user=None, tg_uid=None, database: Database=None):
    if tg_user is not None:
        uid = tg_user.id
    elif tg_uid is not None:
        uid = tg_uid
    else:
        return None
    assert database is not None
    found = database.mongo_users.find_one({'tg_id': uid})
    if found is not None:
        if tg_user is not None and found.get('username') != tg_user.username:
            database.mongo_users.update_one({'tg_id': uid}, {'$set': {'username': tg_user.username}})
            found = database.mongo_users.find_one({'tg_id': uid})
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
    database.mongo_users.insert_one(new_user)
    return new_user


@server.route("/" + TELEBOT_URL)
def web_hook():
    bot.remove_webhook()
    bot.set_webhook(url=BASE_URL + TELEBOT_URL + TOKEN)
    return "!", 200


@server.route("/wakeup/")
def wake_up():
    database = DATABASE
    web_hook()
    if datetime.today().weekday() == 5:  # on saturday, we recalculate the matches
        active_users = database.mongo_users.find({'wants_next_coffee': True})
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
        database.mongo_coffee_pairs.insert_one({'date': str(datetime.utcnow()), 'matches': user_to_matches})

    last_matches = database.mongo_coffee_pairs.find_one({}, sort=[('_id', pymongo.DESCENDING)])
    if last_matches is None:
        bot.send_message(71034798, 'я не нашёл матчей, посмотри логи плз')
    else:
        bot.send_message(71034798, 'вот какие матчи сегодня: {}'.format(last_matches))
        for username, matches in last_matches['matches'].items():
            user_obj = database.mongo_users.find_one({'username': username})
            if user_obj is None:
                bot.send_message(71034798, 'юзер {} не был найден!'.format(username))
            else:
                remind_about_coffee(user_obj, matches, database=database)
    return "Маам, ну ещё пять минуточек!", 200


def remind_about_coffee(user_obj, matches, database: Database):
    user_id = user_obj['tg_id']
    with_whom = 'с @{}'.format(matches[0])
    for next_match in matches[1:]:
        with_whom = with_whom + ' и c @{}'.format(next_match)

    response = None
    if datetime.today().weekday() == 5:  # saturday
        response = 'На этой неделе вы пьёте кофе {}.\nЕсли вы есть, будьте первыми!'.format(with_whom)
    elif datetime.today().weekday() == 4:  # friday
        response = 'На этой неделе вы, наверное, пили кофе {}.\nКак оно прошло?'.format(with_whom)

    if response is not None:
        try_sending_message(bot=bot, user_id=user_id, text=response, database=database)


TAKE_PART = 'Участвовать в следующем кофе'
NOT_TAKE_PART = 'Не участвовать в следующем кофе'

HELP = """Я бот, который пока что умеет только назначать random coffee. 
Это значит, что я каждую субботу в 8 вечера выбираю вам в пару случайного члена клуба. 
После этого у вас есть неделя, чтобы встретиться, выпить вместе кофе и поговорить о жизни.
(Неделя считается до следующих выходных включительно.)
P.S. А ещё я скоро научусь приглашать гостей на встречи и обновлять странички в пиплбуке.
Если вы есть, будьте первыми!"""
HELP_UNAUTHORIZED = """Привет! Я бот Каппа Веди.
К сожалению, вас нет в списке знакомых мне пользователей.
Если вы гость встречи, попросите кого-то из членов клуба сделать для вас приглашение в боте.
Если вы член клуба, попросите Жонибека, Степана, Дашу, Альфию или Давида (@cointegrated) добавить вас в список членов.
Если вы есть, будьте первыми!"""


def try_queued_messages(ctx: Context, database: Database):
    queue = list(database.message_queue.find({'username': ctx.user_object['username'], 'fresh': True}))
    if len(queue) == 0:
        return ctx
    first_message = queue[0]
    database.message_queue.update_one({'_id': first_message['_id']}, {'$set': {'fresh': False}})
    ctx.intent = first_message.get('intent', 'QUEUED_MESSAGE')
    bullshit = 'Я собирался сообщить вам о чем-то важном, но всё забыл. Напишите @cointegrated, пожалуйста.'
    ctx.response = first_message.get('text', bullshit)
    return ctx


def try_membership_management(ctx: Context, database: Database):
    if not database.is_at_least_member(ctx.user_object):
        return ctx
    # todo: add guest management
    if not database.is_admin(ctx.user_object):
        return ctx
    # member management
    if re.match('(добавь|добавить) (члена|членов)( в клуб| клуба)?', ctx.text_normalized):
        ctx.intent = 'MEMBER_ADD_INIT'
        ctx.response = 'Введите телеграмовский логин/логины новых членов через пробел.'
    elif ctx.last_intent == 'MEMBER_ADD_INIT':
        ctx.intent = 'MEMBER_ADD_COMPLETE'
        logins = [c.strip(',').strip('@').lower() for c in ctx.text.split()]
        resp = 'Вот что получилось:'
        for login in logins:
            if not matchers.is_like_telegram_login(login):
                resp = resp + '\nСлово "{}" не очень похоже на логин, пропускаю.'.format(login)
                continue
            existing = database.mongo_membership.find_one({'username': login, 'is_member': True})
            if existing is None:
                database.mongo_membership.update_one({'username': login}, {'$set': {'is_member': True}}, upsert=True)
                resp = resp + '\n@{} успешно добавлен(а) в список членов.'.format(login)
            else:
                resp = resp + '\n@{} уже является членом клуба.'.format(login)
        ctx.response = resp
    return ctx


def try_coffee_management(ctx: Context, database: Database):
    if ctx.text == TAKE_PART:
        ctx.the_update = {"$set": {'wants_next_coffee': True}}
        ctx.response = 'Окей, на следующей неделе вы будете участвовать в random coffee!'
        ctx.intent = 'TAKE_PART'
    elif ctx.text == NOT_TAKE_PART:
        ctx.the_update = {"$set": {'wants_next_coffee': False}}
        ctx.response = 'Окей, на следующей неделе вы не будете участвовать в random coffee!'
        ctx.intent = 'NOT_TAKE_PART'
    return ctx


def try_unauthorized_help(ctx: Context, database: Database):
    if not database.is_at_least_guest(ctx.user_object):
        ctx.intent = 'UNAUTHORIZED'
        ctx.response = HELP_UNAUTHORIZED
    return ctx


@bot.message_handler(func=lambda message: True)
def process_message(msg):
    database = DATABASE
    uo = get_or_insert_user(msg.from_user, database=database)
    user_id = msg.chat.id
    LoggedMessage(text=msg.text, user_id=user_id, from_user=True, database=database).save()
    ctx = Context(text=msg.text, user_object=uo)

    for handler in [
        try_queued_messages,
        try_invitation,
        try_event_creation,
        try_event_usage,
        try_peoplebook_management,
        try_coffee_management,
        try_membership_management,
        try_unauthorized_help
    ]:
        ctx = handler(ctx, database=database)
        if ctx.intent is not None:
            break

    if ctx.intent is not None:
        pass  # everything has been set by a handler
    elif re.match('привет', ctx.text_normalized):
        ctx.intent = 'HELLO'
        ctx.response = random.choice([
            'Приветствую! \U0001f60a',
            'Дратути!\U0001f643',
            'Привет!',
            'Привет-привет',
            'Рад вас видеть!',
            'Здравствуйте, сударь! \U0001f60e'
        ])
    else:
        ctx.response = HELP
        ctx.intent = 'OTHER'
    database.mongo_users.update_one({'tg_id': msg.from_user.id}, ctx.make_update())
    user_object = get_or_insert_user(tg_uid=msg.from_user.id, database=database)

    # context-independent suggests (they are always below the dependent ones)
    if database.is_at_least_member(user_object):
        ctx.suggests.append(TAKE_PART if not user_object.get('wants_next_coffee') else NOT_TAKE_PART)

    if database.is_at_least_guest(user_object):
        ctx.suggests.append('Покажи встречи')
        ctx.suggests.append('Мой пиплбук')

    if database.is_admin(user_object):
        ctx.suggests.append('Создать встречу')
        ctx.suggests.append('Добавить членов')

    markup = types.ReplyKeyboardMarkup(row_width=max(1, min(3, int(len(ctx.suggests) / 2))))
    # todo: split suggests into rows with respect to their lengths
    markup.add(*ctx.suggests)
    LoggedMessage(text=ctx.response, user_id=user_id, from_user=False, database=database).save()

    bot.reply_to(msg, ctx.response, reply_markup=markup, parse_mode='html')


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
