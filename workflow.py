import json
import copy
from utils.telegram_api import surrogate_message
from datetime import datetime


def update_dict(base_dict, updates):
    result = copy.deepcopy(base_dict)
    result.update(updates)
    return result


def format_event_description(event_dict):
    return 'мероприятие по месту {}, в {}, в программе {}, взнос {}'.format(
        event_dict['place'],
        event_dict['time'],  # todo: make sure the datetime renders corrrectly
        event_dict['program'],
        event_dict['cost'])


class SessionManager:
    def __init__(self, connector, group_manager=None, event_manager=None, send_function=None):
        self.connector = connector
        self.connector.add_initial_query(
            "CREATE TABLE IF NOT EXISTS dialog_states(chat_id VARCHAR PRIMARY KEY, state VARCHAR)")
        self.group_manager = group_manager  # это не очень хорошая зависимость, на самом деле
        self.event_manager = event_manager  # но на первое время сгодится, потом отрефакторим
        self.send_function = None

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

        # sometimes message text has priority over states
        if text == '/reset':
            state_name = None
            new_state = {}
            response = "Возвращаю вас в исходное состояние. Если вы есть, будьте первыми!"
        elif text == '/create_event':
            state_name = 'create_event.initial'

        if state_name is not None:
            if state_name == 'create_event.initial':
                response = "Отлично, создаём новое мероприятие! Введите место:"
                new_state = {'name': 'create_event.place'}
            elif state_name == 'create_event.place':
                response = 'Теперь введите дату и время в формате DD.MM.YYYY HH:MM (и никак иначе):'
                new_state = update_dict(state, {'name': 'create_event.time', 'place': text})
            elif state_name == 'create_event.time':
                response = 'Теперь введите краткую программу мероприятия:'
                new_state = update_dict(state, {'name': 'create_event.program', 'time': text})
            elif state_name == 'create_event.program':
                response = 'Теперь введите размер взноса на мероприятие:'
                new_state = update_dict(state, {'name': 'create_event.cost', 'program': text})
            elif state_name == 'create_event.cost':
                new_state = update_dict(state, {'name': 'create_event.confirm', 'cost': text})
                response = 'Отлично! Сейчас я создам ' + format_event_description(new_state) \
                           + '\nВведите "да", если действительно хотите его создать и разослать приглашения:'
            elif state_name == 'create_event.confirm':
                if text.lower().strip() == 'да':
                    response = 'Отлично! Рассылаю приглашения...'
                    event_id = self.event_manager.add_event(
                        {'place': state['place'],
                         'time': datetime.strptime(state['time'], "%d.%m.%Y %H:%M"),
                         'cost': state['cost'],
                         'program': state['program']
                         })
                    # send invitations
                    invitation = "Готовится мероприятие: " + format_event_description(state) + \
                        "\nВы пойдёте? Ответьте 'да', 'нет', или 'пока не знаю'."
                    users = self.group_manager.users
                    chat_ids = self.group_manager.get_chat_id_for_users(users)
                    missing = []
                    for username, chat_id in zip(users, chat_ids):
                        if chat_id is None:
                            missing.append(username)
                        else:
                            self.send_function(surrogate_message(chat_id, username), invitation)
                            self.set_state(chat_id, {'name': 'invite_to_event.confirm', 'event_id': event_id})
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
