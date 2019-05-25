

from utils.database import Database
from utils.dialogue_management import Context


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
