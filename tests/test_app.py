import mongomock

from utils.database import Database
from unittest.mock import patch


def test_import():
    with patch.dict('os.environ', {'TOKEN': 'mock token', 'MONGODB_URI': 'mock uri'}):
        def new_setup_client(obj, mongo_url):
            obj._mongo_db = mongomock.MongoClient().db

        with patch.object(Database, '_setup_client', new=new_setup_client):
            from main import server  # noqa
