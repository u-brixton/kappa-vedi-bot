import json
import copy


def update_dict(base_dict, updates):
    result = copy.deepcopy(base_dict)
    result.update(updates)
    return result


class BaseSessionManager:
    def __init__(self, connector, group_manager=None, event_manager=None, send_function=None):
        self.connector = connector
        self.connector.add_initial_query(
            "CREATE TABLE IF NOT EXISTS dialog_states(chat_id VARCHAR PRIMARY KEY, state VARCHAR)")
        self.group_manager = group_manager  # это не очень хорошая зависимость, на самом деле
        self.event_manager = event_manager  # но на первое время сгодится, потом отрефакторим
        self.send_function = send_function

    def get_state(self, chat_id):
        query = "SELECT state FROM dialog_states WHERE chat_id = '{}'".format(chat_id)
        results = self.connector.sql_get(query)
        if results:
            return json.loads(results[0][0])
        # we need Mongo to manage non-structured sessions
        # or we can just JSON-encode states and put them into a relational DB!
        return dict()

    def set_state(self, chat_id, state):
        values = "('{}', '{}')".format(chat_id, json.dumps(state))
        q = "INSERT INTO dialog_states VALUES{} ON CONFLICT(chat_id) DO UPDATE SET(chat_id, state)={}".format(
            values, values)
        self.connector.sql_set(q)

    def get_response(self, state, message):
        raise NotImplementedError()
        # return new_state, response, callback

    def process_message(self, message):
        state = self.get_state(message.chat.id)
        new_state, response, callback = self.get_response(state, message)
        if new_state is not None:
            self.set_state(message.chat.id, new_state)
        return response, callback
