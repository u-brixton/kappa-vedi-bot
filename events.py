from utils.database import Database
from utils.dialogue_management import Context

import matchers
import re

from datetime import datetime, timedelta


class INVITATION_STATUSES:
    NOT_SENT = 'NOT_SENT'
    ON_HOLD = 'ON_HOLD'
    ACCEPT = 'ACCEPT'
    REJECT = 'REJECT'


class EVENT_INTENTS:
    INVITE = 'INVITE'
    DID_NOT_PARSE = 'DID_NOT_PARSE'
    ON_HOLD = 'ON_HOLD'
    ACCEPT = 'ACCEPT'
    REJECT = 'REJECT'


def format_event_description(event_dict):
    result = 'Мероприятие:'
    for key, title in [
        ['title', 'название'],
        ['date', 'дата'],
        ['time', 'время'],
        ['place', 'место'],
        ['program', 'программа'],
        ['cost', 'взнос'],
        ['chat', 'чат'],
    ]:
        if key in event_dict:
            result = result + '\n\t{}: \t{}'.format(title, event_dict.get(key))
    # todo: compile the link to the peoplebook
    result = result + '\n'
    return result


def make_invitation(invitation, database: Database):
    r = 'Здравствуйте! Вы были приглашены пользователем @{} на встречу Каппа Веди.\n'.format(invitation['invitor'])
    event_code = invitation.get('code', '')
    the_event = database.mongo_events.find_one({'code': event_code})
    if event_code == '' or the_event is None:
        return 'Я не смог найти встречу, напишите @cointegrated пожалуйста.', 'ERROR', []
    r = r + format_event_description(the_event)
    r = r + '\nВы сможете участвовать в этой встрече?'
    suggests = ['Да', 'Нет', 'Пока не знаю']
    intent = EVENT_INTENTS.INVITE
    database.mongo_users.update_one({'username': invitation['username']}, {'$set': {'event_code': event_code}})
    return r, intent, suggests


def try_invitation(ctx: Context, database: Database):
    deferred_invitation = database.mongo_participations.find_one(
        {'username': ctx.username, 'status': INVITATION_STATUSES.NOT_SENT}
    )
    if ctx.last_intent in {EVENT_INTENTS.INVITE, EVENT_INTENTS.DID_NOT_PARSE}:
        new_status = None
        event_code = ctx.user_object.get('event_code')
        if event_code is None:
            ctx.response = 'Почему-то не удалось получить код встречи, сообщите @cointegrated'
        elif matchers.is_like_yes(ctx.text_normalized):
            new_status = INVITATION_STATUSES.ACCEPT
            ctx.intent = EVENT_INTENTS.ACCEPT
            ctx.response = 'Ура! Я очень рад, что вы согласились прийти!'
            # todo: tell the details and remind about money and peoplebook
        elif matchers.is_like_no(ctx.text_normalized):
            new_status = INVITATION_STATUSES.REJECT
            ctx.intent = EVENT_INTENTS.REJECT
            ctx.response = 'Мне очень жаль, что у вас не получается. ' \
                           'Но, видимо, такова жизнь. Если вы есть, будте первыми!'
            # todo: ask why the user rejects it
        elif re.match('пока не знаю', ctx.text_normalized):
            new_status = INVITATION_STATUSES.ON_HOLD
            ctx.intent = EVENT_INTENTS.ON_HOLD
            ctx.response = 'Хорошо, я спрошу попозже ещё.'
            # todo: reask again
        else:
            ctx.intent = EVENT_INTENTS.DID_NOT_PARSE
            ctx.response = 'Я не понял. Ответьте, пожалуйста, на приглашение: "Да", "Нет", или "Пока не знаю".'
            ctx.suggests.extend(['Да', 'Нет', 'Пока не знаю'])
        if new_status is not None:
            database.mongo_participations.update_one(
                {'username': ctx.username, 'code': event_code},
                {'$set': {'status': new_status}}
            )
    elif deferred_invitation is not None:
        resp, intent, suggests = make_invitation(deferred_invitation, database=database)
        ctx.response = resp
        ctx.intent = intent
        ctx.suggests.extend(suggests)
    return ctx


def try_event_usage(ctx: Context, database: Database):
    if not database.is_at_least_guest(ctx.user_object):
        return ctx
    if re.match('(най[тд]и|пока(жи|зать))( мои| все)? (встреч[уи]|событи[ея]|мероприяти[ея])', ctx.text_normalized):
        ctx.intent = 'EVENT_GET_LIST'
        all_events = database.mongo_events.find({})
        future_events = [
            e for e in all_events if datetime.strptime(e['date'], '%Y.%m.%d') + timedelta(days=1) > datetime.utcnow()
        ]
        if len(future_events) > 0:
            ctx.response = 'Найдены предстоящие события:\n'
            for e in future_events:
                ctx.response = ctx.response + '/{}: "{}", {}\n'.format(e['code'], e['title'], e['date'])
        else:
            ctx.response = 'Предстоящих событий не найдено'
    elif ctx.last_intent == 'EVENT_GET_LIST':
        event_code = ctx.text.lstrip('/')
        the_event = database.mongo_events.find_one({'code': event_code})
        if the_event is not None:
            ctx.intent = 'EVENT_CHOOSE_SUCCESS'
            ctx.the_update = {'$set': {'event_code': event_code}}
            ctx.response = 'Событие "{}" {}'.format(the_event['title'], the_event['date'])
            # todo: check if the user participates
            the_participation = database.mongo_participations.find_one(
                {'username': ctx.user_object['username'], 'code': the_event['code']}
            )
            if the_participation is None or the_participation.get('status') != INVITATION_STATUSES.ACCEPT:
                ctx.response = ctx.response + '\n /engage - участвовать'
            else:
                ctx.response = ctx.response + '\n /unengage - отказаться от участия'
                ctx.response = ctx.response + '\n /invite - пригласить гостя'
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
            database.mongo_participations.update_one(
                {'username': ctx.user_object['username'], 'code': event_code},
                {'$set': {'status': INVITATION_STATUSES.ACCEPT}}, upsert=True
            )
            ctx.response = 'Теперь вы участвуете в мероприятии {}!'.format(event_code)
    elif ctx.last_intent == 'EVENT_CHOOSE_SUCCESS' and ctx.text == '/unengage':
        ctx.intent = 'EVENT_UNENGAGE'
        event_code = ctx.user_object.get('event_code')
        if event_code is None:
            ctx.response = 'почему-то не удалось получить код события, сообщите @cointegrated'
        else:
            database.mongo_participations.update_one(
                {'username': ctx.user_object['username'], 'code': event_code},
                {'$set': {'status': INVITATION_STATUSES.REJECT}}, upsert=True
            )
            ctx.response = 'Теперь вы не участвуете в мероприятии {}!'.format(event_code)
    elif ctx.user_object.get('event_code') is not None and ctx.text == '/invite':
        ctx.intent = 'EVENT_INVITE'
        ctx.expected_intent = 'EVENT_INVITE_LOGIN'
        ctx.response = 'Хорошо! Введите Telegram логин человека, которого хотите пригласить на встречу.'
    elif ctx.last_expected_intent == 'EVENT_INVITE_LOGIN':
        ctx.intent = 'EVENT_INVITE_LOGIN'
        the_login = ctx.text.strip().strip('@').lower()
        event_code = ctx.user_object.get('event_code')
        if event_code is None:
            ctx.response = 'Почему-то не удалось получить код события, сообщите @cointegrated'
        elif not matchers.is_like_telegram_login(the_login):
            f = 'Текст "{}" не похож на логин в телеграме. Если хотите попробовать снова, нажмите /invite опять.'
            ctx.response = f.format(the_login)
        else:
            existing_membership = database.mongo_membership.find_one({'username': the_login})
            existing_invitation = database.mongo_participations.find_one({'username': the_login, 'code': event_code})
            if existing_invitation is not None:
                ctx.response = 'Пользователь @{} уже получал приглашение на эту встречу!'.format(the_login)
            else:
                user_account = database.mongo_users.find_one({'username': the_login})
                never_used_this_bot = user_account is None
                if existing_membership is None:
                    database.mongo_membership.update_one(
                        {'username': the_login}, {'$set': {'is_guest': True}}, upsert=True
                    )
                database.mongo_participations.update_one(
                    {'username': the_login, 'code': event_code},
                    {'$set': {'status': INVITATION_STATUSES.NOT_SENT, 'invitor': ctx.user_object['username']}},
                    upsert=True
                )
                r = 'Юзер @{} был добавлен в список участников встречи!'.format(the_login)
                if never_used_this_bot:
                    r = r + '\nПередайте ему/ей ссылку на меня (@kappa_vedi_bot), ' \
                            'чтобы подтвердить участие и заполнить пиплбук (увы, бот не может писать первым).'
                else:
                    sent_invitation_to_user(the_login, event_code, database, ctx.sender)
                ctx.response = r
    return ctx


def sent_invitation_to_user(username, event_code, database: Database, sender):
    invitation = database.mongo_participations.find_one({'username': username, 'code': event_code})
    text, intent, suggests = make_invitation(invitation=invitation, database=database)
    user_account = database.mongo_users.find_one({'username': username})
    if sender(text=text, database=database, suggests=suggests, user_id=user_account['tg_id']):
        database.mongo_users.update_one({'username': username}, {'$set': {'last_intent': intent}})
        return True
    else:
        return False


def try_event_creation(ctx: Context, database: Database):
    if not database.is_admin(ctx.user_object):
        return ctx
    if re.match('созда(ть|й) встречу', ctx.text_normalized):
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
        database.mongo_events.insert_one(event_to_create)
        ctx.suggests.append('Пригласить всех членов клуба')
    elif ctx.last_intent == 'EVENT_CREATE_SET_DATE':
        if re.match('пригласить всех.*', ctx.text_normalized):
            event_to_create = ctx.user_object.get('event_to_create', {})
            ctx.intent = 'INVITE_EVERYONE'
            r = 'Приглашаю всех членов клуба...\n'
            for member in database.mongo_membership.find({'is_member': True}):
                # todo: deduplicate with single-member invitation
                the_login = member['username']
                event_code = event_to_create['code']
                the_invitation = database.mongo_participations.find_one({'username': the_login, 'code': event_code})
                if the_invitation is not None:
                    status = 'приглашение уже было сделано'
                else:
                    database.mongo_participations.update_one(
                        {'username': the_login, 'code': event_code},
                        {'$set': {'status': INVITATION_STATUSES.ACCEPT, 'invitor': ctx.username}}, upsert=True
                    )
                    success = sent_invitation_to_user(
                        username=the_login, event_code=event_code, database=database, sender=ctx.sender
                    )
                    status = 'успех' if success else 'не получилось'
                r = r + '\n  @{}: {}'.format(member['username'], status)
            ctx.response = r
    return ctx