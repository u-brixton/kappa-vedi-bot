import logging

from datetime import datetime
from pymongo import MongoClient
from utils import matchers


logger = logging.getLogger(__name__)


def make_multidict(items, keyname):
    result = {}
    for item in items:
        key = item[keyname]
        if key not in result:
            result[key] = []
        result[key].append(item)
    return result


class Database:
    def __init__(self, mongo_url, admins=None, cache_ttl_seconds=10):
        self._setup_client(mongo_url=mongo_url)
        self._setup_collections()
        self._admins = set([] if admins is None else admins)
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache_time = datetime.now()
        self._update_cache(force=True)

    def _setup_client(self, mongo_url):
        self._mongo_client = MongoClient(mongo_url)
        self._mongo_db = self._mongo_client.get_default_database()

    def _setup_collections(self):
        self.mongo_users = self._mongo_db.get_collection('users')
        self.mongo_messages = self._mongo_db.get_collection('messages')
        self.mongo_coffee_pairs = self._mongo_db.get_collection('coffee_pairs')
        self.mongo_events = self._mongo_db.get_collection('events')
        # title (text), code (text), date (text), ... and many other fields
        self.mongo_participations = self._mongo_db.get_collection('event_participations')
        # username, code, status (INVITATION_STATUSES), invitor (username)
        self.mongo_peoplebook = self._mongo_db.get_collection('peoplebook')
        self.mongo_membership = self._mongo_db.get_collection('membership')
        self.message_queue = self._mongo_db.get_collection('message_queue')
        # (username: text, text: text, intent: text, fresh: bool)

    def _update_cache(self, force=False):
        if not force and (datetime.now() - self._cache_time).total_seconds() < self.cache_ttl_seconds:
            return
        logger.info('updating database cache...')
        self._cache_time = datetime.now()
        self._cached_mongo_membership = {item['username']: item for item in self.mongo_membership.find({})}
        self._cached_mongo_participations = make_multidict(self.mongo_participations.find({}), 'username')

    def is_at_least_guest(self, user_object):
        return self.is_guest(user_object) or self.is_member(user_object) or self.is_admin(user_object)

    def is_at_least_member(self, user_object):
        return self.is_member(user_object) or self.is_admin(user_object)

    def is_admin(self, user_object):
        if (user_object.get('username') or '').lower() in self._admins:
            return True
        return False

    def is_member(self, user_object):
        username = user_object.get('username') or ''
        username = username.lower()
        self._update_cache()
        return self._cached_mongo_membership.get(username, {}).get('is_member')

    def is_guest(self, user_object):
        # todo: check case of username here and everywhere
        self._update_cache()
        username = user_object.get('username') or ''
        if self._cached_mongo_membership.get(username, {}).get('is_guest'):
            return True
        if self._cached_mongo_membership.get(username, {}).get('is_member'):
            return True
        return username in self._cached_mongo_participations


class LoggedMessage:
    def __init__(self, text, user_id, from_user, database: Database, username=None, intent=None, meta=None):
        self.text = text
        self.user_id = user_id
        self.from_user = from_user
        self.timestamp = str(datetime.utcnow())
        self.username = username
        self.intent = intent
        self.meta = meta

        self.mongo_collection = database.mongo_messages

    def save(self):
        self.mongo_collection.insert_one(self.to_dict())

    def to_dict(self):
        result = {
            'text': self.text,
            'user_id': self.user_id,
            'from_user': self.from_user,
            'timestamp': self.timestamp
        }
        if self.username is not None:
            result['username'] = matchers.normalize_username(self.username)
        if self.intent is not None:
            result['intent'] = self.intent
        if self.meta is not None:
            result['meta'] = self.meta
        return result


def get_or_insert_user(tg_user=None, tg_uid=None, database: Database=None):
    if tg_user is not None:
        uid = tg_user.id
    elif tg_uid is not None:
        uid = tg_uid
    else:
        return None
    assert database is not None
    found = database.mongo_users.find_one({'tg_id': uid})
    if found is not None:
        if tg_user is not None and found.get('username') != matchers.normalize_username(tg_user.username):
            database.mongo_users.update_one(
                {'tg_id': uid},
                {'$set': {'username': matchers.normalize_username(tg_user.username)}}
            )
            found = database.mongo_users.find_one({'tg_id': uid})
        return found
    if tg_user is None:
        return ValueError('User should be created, but telegram user object was not provided.')
    new_user = dict(
        tg_id=tg_user.id,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
        username=matchers.normalize_username(tg_user.username),
        wants_next_coffee=False
    )
    database.mongo_users.insert_one(new_user)
    return new_user
