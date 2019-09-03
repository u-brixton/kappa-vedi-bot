import pytest

import mongomock

from utils.dialogue_management import Context
from utils.database import Database
from utils.messaging import BaseSender

from scenarios.dog_mode import doggy_style
from scenarios.coffee import TAKE_PART, NOT_TAKE_PART

from response_logic import respond, PROCESSED_MESSAGES

from telebot.types import Message, User, Chat


class MockedDatabase(Database):
    def _setup_client(self, mongo_url):
        self._mongo_client = mongomock.MongoClient()
        self._mongo_db = self._mongo_client.db


class MockedMessage:
    def __init__(self, text, intent, suggests):
        self.text = text
        self.intent = intent
        self.suggests = suggests


class MockedSender(BaseSender):
    def __init__(self):
        self.sent_messages = []

    def __call__(self, *args, **kwargs):
        self.sent_messages.append(MockedMessage(
            text=kwargs['text'], intent=kwargs.get('intent'),
            suggests=kwargs.get('suggests', [])
        ))


@pytest.fixture()
def mocked_member_uo():
    return {}


@pytest.fixture()
def mocked_db():
    db = MockedDatabase(mongo_url="no url", admins=['an_admin'])
    db.mongo_membership.insert_one({'username': 'a_member', 'is_member': True})
    db.mongo_events.insert_one({'code': 'an_event', 'title': 'An Event', 'date': '2030.12.30'})
    db.mongo_participations.insert_one({'event_code': 'an_event', 'username': 'a_guest'})
    db._update_cache(force=True)
    return db


@pytest.fixture()
def mocked_sender():
    return MockedSender()


def make_mocked_message(text, user_id=123, first_name='Юзер', username='a_member', message_id=None):
    if message_id is None:
        message_id = len(PROCESSED_MESSAGES)
    message = Message(
        message_id=message_id,
        from_user=User(id=user_id, is_bot=False, first_name=first_name, username=username),
        date=None,
        chat=Chat(id=user_id, type='private'),
        content_type=None,
        options={},
        json_string=None
    )
    message.text = text
    return message


def test_everything_is_ok():
    """ This is just a simple example of how a test may be created. """
    assert "A" == "A"


@pytest.mark.parametrize("text,expected_intent", [
    ("привет", None),
    ("покажи встречи", None),
    ("участвовать в следующем кофе", None),
    ("мой пиплбук", None),
    ("да", None),
    ("добавить членов", None),
    ("сука бля", "DOG"),
    ("чё выёбываешься", "DOG"),
    ("ну ты пидор", "DOG"),
])
def test_dog_mode_activation(mocked_member_uo, mocked_db, text, expected_intent):
    ctx = Context(text=text, user_object=mocked_member_uo)
    new_ctx = doggy_style(ctx, database=mocked_db)
    assert new_ctx.intent == expected_intent


@pytest.mark.parametrize("text,expected_intent", [
    ("привет", "HELLO"),
    ("покажи встречи", "EVENT_GET_LIST"),
    ("Участвовать в следующем кофе", "TAKE_PART"),
    ("мой пиплбук", "PEOPLEBOOK_GET_FAIL"),
    ("да", "OTHER"),
    ("абырвалг", "OTHER"),
    ("добавить членов", "OTHER"),
    ("создать встречу", "OTHER"),
    ("сука бля", "DOG"),
    ("чё выёбываешься", "DOG"),
    ("ну ты пидор", "DOG"),
])
def test_basic_responses(mocked_sender, mocked_db, text, expected_intent):
    respond(
        message=make_mocked_message(text),
        database=mocked_db,
        sender=mocked_sender
    )
    assert len(mocked_sender.sent_messages) == 1
    last_message = mocked_sender.sent_messages[-1]
    assert last_message.intent == expected_intent


@pytest.mark.parametrize("text,expected_intent", [
    ("добавить членов", "MEMBER_ADD_INIT"),
    ("создать встречу", "EVENT_CREATE_INIT"),
])
def test_admin(mocked_sender, mocked_db, text, expected_intent):
    respond(
        message=make_mocked_message(text, username='an_admin'),
        database=mocked_db,
        sender=mocked_sender
    )
    assert len(mocked_sender.sent_messages) == 1
    last_message = mocked_sender.sent_messages[-1]
    assert last_message.intent == expected_intent


def test_roles(mocked_db):
    assert mocked_db.is_at_least_guest({'username': 'a_guest'})
    assert not mocked_db.is_at_least_member({'username': 'a_guest'})


def test_guest_can_see_coffee(mocked_sender, mocked_db):
    respond(
        message=make_mocked_message('привет', username='a_guest'),
        database=mocked_db,
        sender=mocked_sender
    )
    assert len(mocked_sender.sent_messages) == 1
    last_message = mocked_sender.sent_messages[-1]
    assert last_message.intent == 'HELLO'
    assert TAKE_PART in last_message.suggests
    assert NOT_TAKE_PART not in last_message.suggests

    respond(
        message=make_mocked_message(TAKE_PART, username='a_guest'),
        database=mocked_db,
        sender=mocked_sender
    )
    assert len(mocked_sender.sent_messages) == 2
    last_message = mocked_sender.sent_messages[-1]
    assert last_message.intent == 'TAKE_PART'
    assert TAKE_PART not in last_message.suggests
    assert NOT_TAKE_PART in last_message.suggests
