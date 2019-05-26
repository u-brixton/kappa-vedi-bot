
from utils.database import Database, LoggedMessage, get_or_insert_user
from utils.dialogue_management import Context
from utils.messaging import BaseSender

from scenarios.events import try_invitation, try_event_usage, try_event_creation, try_event_edition
from scenarios.peoplebook import try_peoplebook_management
from scenarios.conversation import try_conversation, fallback
from scenarios.dog_mode import doggy_style
from scenarios.push import try_queued_messages
from scenarios.membership import try_membership_management
from scenarios.coffee import try_coffee_management, TAKE_PART, NOT_TAKE_PART


def respond(message, database: Database, sender: BaseSender, bot=None):
    # todo: make it less dependent on telebot Message class structure
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
    if database.is_at_least_member(user_object):
        ctx.suggests.append(TAKE_PART if not user_object.get('wants_next_coffee') else NOT_TAKE_PART)

    if database.is_at_least_guest(user_object):
        ctx.suggests.append('Покажи встречи')
        ctx.suggests.append('Мой пиплбук')

    if database.is_admin(user_object):
        ctx.suggests.append('Создать встречу')
        ctx.suggests.append('Добавить членов')

    sender(text=ctx.response, reply_to=message, suggests=ctx.suggests, database=database, intent=ctx.intent)
