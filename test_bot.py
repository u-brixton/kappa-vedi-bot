import pytest

from utils.dialogue_management import Context
from utils.database import Database

from dog_mode import doggy_style


class MockedDatabase(Database):
    def _setup_collections(self, mongo_url):
        # todo: make some collections mocked for the tests that need them
        pass


@pytest.fixture()
def mocked_member_uo():
    return {}


@pytest.fixture()
def mocked_db():
    return MockedDatabase(mongo_url="no url")


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
