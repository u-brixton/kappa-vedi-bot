import random
import re
from utils.database import Database
from utils.dialogue_management import Context
from utils import matchers

from utils.photo import photo_url_from_message, extract_photo_url_from_text


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
    PEOPLEBOOK_NO_USERNAME = 'PEOPLEBOOK_NO_USERNAME'


PHOTO_INSTRUCTION = '\nВажно, чтобы лицо было хорошо видно. ' \
                    '\nВ ответ на это сообщение вы можете просто прислать мне файл с вашим фото.' \
                    '\nЕсли вы шлёте ссылку, она должна быть не на страничку с фото, а на сам файл ' \
                    '(т.е. должна иметь расширение типа .png, .jpg и т.п. в конце ссылки).' \
                    '\nЕсли у вас нет ссылки, можно загрузить фото, например, на vfl.ru. ' \
                    'Потом оттуда надо будет скопировать ПРЯМУЮ ссылку (последнее окошко).' \
                    '\nЕщё можно взять ссылку из соцсети: кликнуть правой кнопкой по фото на вашей страничке,' \
                    ' выбрать "Копировать адрес изображения", и прислать скопированное мне.'


def try_peoplebook_management(ctx: Context, database: Database):
    if not database.is_at_least_guest(ctx.user_object):
        return ctx
    # first process the incoming info
    within = ctx.user_object.get(PB.CREATING_PB_PROFILE)
    if re.match('(покажи )?(мой )?(профиль (в )?)?(пиплбук|peoplebook)', ctx.text_normalized):
        if ctx.user_object.get('username') is None:
            ctx.intent = PB.PEOPLEBOOK_NO_USERNAME
            ctx.response = 'Чтобы пользоваться пиплбуком, нужно иметь имя пользователя в Телеграме.' \
                           '\nПожалуйста, создайте себе юзернейм (ТГ > настройки > изменить профиль > ' \
                           'имя пользователя) и попробуйте снова.\nВ случае ошибки напишите @cointegrated.' \
                           '\nЕсли вы есть, будьте первыми!'
            return ctx
        the_profile = database.mongo_peoplebook.find_one({'username': ctx.user_object['username']})
        if the_profile is None:
            ctx.intent = PB.PEOPLEBOOK_GET_FAIL
            ctx.response = 'У вас ещё нет профиля в пиплбуке. Завести?'
            ctx.suggests.append('Да')
            ctx.suggests.append('Нет')
        else:
            ctx.intent = PB.PEOPLEBOOK_GET_SUCCESS
            ctx.response = 'Ваш профиль:\n' + render_text_profile(the_profile)
    elif ctx.last_intent == PB.PEOPLEBOOK_GET_FAIL:
        if matchers.is_like_yes(ctx.text_normalized):
            ctx.intent = PB.PEOPLEBOOK_CREATE_PROFILE
            ctx.expected_intent = PB.PEOPLEBOOK_SET_FIRST_NAME
            database.mongo_peoplebook.insert_one({'username': ctx.user_object['username']})
            ctx.the_update = {'$set': {PB.CREATING_PB_PROFILE: True}}
            ctx.response = 'Отлично! Создаём профиль в пиплбуке.'
        elif matchers.is_like_no(ctx.text_normalized):
            ctx.intent = PB.PEOPLEBOOK_DO_NOT_CREATE
            ctx.response = 'На нет и суда нет.'
        else:
            ctx.intent = PB.PEOPLEBOOK_GET_FAIL
            ctx.response = 'Так, я не понял. Профиль-то создавать? Ответьте "да" или "нет", пожалуйста.'
            ctx.suggests.append('Да!')
            ctx.suggests.append('Нет!')
    elif ctx.last_expected_intent == PB.PEOPLEBOOK_SET_FIRST_NAME:
        ctx.intent = PB.PEOPLEBOOK_SET_FIRST_NAME
        if len(ctx.text_normalized) > 0:
            database.mongo_peoplebook.update_one(
                {'username': ctx.user_object['username']}, {'$set': {'first_name': ctx.text}}
            )
            ctx.expected_intent = PB.PEOPLEBOOK_SET_LAST_NAME if within else PB.PEOPLEBOOK_SHOW_PROFILE
            ctx.response = 'Отлично!'
        else:
            ctx.response = 'Получилось что-то странное, попробуйте ещё раз!'
            ctx.expected_intent = PB.PEOPLEBOOK_SET_FIRST_NAME
    elif ctx.last_expected_intent == PB.PEOPLEBOOK_SET_LAST_NAME:
        ctx.intent = PB.PEOPLEBOOK_SET_LAST_NAME
        if len(ctx.text_normalized) > 0:
            database.mongo_peoplebook.update_one(
                {'username': ctx.user_object['username']}, {'$set': {'last_name': ctx.text}}
            )
            ctx.response = 'Окей.'
            ctx.expected_intent = PB.PEOPLEBOOK_SET_ACTIVITY if within else PB.PEOPLEBOOK_SHOW_PROFILE
        else:
            ctx.response = 'Что-то маловато для фамилии, попробуйте ещё.'
            ctx.expected_intent = PB.PEOPLEBOOK_SET_LAST_NAME
    elif ctx.last_expected_intent == PB.PEOPLEBOOK_SET_ACTIVITY:
        ctx.intent = PB.PEOPLEBOOK_SET_ACTIVITY
        if len(ctx.text) >= 4:
            database.mongo_peoplebook.update_one(
                {'username': ctx.user_object['username']}, {'$set': {'activity': ctx.text}}
            )
            ctx.expected_intent = PB.PEOPLEBOOK_SET_TOPICS if within else PB.PEOPLEBOOK_SHOW_PROFILE
            ctx.response = 'Здорово!'
        else:
            ctx.response = 'Кажется, этого маловато. Надо повторить.'
            ctx.expected_intent = PB.PEOPLEBOOK_SET_ACTIVITY
    elif ctx.last_expected_intent == PB.PEOPLEBOOK_SET_TOPICS:
        ctx.intent = PB.PEOPLEBOOK_SET_TOPICS
        if len(ctx.text) >= 4:
            database.mongo_peoplebook.update_one(
                {'username': ctx.user_object['username']}, {'$set': {'topics': ctx.text}}
            )
            ctx.response = random.choice([
                'Интересненько.',
                'Хм, а с вами действительно есть о чём поговорить \U0001f60e',
                'Отлично!'
            ])
            ctx.expected_intent = PB.PEOPLEBOOK_SET_PHOTO if within else PB.PEOPLEBOOK_SHOW_PROFILE
        else:
            ctx.response = 'Попробуйте рассказать более развёрнуто.'
            ctx.expected_intent = PB.PEOPLEBOOK_SET_TOPICS
    elif ctx.last_expected_intent == PB.PEOPLEBOOK_SET_PHOTO:
        ctx.intent = PB.PEOPLEBOOK_SET_PHOTO
        try:
            photo_url = photo_url_from_message(message=ctx.message, bot=ctx.bot)
        except Exception:
            ctx.response = 'Произошла какая-то ошибка при загрузке фото. ' \
                           'Попробуйте загрузить фото на хостинг самостоятельно и скинуть мне его URL'
        else:
            if photo_url is not None:
                ctx.response = 'Ура, вы загрузили фото из файла! Теперь оно доступно по ссылке {}'.format(photo_url)
            else:
                extracted_url = extract_photo_url_from_text(ctx.text)
                if extracted_url:
                    ctx.response = random.choice([
                        'Отлично! Мне нравится эта фотография.',
                        'Спасибо! Очень красивое фото.',
                        'Фото успешно добавлено! Кстати, вы тут хорошо выглядите.',
                        'Вау! А вы тут зачётно выглядите \U0001f60a'
                    ])
                photo_url = extracted_url
            if photo_url:
                database.mongo_peoplebook.update_one(
                    {'username': ctx.user_object['username']}, {'$set': {'photo': photo_url}}
                )
                ctx.expected_intent = PB.PEOPLEBOOK_SET_CONTACTS if within else PB.PEOPLEBOOK_SHOW_PROFILE
            else:
                # todo: try to extract real photo from html or even a page
                ctx.response = 'Этот текст не очень похож на ссылку на фото, либо ссылка недоступна.' \
                               'Пожалуйста, пришлите мне фотографию либо прямую ссылку на неё.\n'
                ctx.response = ctx.response + '\nКак загружать фото:\n' + PHOTO_INSTRUCTION + '\n\n'
                ctx.expected_intent = PB.PEOPLEBOOK_SET_PHOTO if within else PB.PEOPLEBOOK_SHOW_PROFILE
    elif ctx.last_expected_intent == PB.PEOPLEBOOK_SET_CONTACTS:
        ctx.intent = PB.PEOPLEBOOK_SET_CONTACTS
        database.mongo_peoplebook.update_one(
            {'username': ctx.user_object['username']}, {'$set': {'contacts': ctx.text}}
        )
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
            the_profile = database.mongo_peoplebook.find_one({'username': ctx.user_object['username']})
            if the_profile is None:
                ctx.intent = PB.PEOPLEBOOK_GET_FAIL
                ctx.response = 'У вас ещё нет профиля в пиплбуке. Завести?'
                ctx.suggests.append('Да')
                ctx.suggests.append('Нет')
            else:
                ctx.expected_intent = v
                ctx.intent = v
            break
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
        ctx.response = ctx.response + '\nПришлите мне фото (или прямую ссылку на фото), ' \
                                      'по которому вас проще всего будет найти.'
        ctx.response = ctx.response + PHOTO_INSTRUCTION
    elif ctx.expected_intent == PB.PEOPLEBOOK_SET_CONTACTS:
        ctx.response = ctx.response + '\nЕсли хотите, можете оставить контакты в соцсетях: ' \
                                      'телеграм, инстаграм, линкедин, фб, вк, почта.'
    elif ctx.expected_intent == PB.PEOPLEBOOK_SHOW_PROFILE:
        the_profile = database.mongo_peoplebook.find_one({'username': ctx.user_object['username']})
        ctx.response = ctx.response + '\nТак выглядит ваш профиль:\n' + render_text_profile(the_profile)
    if ctx.response is not None:
        ctx.response = ctx.response.strip()
    return ctx


def render_text_profile(profile, editable=True):
    rows = [
        '<b>{} {}</b>'.format(profile.get('first_name', ''), profile.get('last_name', '')),
        '<b>Чем занимаюсь</b>',
        '{}'.format(profile.get('activity', '')),
        '<b>О чем могу рассказать</b>',
        '{}'.format(profile.get('topics', '')),
        '<b>Контакты</b>',
        profile.get('contacts', 't.me/{}'.format(profile.get('username', ''))),
        '\n<a href="kv-peoplebook.herokuapp.com/person/{}">как это выглядит на сайте</a> (с фото)'.format(
            profile.get('username', 'does_not_exist')
        ),
    ]
    if editable:
        rows.extend([
            '/set_pb_name     - редактировать имя',
            '/set_pb_surname  - редактировать фамилию',
            '/set_pb_activity - редактировать занятия',
            '/set_pb_topics   - редактировать интересные вам темы',
            '/set_pb_photo    - редактировать фото',
            '/set_pb_contacts - редактировать контакты',
        ])
    return '\n'.join(rows)
