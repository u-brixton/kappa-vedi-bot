import json
import copy


def update_dict(base_dict, updates):
    result = copy.deepcopy(base_dict)
    result.update(updates)
    return result


class SessionManager:
    def __init__(self, connector, group_manager=None):
        self.connector = connector
        self.connector.add_initial_query(
            "CREATE TABLE IF NOT EXISTS dialog_states(chat_id VARCHAR PRIMARY KEY, state VARCHAR)")
        self.group_manager = group_manager  # это не очень хорошая зависимость, на самом деле

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
        text = message.text
        state_name = state.get('name')
        response = None
        new_state = None
        if state:
            if state_name == 'create_event.initial':
                response = "Отлично, создаём новое мероприятие! Введите место:"
                new_state = {'name': 'create_event.place'}
            elif state_name == 'create_event.place':
                response = 'Теперь введите дату и время:'
                new_state = update_dict(state, {'name': 'create_event.time', 'place': text})
            elif state_name == 'create_event.time':
                response = 'Теперь введите краткую программу мероприятия:'
                new_state = update_dict(state, {'name': 'create_event.program', 'time': text})
            elif state_name == 'create_event.program':
                response = 'Теперь введите краткую программу мероприятия:'
                new_state = update_dict(state, {'name': 'create_event.cost', 'program': text})
            elif state_name == 'create_event.cost':
                response = 'Отлично! Сейчас я создам мероприятие по месту {}, в {}, в программе {}, взнос {}'.format(
                    state['place'], state['time'], state['program'], state['cost']
                ) + '\nВведите "да", если действительно хотите его создать и разослать приглашения:'
                new_state = update_dict(state, {'name': 'create_event.confirm'})
            elif state_name == 'create_event.confirm':
                if text.lower().strip() == 'да':
                    response = 'Отлично! Рассылаю приглашения...'
                    # todo: разослать приглашения
                else:
                    response = 'Ладно, не буду создавать это мероприятие.'
                new_state = {}
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
        if new_state is not None:
            self.set_state(message.chat.id, new_state)
        if response is not None:
            return response
