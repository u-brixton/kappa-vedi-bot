import re


class Context:
    def __init__(self, user_object=None, text=None, sender=None, message=None, bot=None):
        self.user_object = user_object
        self.username = user_object.get('username', '')
        self.last_intent = user_object.get('last_intent', '')
        self.last_expected_intent = user_object.get('last_expected_intent', '')
        self.text = text or ''
        self.text_normalized = re.sub('[.,!?:;()\s]+', ' ', self.text.lower()).strip()
        self.sender = sender

        self.message = message
        self.bot = bot

        self.intent = None
        self.response = None
        self.the_update = None
        self.expected_intent = None
        self.suggests = []
        self.file_to_send = None

    def make_update(self):
        if self.the_update is None:
            the_update = {}
        else:
            the_update = self.the_update
        if '$set' not in the_update:
            the_update['$set'] = {}
        the_update['$set']['last_intent'] = self.intent
        the_update['$set']['last_expected_intent'] = self.expected_intent
        return the_update
