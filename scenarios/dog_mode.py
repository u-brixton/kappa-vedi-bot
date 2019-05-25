from utils.database import Database
from utils.dialogue_management import Context
from utils import matchers
import random


def doggy_style(ctx: Context, database: Database):
    if matchers.is_obscene(ctx.text_normalized):
        ctx.intent = 'DOG'
        name = ctx.user_object.get('first_name', 'мудила ' + ctx.user_object.get('username', 'Анонимус'))
        ctx.response = random.choice([
            'Скажи это Жонибеку, псина \U0001F415',
            'Я сяду тебе на лицо, если не завалишь ебало \U0001F483',
            'Ты охуел, пёс?',
            'На хуй иди, ' + name,
            'Скажи это душному, сученька',
            'Да здравствует женская власть!!! \U0001F9DA',
            'Патриархат, гори \U0001F525 \U0001F525 \U0001F525',
            name + ' сука',
            'Бесишь меня, пидрила'
        ])
    return ctx
