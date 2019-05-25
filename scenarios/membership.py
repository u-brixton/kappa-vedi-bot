
import re

from utils import matchers

from utils.database import Database
from utils.dialogue_management import Context


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
        logins = [matchers.normalize_username(c.strip(',').strip('@').lower()) for c in ctx.text.split()]
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
