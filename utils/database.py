from datetime import datetime

from pymongo import MongoClient


class Database:
    def __init__(self, mongo_url, admins=None):
        self._mongo_client = MongoClient(mongo_url)
        self._mongo_db = self._mongo_client.get_default_database()
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

        self._admins = set([] if admins is None else admins)

    def is_at_least_guest(self, user_object):
        return self.is_guest(user_object) or self.is_member(user_object) or self.is_admin(user_object)

    def is_at_least_member(self, user_object):
        return self.is_member(user_object) or self.is_admin(user_object)

    def is_admin(self, user_object):
        if user_object.get('username').lower() in self._admins:
            return True
        return False

    def is_member(self, user_object):
        existing = self.mongo_membership.find_one({'username': user_object.get('username', ''), 'is_member': True})
        return existing is not None

    def is_guest(self, user_object):
        # todo: lookup for the list of guests
        return True


class LoggedMessage:
    def __init__(self, text, user_id, from_user, database: Database):
        self.text = text
        self.user_id = user_id
        self.from_user = from_user
        self.timestamp = str(datetime.utcnow())

        self.mongo_collection = database.mongo_messages

    def save(self):
        self.mongo_collection.insert_one(self.to_dict())

    def to_dict(self):
        return {
            'text': self.text,
            'user_id': self.user_id,
            'from_user': self.from_user,
            'timestamp': self.timestamp
        }


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
        if tg_user is not None and found.get('username') != tg_user.username:
            database.mongo_users.update_one({'tg_id': uid}, {'$set': {'username': tg_user.username}})
            found = database.mongo_users.find_one({'tg_id': uid})
        return found
    if tg_user is None:
        return ValueError('User should be created, but telegram user object was not provided.')
    new_user = dict(
        tg_id=tg_user.id,
        first_name=tg_user.first_name,
        last_name=tg_user.last_name,
        username=tg_user.username,
        wants_next_coffee=False
    )
    database.mongo_users.insert_one(new_user)
    return new_user
