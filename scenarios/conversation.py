from utils.database import Database
from utils.dialogue_management import Context

import random
import re


class Intents:
    OTHER = 'OTHER'
    UNAUTHORIZED = 'UNAUTHORIZED'


HELP = """Я бот, который умеет назначать random coffee.
Это значит, что я каждую субботу в 8 вечера выбираю вам в пару случайного члена клуба.
После этого у вас есть неделя, чтобы встретиться, выпить вместе кофе \U0001F375 и поговорить о жизни.
(Неделя считается до следующих выходных включительно.)

А ещё я умею приглашать гостей на встречи и обновлять странички в пиплбуке.
И я постоянно учусь новым вещам. Надеюсь, что вы тоже. \U0001f609
Если вы есть, будьте первыми!"""
HELP_UNAUTHORIZED = """Привет! Я бот Каппа Веди.
К сожалению, вас нет в списке знакомых мне пользователей.
Если вы гость встречи, попросите кого-то из членов клуба сделать для вас приглашение в боте.
Если вы член клуба, попросите Жонибека, Степана, Дашу, Альфию или Давида (@cointegrated) добавить вас в список членов.
В любом случае для авторизации понадобится ваш уникальный юзернейм в Телеграме.
Если вы есть, будьте первыми!"""


def try_conversation(ctx: Context, database: Database):
    if re.match('привет', ctx.text_normalized):
        ctx.intent = 'HELLO'
        ctx.response = random.choice([
            'Приветствую! \U0001f60a',
            'Дратути!\U0001f643',
            'Привет!',
            'Привет-привет',
            'Рад вас видеть!',
            'Здравствуйте, сударь! \U0001f60e'
        ])
    return ctx


def fallback(ctx: Context, database: Database):
    if not database.is_at_least_guest(ctx.user_object):
        ctx.intent = Intents.UNAUTHORIZED
        ctx.response = HELP_UNAUTHORIZED
    else:
        ctx.intent = Intents.OTHER
        ctx.response = HELP
    return ctx
