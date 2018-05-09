import json


class SessionManager:
    def __init__(self, connector):
        self.connector = connector
        self.connector.add_initial_query(
            "CREATE TABLE IF NOT EXISTS dialog_states(chat_id VARCHAR PRIMARY KEY, state VARCHAR)")

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

    def process_message(self, message):
        state = self.get_state(message.chat.id)
        state_name = state.get('name')
        if state:
            if state_name == 'create_event.initial':
                pass
            elif state_name == 'create_event.place':
                pass
            elif state_name == 'create_event.time':
                pass
            elif state_name == 'create_event.plan':
                pass
            elif state_name == 'create_event.money':
                pass
            elif state_name == 'create_event.confirm':
                pass
            elif state_name == 'invite_to_event.confirm':
                pass
            elif state_name == 'remind_about_event.confirm':
                pass
            elif state_name == 'return_money.confirm':
                pass
            elif state_name == 'free_feedback.text_anonym':
                pass
            elif state_name == 'free_feedback.text_deanonym':
                pass
            elif state_name == 'event_feedback.points':
                pass
            elif state_name == 'event_feedback.text':
                pass
            # now we will handle each state according to the state itself and message.text
            raise NotImplementedError()
