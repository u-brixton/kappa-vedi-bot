from typing import Callable

from utils.database import Database
from utils.dialogue_management import Context
from utils import matchers
import random
import re

from datetime import datetime, timedelta

PEOPLEBOOK_EVENT_ROOT = 'http://kv-peoplebook.herokuapp.com/event/'


class InvitationStatuses:
    NOT_SENT = 'NOT_SENT'
    ON_HOLD = 'ON_HOLD'
    ACCEPT = 'ACCEPT'
    REJECT = 'REJECT'

    @classmethod
    def translate(cls, status):
        d = {
            cls.NOT_SENT: 'приглашение пока не получено',
            cls.ON_HOLD: 'пока определяется',
            cls.ACCEPT: 'принял(а) приглашение',
            cls.REJECT: 'отклонил(а) приглашение',
        }
        return d.get(status, 'какой-то непонятный статус')


class EventIntents:
    INVITE = 'INVITE'
    DID_NOT_PARSE = 'DID_NOT_PARSE'
    ON_HOLD = 'ON_HOLD'
    ACCEPT = 'ACCEPT'
    REJECT = 'REJECT'
    NORMAL_REMINDER = 'NORMAL_REMINDER'


def render_full_event(ctx: Context, database: Database, the_event):
    response = format_event_description(the_event)
    the_participation = database.mongo_participations.find_one(
        {'username': ctx.user_object['username'], 'code': the_event['code']}
    )
    if the_participation is None or the_participation.get('status') != InvitationStatuses.ACCEPT:
        response = response + '\nВы не участвуете.\n /engage - участвовать'
    else:
        response = response + '\nВы участвуете.\n /unengage - отказаться от участия'
    if database.is_at_least_member(user_object=ctx.user_object):
        response = response + '\n /invite - пригласить гостя'
    if database.is_admin(user_object=ctx.user_object):
        response = response + EVENT_EDITION_COMMANDS
    return response


def make_invitation(invitation, database: Database):
    r = 'Здравствуйте! Вы были приглашены пользователем @{} на встречу Каппа Веди.\n'.format(invitation['invitor'])
    event_code = invitation.get('code', '')
    the_event = database.mongo_events.find_one({'code': event_code})
    if event_code == '' or the_event is None:
        return 'Я не смог найти встречу, напишите @cointegrated пожалуйста.', 'ERROR', []
    r = r + format_event_description(the_event)
    r = r + '\nВы сможете участвовать в этой встрече?'
    suggests = ['Да', 'Нет', 'Пока не знаю']
    intent = EventIntents.INVITE
    database.mongo_users.update_one({'username': invitation['username']}, {'$set': {'event_code': event_code}})
    return r, intent, suggests


def try_invitation(ctx: Context, database: Database):
    deferred_invitation = database.mongo_participations.find_one(
        {'username': ctx.username, 'status': InvitationStatuses.NOT_SENT}
    )
    if ctx.last_intent in {EventIntents.INVITE, EventIntents.DID_NOT_PARSE}:
        new_status = None
        event_code = ctx.user_object.get('event_code')
        if event_code is None:
            ctx.response = 'Почему-то не удалось получить код встречи, сообщите @cointegrated'
        elif matchers.is_like_yes(ctx.text_normalized):
            new_status = InvitationStatuses.ACCEPT
            ctx.intent = EventIntents.ACCEPT
            ctx.response = 'Ура! Я очень рад, что вы согласились прийти!'
            the_peoplebook = database.mongo_peoplebook.find_one({'username': ctx.username})
            if the_peoplebook is None:
                t = '\nЧтобы встреча прошла продуктивнее, пожалуйста, заполните свою страничку в ' \
                    + '<a href="{}{}">пиплбуке встречи</a>.'.format(PEOPLEBOOK_EVENT_ROOT, event_code) \
                    + '\nДля этого, когда будете готовы, напишите мне "мой пиплбук"' \
                    + ' и ответьте на пару вопросов о себе.'\
                    + '\nЕсли вы есть, будьте первыми!'
            else:
                t = '\nВозможно, вы хотите обновить свою страничку в ' \
                    + '<a href="{}{}">пиплбуке встречи</a>.'.format(PEOPLEBOOK_EVENT_ROOT, event_code) \
                    + '\nДля этого, когда будете готовы, напишите мне "мой пиплбук"' \
                    + ' и ответьте на пару вопросов о себе.' \
                    + '\nЕсли вы есть, будьте первыми!'
            ctx.response = ctx.response + t
            # todo: tell the details and remind about money
        elif matchers.is_like_no(ctx.text_normalized):
            new_status = InvitationStatuses.REJECT
            ctx.intent = EventIntents.REJECT
            ctx.response = 'Мне очень жаль, что у вас не получается. ' \
                           'Но, видимо, такова жизнь. Если вы есть, будте первыми!'
            # todo: ask why the user rejects it
        elif re.match('пока не знаю', ctx.text_normalized):
            new_status = InvitationStatuses.ON_HOLD
            ctx.intent = EventIntents.ON_HOLD
            ctx.response = 'Хорошо, я спрошу попозже ещё.'
        else:
            ctx.intent = EventIntents.DID_NOT_PARSE
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
        ctx.the_update = {'$set': {'event_code': deferred_invitation.get('code')}}
    return ctx


def try_event_usage(ctx: Context, database: Database):
    if not database.is_at_least_guest(ctx.user_object):
        return ctx
    event_code = ctx.user_object.get('event_code')
    if re.match('(най[тд]и|пока(жи|зать))( мои| все)? (встреч[уи]|событи[ея]|мероприяти[ея])', ctx.text_normalized):
        ctx.intent = 'EVENT_GET_LIST'
        all_events = list(database.mongo_events.find({}))
        #future_events = [
        #    e for e in all_events if datetime.strptime(e['date'], '%Y.%m.%d') + timedelta(days=1) > datetime.utcnow()
        #]
        # todo: filter future events if requested so
        if database.is_at_least_member(user_object=ctx.user_object):
            available_events = all_events
        else:
            available_events = [
                c['the_event'][0] for c in database.mongo_participations.aggregate([
                    {
                        '$match': {'username': ctx.username}
                    }, {
                        '$lookup': {
                            'from': 'events',
                            'localField': 'code',
                            'foreignField': 'code',
                            'as': 'the_event'
                        }
                    }
                ])
            ]
        if len(available_events) > 0:
            ctx.response = 'Найдены события:\n'
            for e in available_events:
                ctx.response = ctx.response + '/{}: "{}", {}\n'.format(e['code'], e['title'], e['date'])
                invitation = database.mongo_participations.find_one({'username': ctx.username, 'code': e['code']})
                if (invitation is None or 'status' not in invitation
                        or invitation['status'] == InvitationStatuses.REJECT):
                    status = 'Вы не участвуете'
                elif invitation['status'] in {InvitationStatuses.ON_HOLD, InvitationStatuses.NOT_SENT}:
                    status = 'Вы пока не решили, участвовать ли'
                elif invitation['status'] == InvitationStatuses.ACCEPT:
                    status = 'Вы участвуете'
                else:
                    status = 'Какой-то непонятный статус'
                ctx.response = ctx.response + '{}\n\n'.format(status)
            ctx.response = ctx.response + 'Кликните по нужной ссылке, чтобы выбрать встречу.'
        elif len(all_events) > 0:
            ctx.response = 'Доступных вам событий не найдено.'
        else:
            ctx.response = 'Событий не найдено'
    elif ctx.last_intent == 'EVENT_GET_LIST':
        event_code = ctx.text.lstrip('/')
        the_event = database.mongo_events.find_one({'code': event_code})
        if the_event is not None:
            ctx.intent = 'EVENT_CHOOSE_SUCCESS'
            ctx.the_update = {'$set': {'event_code': event_code}}
            ctx.response = render_full_event(ctx, database, the_event)
            if database.is_admin(ctx.user_object):
                ctx.suggests.append('Пригласить всех членов клуба')
    elif event_code is not None and (
            ctx.text == '/engage' or re.match('^(участвовать|принять участие)(в этой встрече)$', ctx.text_normalized)
    ):
        ctx.intent = 'EVENT_ENGAGE'
        database.mongo_participations.update_one(
            {'username': ctx.user_object['username'], 'code': event_code},
            {'$set': {'status': InvitationStatuses.ACCEPT}}, upsert=True
        )
        ctx.response = 'Теперь вы участвуете в мероприятии {}!'.format(event_code)
    elif event_code is not None and (
            ctx.text == '/unengage' or re.match('^(не участвовать|покинуть встречу)$', ctx.text_normalized)
    ):
        ctx.intent = 'EVENT_UNENGAGE'
        database.mongo_participations.update_one(
            {'username': ctx.user_object['username'], 'code': event_code},
            {'$set': {'status': InvitationStatuses.REJECT}}, upsert=True
        )
        ctx.response = 'Теперь вы не участвуете в мероприятии {}!'.format(event_code)
    elif event_code is not None and ctx.text == '/invite':
        ctx.intent = 'EVENT_INVITE'
        if database.is_at_least_member(user_object=ctx.user_object):
            ctx.expected_intent = 'EVENT_INVITE_LOGIN'
            ctx.response = 'Хорошо! Введите Telegram логин человека, которого хотите пригласить на встречу.'
        else:
            ctx.response = 'Вы не являетесь членом клуба, и поэтому не можете приглашать гостей. Сорян.'
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
                    {'$set': {'status': InvitationStatuses.NOT_SENT, 'invitor': ctx.user_object['username']}},
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


def sent_invitation_to_user(username, event_code, database: Database, sender: Callable):
    invitation = database.mongo_participations.find_one({'username': username, 'code': event_code})
    if invitation is None:
        return False
    text, intent, suggests = make_invitation(invitation=invitation, database=database)
    user_account = database.mongo_users.find_one({'username': username})
    if user_account is None:
        return False
    if sender(text=text, database=database, suggests=suggests, user_id=user_account['tg_id']):
        database.mongo_users.update_one(
            {'username': username},
            {'$set': {'last_intent': intent, 'event_code': event_code}}
        )
        return True
    else:
        return False


class EventCreationIntents:
    INIT = 'EVENT_CREATE_INIT'
    CANCEL = 'EVENT_CREATE_CANCEL'
    SET_TITLE = 'EVENT_CREATE_SET_TITLE'
    SET_CODE = 'EVENT_CREATE_SET_CODE'
    SET_DATE = 'EVENT_CREATE_SET_DATE'


def try_parse_date(text):
    try:
        return datetime.strptime(text, '%Y.%m.%d')
    except ValueError:
        return None
    except TypeError:
        return None


def try_event_creation(ctx: Context, database: Database):
    if not database.is_admin(ctx.user_object):
        return ctx
    event_code = ctx.user_object.get('event_code')
    if re.match('созда(ть|й) встречу', ctx.text_normalized):
        ctx.intent = EventCreationIntents.INIT
        ctx.expected_intent = EventCreationIntents.SET_TITLE
        ctx.response = 'Придумайте название встречи (например, Встреча Каппа Веди 27 апреля):'
        ctx.the_update = {'$set': {'event_to_create': {}}}
        ctx.suggests.append('Отменить создание встречи')
    elif re.match('отменить создание встречи', ctx.text_normalized):
        ctx.intent = EventCreationIntents.CANCEL
        ctx.response = 'Хорошо, пока не будем создавать встречу'
    elif ctx.last_expected_intent == EventCreationIntents.SET_TITLE:
        ctx.intent = EventCreationIntents.SET_TITLE
        if len(ctx.text_normalized) < 3:
            ctx.expected_intent = EventCreationIntents.SET_TITLE
            ctx.response = 'Это название слишком странное. Пожалуйста, попробуйте другое.'
        elif database.mongo_events.find_one({'title': ctx.text}) is not None:
            ctx.expected_intent = EventCreationIntents.SET_TITLE
            ctx.response = 'Такое название уже существует. Пожалуйста, попробуйте другое.'
        else:
            event_to_create = ctx.user_object.get('event_to_create', {})
            event_to_create['title'] = ctx.text
            ctx.the_update = {'$set': {'event_to_create': event_to_create}}
            ctx.response = (
                'Хорошо, назовём встречу "{}".'.format(ctx.text)
                + '\nТеперь придумайте код встречи из латинских букв и цифр '
                + '(например, april2019):'
            )
            ctx.expected_intent = EventCreationIntents.SET_CODE
        ctx.suggests.append('Отменить создание встречи')
    elif ctx.last_expected_intent == EventCreationIntents.SET_CODE:
        ctx.intent = EventCreationIntents.SET_CODE
        if len(ctx.text) < 3:
            ctx.expected_intent = EventCreationIntents.SET_CODE
            ctx.response = 'Этот код слишком короткий. Пожалуйста, попробуйте другой.'
        elif not re.match('^[a-z0-9_]+$', ctx.text):
            ctx.expected_intent = EventCreationIntents.SET_CODE
            ctx.response = 'Код должен состоять из цифр и латинских букв в нижнем регистре. ' \
                           'Пожалуйста, попробуйте ещё раз.'
        elif database.mongo_events.find_one({'code': ctx.text}) is not None:
            ctx.expected_intent = EventCreationIntents.SET_CODE
            ctx.response = 'Событие с таким кодом уже есть. Пожалуйста, придумайте другой код.'
        else:
            event_to_create = ctx.user_object.get('event_to_create', {})
            event_to_create['code'] = ctx.text
            ctx.the_update = {'$set': {'event_to_create': event_to_create}}
            ctx.response = (
                    'Хорошо, код встречи будет "{}". '.format(ctx.text)
                    + '\nТеперь введите дату встречи в формате ГГГГ.ММ.ДД:'
            )
            ctx.expected_intent = EventCreationIntents.SET_DATE
        ctx.suggests.append('Отменить создание встречи')
    elif ctx.last_expected_intent == EventCreationIntents.SET_DATE:
        ctx.intent = EventCreationIntents.SET_DATE
        if not re.match('^20\d\d\.[01]\d\.[0123]\d$', ctx.text):
            ctx.expected_intent = EventCreationIntents.SET_DATE
            ctx.response = 'Дата должна быть в формате ГГГГ.ММ.ДД (типа 2020.03.05). Попробуйте ещё раз!'
            ctx.suggests.append('Отменить создание встречи')
        elif try_parse_date(ctx.text) is None:
            ctx.expected_intent = EventCreationIntents.SET_DATE
            ctx.response = 'Не получилось разобрать такую дату. Попробуйте, пожалуйста, ещё раз.'
            ctx.suggests.append('Отменить создание встречи')
        elif try_parse_date(ctx.text) + timedelta(days=1) < datetime.utcnow():
            ctx.expected_intent = EventCreationIntents.SET_DATE
            ctx.response = 'Кажется, эта дата уже в прошлом. Попробуйте, пожалуйста, ввести дату из будущего.'
            ctx.suggests.append('Отменить создание встречи')
        else:
            event_to_create = ctx.user_object.get('event_to_create', {})
            event_to_create['date'] = ctx.text
            database.mongo_events.insert_one(event_to_create)
            ctx.the_update = {'$set': {'event_code': event_to_create['code']}}
            ctx.response = 'Хорошо, дата встречи будет "{}". '.format(ctx.text) + '\nВстреча успешно создана!'
            ctx.suggests.append('Пригласить всех членов клуба')
    elif event_code is not None:  # this event is context-independent, triggers at any time just by text
        if re.match('пригласить (всех|весь).*', ctx.text_normalized) or ctx.text == '/invite_everyone':
            ctx.intent = 'INVITE_EVERYONE'
            ctx.response = 'Действительно пригласить всех членов клуба на встречу {}?'.format(event_code)
            ctx.suggests.extend(['Да', 'Нет'])
        elif ctx.last_intent == 'INVITE_EVERYONE' and matchers.is_like_no(ctx.text_normalized):
            ctx.intent = 'INVITE_EVERYONE_NOT_CONFIRM'
            ctx.response = 'Ладно.'
        elif ctx.last_intent == 'INVITE_EVERYONE' and matchers.is_like_yes(ctx.text_normalized):
            ctx.intent = 'INVITE_EVERYONE_CONFIRM'
            r = 'Приглашаю всех членов клуба...\n'
            for member in database.mongo_membership.find({'is_member': True}):
                # todo: deduplicate the code with single-member invitation
                the_login = member['username']
                the_invitation = database.mongo_participations.find_one({'username': the_login, 'code': event_code})
                if the_invitation is not None:
                    status = 'приглашение уже было сделано'
                else:
                    database.mongo_participations.update_one(
                        {'username': the_login, 'code': event_code},
                        {'$set': {'status': InvitationStatuses.NOT_SENT, 'invitor': ctx.username}}, upsert=True
                    )
                    success = sent_invitation_to_user(
                        username=the_login, event_code=event_code, database=database, sender=ctx.sender
                    )
                    status = 'успех' if success else 'не получилось'
                r = r + '\n  @{}: {}'.format(member['username'], status)
            ctx.response = r
    return ctx


class EventField:
    def __init__(self, code: str, name: str, validator):
        self.code = code
        self.command = '/set_e_' + code
        self.intent = 'EVENT_EDIT_' + code.upper()
        self.name = name
        self.name_accs = matchers.inflect_first_word(self.name, 'accs')
        self.validator = validator

    def validate(self, text):
        if self.validator is None:
            return True
        elif isinstance(self.validator, str):
            return bool(re.match(self.validator, text))
        else:
            return bool(self.validator(text))


EVENT_FIELDS = [
    EventField(*r) for r in [
        ['title', 'название', '.{3,}'],
        ['date', 'дата', lambda text: (try_parse_date(text) is not None)],
        ['time', 'время', '.{3,}'],
        ['place', 'адрес', '.{3,}'],
        ['program', 'программа', '.{3,}'],
        ['cost', 'размер взноса', '.{3,}'],
        ['chat', 'чат встречи', '.{3,}'],
        ['materials', 'ссылка на архив материалов', '.{3,}'],
    ]
]

EVENT_FIELD_BY_COMMAND = {e.command: e for e in EVENT_FIELDS}
EVENT_FIELD_BY_INTENT = {e.intent: e for e in EVENT_FIELDS}

EVENT_EDITION_COMMANDS = '\n'.join(
    [""]
    + ['{} - задать {}'.format(e.command, e.name_accs) for e in EVENT_FIELDS]
    + [
        "/remove_event - удалить событие и отменить все приглашения",
        "/invite_everyone - пригласить всех членов клуба",
        "/invitation_statuses - посмотреть статусы приглашений"
    ]
)


def format_event_description(event_dict):
    result = 'Мероприятие:'
    for field in EVENT_FIELDS:
        if event_dict.get(field.code, '') != '':
            result = result + '\n\t<b>{}</b>: \t{}'.format(field.name, event_dict.get(field.code))
    result = result + '\n\t<b>пиплбук встречи</b>: <a href="{}{}">ссылка</a>\n'.format(
        PEOPLEBOOK_EVENT_ROOT, event_dict.get('code')
    )
    return result


def try_event_edition(ctx: Context, database: Database):
    if not database.is_admin(ctx.user_object):
        return ctx
    event_code = ctx.user_object.get('event_code')
    the_event = database.mongo_events.find_one({'code': event_code})
    if event_code is None:
        return ctx
    if ctx.text in EVENT_FIELD_BY_COMMAND:
        field: EventField = EVENT_FIELD_BY_COMMAND[ctx.text]
        ctx.intent = field.intent
        ctx.expected_intent = field.intent
        ctx.response = 'Пожалуйста, введите {} мероприятия.'.format(field.name_accs)
        ctx.suggests.append('Отменить редактирование события')
    elif ctx.text == 'Отменить редактирование события':
        ctx.intent = 'EVENT_EDIT_CANCEL'
        ctx.response = 'Ладно\n\n' + render_full_event(ctx, database, the_event)
    elif ctx.last_expected_intent in EVENT_FIELD_BY_INTENT:
        field: EventField = EVENT_FIELD_BY_INTENT[ctx.last_expected_intent]
        ctx.intent = ctx.last_expected_intent
        if field.validate(ctx.text):
            database.mongo_events.update_one({'code': event_code}, {'$set': {field.code: ctx.text}})
            the_event = database.mongo_events.find_one({'code': event_code})
            ctx.response = 'Вы успешно изменили {}!\n\n'.format(field.name_accs)
            ctx.response = ctx.response + render_full_event(ctx, database, the_event)
        else:
            ctx.expected_intent = field.intent
            ctx.response = 'Кажется, формат не подходит. Пожалуйста, введите {} ещё раз.'.format(field.name_accs)
            ctx.suggests.append('Отменить редактирование')
    elif ctx.text == '/invitation_statuses':
        ctx.intent = 'EVENT_GET_INVITATION_STATUSES'
        event_members = list(database.mongo_participations.find({'code': event_code}))
        if len(event_members) == 0:
            ctx.response = 'Пока в этой встрече совсем нет участников. Если вы есть, будьте первыми!!!'
        else:
            statuses = '\n'.join([
                '@{} - {}'.format(em['username'], InvitationStatuses.translate(em['status']))
                + ('' if 'invitor' not in em else ' (гость @{})'.format(em['invitor']))
                for em in event_members
            ])
            ctx.response = 'Вот какие статусы участников встречи {}\n{}'.format(event_code, statuses)
        ctx.response = ctx.response + '\n\n' + render_full_event(ctx, database, the_event)
    elif ctx.text == '/remove_event':
        ctx.intent = 'EVENT_REMOVE'
        ctx.expected_intent = 'EVENT_REMOVE_CONFIRM'
        ctx.response = 'Вы уверены, что хотите удалить событие "{}"? Это безвозвратно!'.format(the_event['title'])
        ctx.suggests.extend(['Да', 'Нет'])
    elif ctx.last_expected_intent == 'EVENT_REMOVE_CONFIRM':
        if matchers.is_like_yes(ctx.text_normalized):
            database.mongo_events.delete_one({'code': event_code})
            database.mongo_participations.delete_many({'code': event_code})
            ctx.the_update = {'$unset': {'event_code': ""}}
            ctx.intent = 'EVENT_REMOVE_CONFIRM'
            ctx.response = 'Хорошо. Событие "{}" было удалено.'.format(the_event['title'])
        elif matchers.is_like_no(ctx.text_normalized):
            ctx.intent = 'EVENT_REMOVE_NOT_CONFIRM'
            ctx.response = 'Ладно, не буду удалять это событие.'
    return ctx


def daily_event_management(database: Database, sender: Callable):
    all_users = {u['username']: u for u in database.mongo_users.find() if u['username'] is not None}
    # find all the future events
    future_events = []
    for e in database.mongo_events.find({}):
        days_to = (datetime.strptime('2019.05.25', '%Y.%m.%d') - datetime.utcnow()) / timedelta(days=1)
        if days_to >= 0:
            e['days_to'] = int(days_to)
            future_events.append(e)
    # find all open invitations for the future events
    for event in future_events:
        hold_invitations = database.mongo_participations.find(
            {'code': event['code'], 'status': InvitationStatuses.ON_HOLD}
        )
        not_sent_invitations = database.mongo_participations.find(
            {'code': event['code'], 'status': InvitationStatuses.NOT_SENT}
        )
        sure_invitations = database.mongo_participations.find(
            {'code': event['code'], 'status': InvitationStatuses.ACCEPT}
        )
        open_invitations = [
            inv for inv in (hold_invitations + not_sent_invitations)
            if inv['username'] in all_users  # if not, we just cannot send anything
        ]
        # for every open invitation, decide whether to remind (soon-ness -> reminder probability)
        for inv in open_invitations:
            if event['days_to'] > 7:
                remind_probability = 0.1
            elif event['days_to'] > 7:
                remind_probability = 0.25
            elif event['days_to'] > 3:
                remind_probability = 0.5
            else:
                remind_probability = 1
            if random.random() <= remind_probability:
                # todo: make a custom header (with days to event)
                sent_invitation_to_user(
                    username=inv['username'], event_code=event['code'], database=database, sender=sender
                )
        if event['days_to'] in {0, 5}:
            for invitation in sure_invitations:
                user_account = database.mongo_users.find_one({'username': invitation['username']})
                if user_account is None:
                    continue
                text = 'Здравствуйте, {}! Осталось всего {} дней до очередной встречи Каппа Веди\n'.format(
                    user_account.get('first_name', 'товарищ ' + user_account.get('username', 'Анонимус')),
                    event['days_to'] + 1
                )
                text = text + format_event_description(event)
                text = text + '\nСоветую вам полистать пиплбук встречи заранее, чтобы нетворкаться на ней эффективнее.'
                text = text + '\nЕсли вы есть, будьте первыми! \U0001f60e'
                intent = EventIntents.NORMAL_REMINDER
                suggests = []
                if sender(text=text, database=database, suggests=suggests, user_id=user_account['tg_id']):
                    database.mongo_users.update_one(
                        {'username': invitation['username']},
                        {'$set': {'last_intent': intent, 'event_code': invitation['code']}}
                    )
