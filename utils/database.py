from pymongo import MongoClient


class Database:
    def __init__(self, mongo_url, admins=None):
        self._mongo_client = MongoClient(mongo_url)
        self._mongo_db = self._mongo_client.get_default_database()
        self.mongo_users = self._mongo_db.get_collection('users')
        self.mongo_messages = self._mongo_db.get_collection('messages')
        self.mongo_coffee_pairs = self._mongo_db.get_collection('coffee_pairs')
        self.mongo_events = self._mongo_db.get_collection('events')
        # title (text), code (text), date (text) # todo time place program cost chat
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
