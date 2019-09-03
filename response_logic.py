import logging


from utils.database import Database, LoggedMessage, get_or_insert_user
from utils.dialogue_management import Context
from utils.messaging import BaseSender

from scenarios.events import try_invitation, try_event_usage, try_event_creation, try_event_edition
from scenarios.peoplebook import try_peoplebook_management
from scenarios.conversation import try_conversation, fallback
from scenarios.dog_mode import doggy_style
from scenarios.push import try_queued_messages
from scenarios.membership import try_membership_management
from scenarios.coffee import try_coffee_management
from scenarios.suggests import make_standard_suggests

PROCESSED_MESSAGES = set()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def respond(message, database: Database, sender: BaseSender, bot=None):
    # todo: make it less dependent on telebot Message class structure
    logger.info('Got message {} with type {} and text {}'.format(
        message.message_id, message.content_type, message.text
    ))
    if message.message_id in PROCESSED_MESSAGES:
        return
    PROCESSED_MESSAGES.add(message.message_id)

    if message.chat.type != 'private':
        print(message.chat)
        if not message.from_user or not message.chat.id:
            return
        uo = get_or_insert_user(message.from_user, database=database)
        if not uo.get('username'):
            return
        user_filter = {'username': uo['username']}
        if message.chat.id == sender.config.MAIN_CHAT_ID:
            print('adding user {} to the community members'.format(user_filter))
            database.mongo_membership.update_one(user_filter, {'$set': {'is_guest': True}}, upsert=True)
        elif message.chat.id == sender.config.FIRST_CHAT_ID:
            database.mongo_membership.update_one(user_filter, {'$set': {'is_member': True}}, upsert=True)
            print('adding user {} to the club members'.format(user_filter))
        return

    if bot is not None:
        bot.send_chat_action(message.chat.id, 'typing')
    uo = get_or_insert_user(message.from_user, database=database)
    user_id = message.chat.id
    LoggedMessage(
        text=message.text, user_id=user_id, from_user=True, database=database, username=uo.get('username')
    ).save()
    ctx = Context(text=message.text, user_object=uo, sender=sender, message=message, bot=bot)

    for handler in [
        try_queued_messages,
        try_invitation,
        try_event_creation,
        try_event_usage,
        try_peoplebook_management,
        try_coffee_management,
        try_membership_management,
        try_event_edition,
        try_conversation,
        doggy_style,
        fallback
    ]:
        ctx = handler(ctx, database=database)
        if ctx.intent is not None:
            break

    assert ctx.intent is not None
    assert ctx.response is not None
    database.mongo_users.update_one({'tg_id': message.from_user.id}, ctx.make_update())
    user_object = get_or_insert_user(tg_uid=message.from_user.id, database=database)

    # context-independent suggests (they are always below the dependent ones)
    ctx.suggests.extend(make_standard_suggests(database=database, user_object=user_object))

    logger.info('Start sending an already prepared reply to {}'.format(message.message_id))
    sender(
        text=ctx.response, reply_to=message, suggests=ctx.suggests, database=database, intent=ctx.intent,
        file_to_send=ctx.file_to_send
    )
    logger.info('Sent message with text {} as reply to {}'.format(ctx.response, message.message_id))
