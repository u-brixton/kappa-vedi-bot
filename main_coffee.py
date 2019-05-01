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
mongo_peoplebook = mongo_db.get_collection('peoplebook')
mongo_membership = mongo_db.get_collection('membership')


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
    if user_object.get('username').lower() in {
        'cointegrated', 'stepan_ivanov', 'jonibekortikov', 'dkkharlm', 'helmeton'
    }:
        return True
    return False


def is_member(user_object):
    # todo: lookup for the list of members
    return True


def is_guest(user_object):
    # todo: lookup for the list of guests
    return True


class Context:
    def __init__(self, user_object=None, text=None):
        self.user_object = user_object
        self.last_intent = user_object.get('last_intent', '')
        self.last_expected_inent = user_object.get('last_expected_intent', '')
        self.text = text
        self.text_normalized = re.sub('[.,!?:;()\s]+', ' ', text.lower()).strip()

        self.intent = None
        self.response = None
        self.the_update = None
        self.expected_intent = None

    def make_update(self):
        if self.the_update is None:
            the_update = {}
        else:
            the_update = self.the_update
        if '$set' not in the_update:
            the_update['$set'] = {}
        the_update['$set']['last_intent'] = self.intent
        the_update['$set']['last_expected_intent'] = self.expected_intent
        return the_update


def try_event_creation(ctx: Context):
    if not is_admin(ctx.user_object):
        return ctx
    if ctx.text_normalized == 'созда(ть|й) встречу':
        ctx.intent = 'EVENT_CREATE_INIT'
        ctx.response = 'Придумайте название встречи (например, Встреча Каппа Веди 27 апреля):'
        ctx.the_update = {'$set': {'event_to_create': {}}}
    elif ctx.last_intent == 'EVENT_CREATE_INIT':
        ctx.intent = 'EVENT_CREATE_SET_TITLE'
        event_to_create = ctx.user_object.get('event_to_create', {})
        # todo: validate that event title is not empty and long enough
        event_to_create['title'] = ctx.text
        ctx.the_update = {'$set': {'event_to_create': event_to_create}}
        ctx.response = (
                'Хорошо, назовём встречу "{}".'.format(ctx.text)
                + '\nТеперь придумайте название встречи из латинских букв и цифр '
                + '(например, april2019):'
        )
    elif ctx.last_intent == 'EVENT_CREATE_SET_TITLE':
        ctx.intent = 'EVENT_CREATE_SET_CODE'
        event_to_create = ctx.user_object.get('event_to_create', {})
        # todo: validate that event code is indeed alphanumeric
        # todo: validate that event code is not equal to any of the reserved commands
        event_to_create['code'] = ctx.text
        ctx.the_update = {'$set': {'event_to_create': event_to_create}}
        ctx.response = (
                'Хорошо, код встречи будет "{}". '.format(ctx.text)
                + '\nТеперь введите дату встречи в формате ГГГГ.ММ.ДД:'
        )
    elif ctx.last_intent == 'EVENT_CREATE_SET_CODE':
        ctx.intent = 'EVENT_CREATE_SET_DATE'
        event_to_create = ctx.user_object.get('event_to_create', {})
        # todo: validate that event date is indeed yyyy.mm.dd
        event_to_create['date'] = ctx.text
        ctx.the_update = {'$set': {'event_to_create': event_to_create}}
        ctx.response = 'Хорошо, дата встречи будет "{}". '.format(ctx.text) + '\nВстреча успешно создана!'
        mongo_events.insert_one(event_to_create)
        # todo: propose sending invitations
    return ctx


def try_event_usage(ctx: Context):
    if not is_member(ctx.user_object) and not is_guest(ctx.user_object):
        return ctx
    if re.match('най[тд]и встреч[уи]', ctx.text_normalized):
        ctx.intent = 'EVENT_GET_LIST'
        all_events = mongo_events.find({})
        # todo: compare with more exact time (or maybe just add a day buffer)
        future_events = [
            e for e in all_events if datetime.strptime(e['date'], '%Y.%m.%d') + timedelta(days=1) > datetime.utcnow()
        ]
        if len(future_events) > 0:
            ctx.response = 'Найдены предстоящие события:\n'
            for e in future_events:
                ctx.response = ctx.response + '/{}: "{}", {}'.format(e['code'], e['title'], e['date'])
        else:
            ctx.response = 'Предстоящих событий не найдено'
    elif ctx.last_intent == 'EVENT_GET_LIST':
        event_code = ctx.text.lstrip('/')
        the_event = mongo_events.find_one({'code': event_code})
        if the_event is not None:
            ctx.intent = 'EVENT_CHOOSE_SUCCESS'
            ctx.the_update = {'$set': {'event_code': event_code}}
            ctx.response = 'Событие "{}" {}'.format(the_event['title'], the_event['date'])
            # todo: check if the user participates
            the_participation = mongo_participations.find_one(
                {'username': ctx.user_object['username'], 'code': the_event['code']}
            )
            if the_participation is None or not the_participation.get('engaged'):
                ctx.response = ctx.response + '\n /engage - участвовать'
            else:
                ctx.response = ctx.response + '\n /unengage - отказаться от участия'
                ctx.response = ctx.response + '\n /invite - пригласить гостя (пока не работает)'
                # todo: add the option to invite everyone
        else:
            ctx.intent = 'EVENT_CHOOSE_FAIL'
            ctx.response = 'Такое событие не найдено'
    elif ctx.last_intent == 'EVENT_CHOOSE_SUCCESS' and ctx.text == '/engage':
        ctx.intent = 'EVENT_ENGAGE'
        event_code = ctx.user_object.get('event_code')
        if event_code is None:
            ctx.response = 'почему-то не удалось получить код события, сообщите @cointegrated'
        else:
            mongo_participations.update_one(
                {'username': ctx.user_object['username'], 'code': event_code},
                {'$set': {'engaged': True}}, upsert=True
            )
            ctx.response = 'Теперь вы участвуете в мероприятии {}!'.format(event_code)
    elif ctx.last_intent == 'EVENT_CHOOSE_SUCCESS' and ctx.text == '/unengage':
        ctx.intent = 'EVENT_UNENGAGE'
        event_code = ctx.user_object.get('event_code')
        if event_code is None:
            ctx.response = 'почему-то не удалось получить код события, сообщите @cointegrated'
        else:
            mongo_participations.update_one(
                {'username': ctx.user_object['username'], 'code': event_code},
                {'$set': {'engaged': False}}, upsert=True
            )
            ctx.response = 'Теперь вы не участвуете в мероприятии {}!'.format(event_code)
    elif ctx.last_intent == 'EVENT_CHOOSE_SUCCESS' and ctx.text == '/invite':
        ctx.intent = 'EVENT_INVITE'
        # todo: process the invitation
        ctx.response = 'Пока что я не научился приглашать гостей'
    return ctx


class PB:
    PEOPLEBOOK_GET_SUCCESS = 'PEOPLEBOOK_GET_SUCCESS'
    PEOPLEBOOK_GET_FAIL = 'PEOPLEBOOK_GET_FAIL'
    PEOPLEBOOK_DO_NOT_CREATE = 'PEOPLEBOOK_DO_NOT_CREATE'
    PEOPLEBOOK_CREATE_PROFILE = 'PEOPLEBOOK_CREATE_PROFILE'
    PEOPLEBOOK_SET_FIRST_NAME = 'PEOPLEBOOK_SET_FIRST_NAME'
    PEOPLEBOOK_SET_LAST_NAME = 'PEOPLEBOOK_SET_LAST_NAME'
    PEOPLEBOOK_SET_ACTIVITY = 'PEOPLEBOOK_SET_ACTIVITY'
    PEOPLEBOOK_SET_TOPICS = 'PEOPLEBOOK_SET_TOPICS'
    PEOPLEBOOK_SET_CONTACTS = 'PEOPLEBOOK_SET_CONTACTS'
    PEOPLEBOOK_SET_PHOTO = 'PEOPLEBOOK_SET_PHOTO'
    PEOPLEBOOK_SET_FINAL = 'PEOPLEBOOK_SET_FINAL'
    PEOPLEBOOK_SHOW_PROFILE = 'PEOPLEBOOK_SHOW_PROFILE'
    CREATING_PB_PROFILE = 'creating_pb_profile'


def try_peoplebook_management(ctx: Context):
    if not is_member(ctx.user_object) and not is_guest(ctx.user_object):
        return ctx
    # first process the incoming info
    within = ctx.user_object.get(PB.CREATING_PB_PROFILE)
    if re.match('мой пиплбук', ctx.text):
        the_profile = mongo_peoplebook.find_one({'username': ctx.user_object['username']})
        if the_profile is None:
            ctx.intent = PB.PEOPLEBOOK_GET_FAIL
            ctx.response = 'У вас ещё нет профиля в пиплбуке. Завести?'
        else:
            ctx.intent = PB.PEOPLEBOOK_GET_SUCCESS
            ctx.response = 'Ваш профиль:\n' + peoplebook.render_text_profile(the_profile)
    elif ctx.last_intent == PB.PEOPLEBOOK_GET_FAIL:
        if re.match('да', ctx.text_normalized):
            ctx.intent = PB.PEOPLEBOOK_CREATE_PROFILE
            ctx.expected_intent = PB.PEOPLEBOOK_SET_FIRST_NAME
            mongo_peoplebook.insert_one({'username': ctx.user_object['username']})
            ctx.the_update = {'$set': {PB.CREATING_PB_PROFILE: True}}
            ctx.response = 'Отлично! Создаём профиль в пиплбуке.'
        elif re.match('нет', ctx.text_normalized):
            ctx.intent = PB.PEOPLEBOOK_DO_NOT_CREATE
            ctx.response = 'На нет и суда нет.'
        else:
            ctx.intent = PB.PEOPLEBOOK_GET_FAIL
            ctx.response = 'Так, я не понял. Профиль-то создавать? Ответьте "да" или "нет", пожалуйста.'
    elif ctx.last_expected_inent == PB.PEOPLEBOOK_SET_FIRST_NAME:
        ctx.intent = PB.PEOPLEBOOK_SET_FIRST_NAME
        if len(ctx.text_normalized) > 0:
            mongo_peoplebook.update_one({'username': ctx.user_object['username']}, {'$set': {'first_name': ctx.text}})
            ctx.expected_intent = PB.PEOPLEBOOK_SET_LAST_NAME if within else PB.PEOPLEBOOK_SHOW_PROFILE
            ctx.response = 'Отлично!'
        else:
            ctx.response = 'Получилось что-то странное, попробуйте ещё раз!'
            ctx.expected_intent = PB.PEOPLEBOOK_SET_FIRST_NAME
    elif ctx.last_expected_inent == PB.PEOPLEBOOK_SET_LAST_NAME:
        ctx.intent = PB.PEOPLEBOOK_SET_LAST_NAME
        if len(ctx.text_normalized) > 0:
            mongo_peoplebook.update_one({'username': ctx.user_object['username']}, {'$set': {'last_name': ctx.text}})
            ctx.response = 'Окей.'
            ctx.expected_intent = PB.PEOPLEBOOK_SET_ACTIVITY if within else PB.PEOPLEBOOK_SHOW_PROFILE
        else:
            ctx.response = 'Что-то маловато для фамилии, попробуйте ещё.'
            ctx.expected_intent = PB.PEOPLEBOOK_SET_LAST_NAME
    elif ctx.last_expected_inent == PB.PEOPLEBOOK_SET_ACTIVITY:
        ctx.intent = PB.PEOPLEBOOK_SET_ACTIVITY
        if len(ctx.text) >= 4:
            mongo_peoplebook.update_one({'username': ctx.user_object['username']}, {'$set': {'activity': ctx.text}})
            ctx.expected_intent = PB.PEOPLEBOOK_SET_TOPICS if within else PB.PEOPLEBOOK_SHOW_PROFILE
            ctx.response = 'Здорово!'
        else:
            ctx.response = 'Кажется, этого маловато. Надо повторить.'
            ctx.expected_intent = PB.PEOPLEBOOK_SET_ACTIVITY
    elif ctx.last_expected_inent == PB.PEOPLEBOOK_SET_TOPICS:
        ctx.intent = PB.PEOPLEBOOK_SET_TOPICS
        if len(ctx.text) >= 4:
            mongo_peoplebook.update_one({'username': ctx.user_object['username']}, {'$set': {'topics': ctx.text}})
            ctx.response = 'Интересненько.'
            ctx.expected_intent = PB.PEOPLEBOOK_SET_PHOTO if within else PB.PEOPLEBOOK_SHOW_PROFILE
        else:
            ctx.response = 'Попробуйте рассказать более развёрнуто.'
            ctx.expected_intent = PB.PEOPLEBOOK_SET_TOPICS
    elif ctx.last_expected_inent == PB.PEOPLEBOOK_SET_PHOTO:
        ctx.intent = PB.PEOPLEBOOK_SET_PHOTO
        # todo: validate the photo
        mongo_peoplebook.update_one({'username': ctx.user_object['username']}, {'$set': {'photo': ctx.text.strip()}})
        ctx.response = 'Отлично'
        ctx.expected_intent = PB.PEOPLEBOOK_SET_CONTACTS if within else PB.PEOPLEBOOK_SHOW_PROFILE
    elif ctx.last_expected_inent == PB.PEOPLEBOOK_SET_CONTACTS:
        ctx.intent = PB.PEOPLEBOOK_SET_CONTACTS
        mongo_peoplebook.update_one({'username': ctx.user_object['username']}, {'$set': {'contacts': ctx.text}})
        if within:
            ctx.response = 'Отлично! Ваш профайл создан.'
            ctx.the_update = {'$unset': {PB.CREATING_PB_PROFILE: False}}
        ctx.expected_intent = PB.PEOPLEBOOK_SHOW_PROFILE
    for k, v in {
        '/set_pb_name': PB.PEOPLEBOOK_SET_FIRST_NAME,
        '/set_pb_surname': PB.PEOPLEBOOK_SET_LAST_NAME,
        '/set_pb_activity': PB.PEOPLEBOOK_SET_ACTIVITY,
        '/set_pb_topics': PB.PEOPLEBOOK_SET_TOPICS,
        '/set_pb_photo': PB.PEOPLEBOOK_SET_PHOTO,
        '/set_pb_contacts': PB.PEOPLEBOOK_SET_CONTACTS
    }.items():
        if ctx.text == k:
            the_profile = mongo_peoplebook.find_one({'username': ctx.user_object['username']})
            if the_profile is None:
                ctx.intent = PB.PEOPLEBOOK_GET_FAIL
                ctx.response = 'У вас ещё нет профиля в пиплбуке. Завести?'
            else:
                ctx.expected_intent = v
                ctx.intent = v
            break
        # todo: parse the case with command + target text
    # then, prepare the response
    if ctx.expected_intent is not None:
        if ctx.response is None:
            ctx.response = ''
    if ctx.expected_intent == PB.PEOPLEBOOK_SET_FIRST_NAME:
        ctx.response = ctx.response + '\nПожалуйста, введите ваше имя (без фамилии).'
    elif ctx.expected_intent == PB.PEOPLEBOOK_SET_LAST_NAME:
        ctx.response = ctx.response + '\nПожалуйста, назвовите вашу фамилию.'
    elif ctx.expected_intent == PB.PEOPLEBOOK_SET_ACTIVITY:
        ctx.response = ctx.response + '\nРасскажите, чем вы занимаетесь. ' \
                                      'Работа, предыдущая работа, сайдпроджекты, ресёрч. ' \
                                      'Лучше развёрнуто, в несколько предложений. '
    elif ctx.expected_intent == PB.PEOPLEBOOK_SET_TOPICS:
        ctx.response = ctx.response + '\nПро что вас можно расспросить, о чём вы знаете больше других? ' \
                                      'Это могут быть города, хобби, мероприятия, необычный опыт.'
    elif ctx.expected_intent == PB.PEOPLEBOOK_SET_PHOTO:
        ctx.response = ctx.response + '\nДайте ссылку на фото, по которому вас проще всего будет найти. ' \
                                      'Важно, чтобы лицо было хорошо видно. ' \
                                      '\nСсылка должна быть не на страничку с фото, а на файл ' \
                                      '(с расширением типа .png, .jpg и т.п. в конце ссылки).' \
                                      '\nЕсли у вас нет ссылки, можно загрузить фото, например, на vfl.ru.'
    elif ctx.expected_intent == PB.PEOPLEBOOK_SET_CONTACTS:
        ctx.response = ctx.response + '\nЕсли хотите, можете оставить контакты в соцсетях: ' \
                                      'телеграм, инстаграм, линкедин, фб, вк, почта.'
    elif ctx.expected_intent == PB.PEOPLEBOOK_SHOW_PROFILE:
        the_profile = mongo_peoplebook.find_one({'username': ctx.user_object['username']})
        ctx.response = ctx.response + '\nТак выглядит ваш профиль:\n' + peoplebook.render_text_profile(the_profile)
    if ctx.response is not None:
        ctx.response = ctx.response.strip()
    return ctx


def try_membership_management(ctx: Context):
    if not is_member(ctx.user_object):
        return ctx
    # todo: add guest management
    if not is_admin(ctx.user_object):
        return ctx
    # member management
    if re.match('(добавь|добавить) (члена|членов)', ctx.text_normalized):
        ctx.intent = 'MEMBER_ADD_INIT'
        ctx.response = 'Введите телеграмовский логин/логины новых членов через пробел.'
    elif ctx.last_intent == 'MEMBER_ADD_INIT':
        ctx.intent = 'MEMBER_ADD_COMPLETE'
        logins = [c.strip(',').strip('@').lower() for c in ctx.text.split()]
        resp = 'Вот что получилось:'
        for login in logins:
            if not re.match('[a-z0-9_]{5,}', login):
                resp = resp + '\nСлово "{}" не очень похоже на логин, пропускаю.'.format(login)
                continue
            existing = mongo_membership.find_one({'username': login, 'is_member': True})
            if existing is None:
                mongo_membership.update_one({'username': login}, {'$set': {'is_member': True}}, upsert=True)
                resp = resp + '\n@{} успешно добавлен(а) список членов.'.format(login)
            else:
                resp = resp + '\n@{} уже является членом клуба.'.format(login)
        ctx.response = resp
    return ctx


def try_coffee_management(ctx: Context):
    if ctx.text == TAKE_PART:
        ctx.the_update = {"$set": {'wants_next_coffee': True}}
        ctx.response = 'Окей, на следующей неделе вы будете участвовать в random coffee!'
        ctx.intent = 'TAKE_PART'
    elif ctx.text == NOT_TAKE_PART:
        ctx.the_update = {"$set": {'wants_next_coffee': False}}
        ctx.response = 'Окей, на следующей неделе вы не будете участвовать в random coffee!'
        ctx.intent = 'NOT_TAKE_PART'
    # todo: manage coffee suggests here
    return ctx


@bot.message_handler(func=lambda message: True)
def process_message(msg):
    uo = get_or_insert_user(msg.from_user)
    user_id = msg.chat.id
    LoggedMessage(text=msg.text, user_id=user_id, from_user=True).save()
    ctx = Context(text=msg.text, user_object=uo)

    for handler in [
        try_event_creation,
        try_event_usage,
        try_peoplebook_management,
        try_coffee_management,
        try_membership_management
    ]:
        ctx = handler(ctx)
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
    mongo_users.update_one({'tg_id': msg.from_user.id}, ctx.make_update())
    user_object = get_or_insert_user(tg_uid=msg.from_user.id)
    markup = types.ReplyKeyboardMarkup()
    markup.add(TAKE_PART if not user_object.get('wants_next_coffee') else NOT_TAKE_PART)

    LoggedMessage(text=ctx.response, user_id=user_id, from_user=False).save()

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
