import pymongo

from datetime import datetime, date
from typing import Callable

from utils.database import Database
from utils.dialogue_management import Context

from scenarios.coffee_match_maker import generate_good_pairs

from config import ADMIN_UID

import time

TAKE_PART = 'Участвовать в следующем кофе'
NOT_TAKE_PART = 'Не участвовать в следующем кофе'


def get_coffee_score(text):
    text = text.lower()
    if 'участ' in text and ('кофе' in text or 'coffee' in text):
        if 'не ' in text or 'отказ' in text:
            return -1
        return 1
    return 0


def daily_random_coffee(database: Database, sender: Callable, force_restart=False):
    if force_restart or datetime.today().weekday() == 5:  # on saturday, we recalculate the matches
        user_to_matches = generate_good_pairs(database)
        database.mongo_coffee_pairs.insert_one({'date': str(datetime.utcnow()), 'matches': user_to_matches})

    last_matches = database.mongo_coffee_pairs.find_one({}, sort=[('_id', pymongo.DESCENDING)])

    if last_matches is None:
        sender(
            text='я не нашёл матчей, посмотри логи плз',
            user_id=ADMIN_UID, database=database, notify_on_error=False
        )
    else:
        str_uid_to_username = {str(uo['tg_id']): uo['username'] for uo in database.mongo_users.find({})}
        converted_matches = {
            str_uid_to_username[key]: [str_uid_to_username[value] for value in values]
            for key, values in last_matches['matches'].items()
        }
        sender(
            text='вот какие матчи сегодня: {}'.format(converted_matches),
            user_id=ADMIN_UID, database=database, notify_on_error=False
        )
        for username, matches in converted_matches.items():
            user_obj = database.mongo_users.find_one({'username': username})
            if user_obj is None:
                sender(
                    text='юзер {} не был найден!'.format(username),
                    user_id=ADMIN_UID, database=database, notify_on_error=False
                )
            else:
                remind_about_coffee(user_obj, matches, database=database, sender=sender, force_restart=force_restart)
                time.sleep(0.5)


def remind_about_coffee(user_obj, matches, database: Database, sender: Callable, force_restart=False):
    user_id = user_obj['tg_id']
    match_texts = []
    for m in matches:
        in_pb = database.mongo_peoplebook.find_one({'username': m})
        if in_pb:
            match_texts.append('@{} (<a href="http://kv-peoplebook.herokuapp.com/person/{}">пиплбук</a>)'.format(m, m))
        else:
            match_texts.append('@{}'.format(m))

    with_whom = 'с {}'.format(match_texts[0])
    for next_match in match_texts[1:]:
        with_whom = with_whom + ' и c {}'.format(next_match)

    response = None
    if force_restart or datetime.today().weekday() == 5:  # saturday
        response = 'На этой неделе вы пьёте кофе {}.\nЕсли вы есть, будьте первыми!'.format(with_whom)
    elif datetime.today().weekday() == 4:  # friday
        response = 'На этой неделе вы, наверное, пили кофе {}.\nКак оно прошло?'.format(with_whom)
        # todo: remember the feedback (with expected_intent)
    elif datetime.today().weekday() == 0:  # monday
        response = 'Напоминаю, что на этой неделе вы пьёте кофе {}.\n'.format(with_whom) + \
            '\nНадеюсь, вы уже договорились о встрече?	\U0001f609' + \
            '\n(если в минувшую субботу пришло несколько оповещений о кофе, то действительно только последнее)'
    if response is not None:
        user_in_pb = database.mongo_peoplebook.find_one({'username': user_obj.get('username')})
        if not user_in_pb:
            response = response + '\n\nКстати, кажется, вас нет в пиплбуке, а жаль: ' \
                                  'с пиплбуком даже незнакомому собеседнику проще будет начать с вами общение.' \
                                  '\nПожалуйста, когда будет время, напишите мне "мой пиплбук" ' \
                                  'и заполните свою страничку.\nЕсли вы есть, будьте первыми!'
        # avoiding circular imports
        from scenarios.suggests import make_standard_suggests
        suggests = make_standard_suggests(database=database, user_object=user_obj)
        sender(user_id=user_id, text=response, database=database, suggests=suggests,
               reset_intent=True, intent='coffee_push')


def try_coffee_management(ctx: Context, database: Database):
    if not database.is_at_least_guest(user_object=ctx.user_object):
        return ctx
    coffee_score = get_coffee_score(ctx.text)
    if ctx.text == TAKE_PART or coffee_score == 1:
        if ctx.user_object.get('username') is None:
            ctx.intent = 'COFFEE_NO_USERNAME'
            ctx.response = 'Чтобы участвовать в random coffee, нужно иметь имя пользователя в Телеграме.' \
                           '\nПожалуйста, создайте себе юзернейм (ТГ > настройки > изменить профиль > ' \
                           'имя пользователя) и попробуйте снова.\nВ случае ошибки напишите @cointegrated.' \
                           '\nЕсли вы есть, будьте первыми!'
            return ctx
        ctx.the_update = {"$set": {'wants_next_coffee': True}}
        ctx.response = 'Окей, на следующей неделе вы будете участвовать в random coffee!'
        ctx.intent = 'TAKE_PART'
    elif ctx.text == NOT_TAKE_PART or coffee_score == -1:
        ctx.the_update = {"$set": {'wants_next_coffee': False}}
        ctx.response = 'Окей, на следующей неделе вы не будете участвовать в random coffee!'
        ctx.intent = 'NOT_TAKE_PART'
    return ctx
