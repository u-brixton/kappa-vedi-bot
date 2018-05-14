import json
import copy
from utils.telegram_api import surrogate_message
from datetime import datetime


def update_dict(base_dict, updates):
    result = copy.deepcopy(base_dict)
    result.update(updates)
    return result


def format_event_description(event_dict):
    return 'мероприятие:\n\tместо:\t{},\n\tвремя:\t{},\n\tпрограмма:\t{},\n\tвзнос:\t{}\n'.format(
        event_dict['place'],
        event_dict['time'],
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
        callback = None

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
                # todo: validate the time format, ask again if needed
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
                    event_id = self.event_manager.add_event(
                        {'place': state['place'],
                         'time': datetime.strptime(state['time'], "%d.%m.%Y %H:%M"),
                         'cost': state['cost'],
                         'program': state['program']
                         })
                    # todo: check if event_id is not None
                    response = 'Отлично! Подготавливаю приглашения...'
                    # send invitations
                    invitation = "Готовится " + format_event_description(state) + \
                        """\nВы пойдёте? Ответьте "да", "нет", или "пока не знаю"."""
                    users = self.group_manager.users
                    chat_ids = self.group_manager.get_chat_id_for_users(users)
                    missing = []
                    non_missing = []
                    non_missing_chat_id = []
                    for username, chat_id in zip(users, chat_ids):
                        if chat_id is None:
                            missing.append(username)
                        else:
                            non_missing.append(username)
                            non_missing_chat_id.append(chat_id)
                    response = response + '\nПриглашу: {}\nНет в чате: {}'.format(
                        ", ".join(non_missing) or "нет таких",
                        ", ".join(missing) or "нет таких"
                    )

                    # invitations must be set only after this function has finished - make it a callback
                    def callback_tmp():
                        for t_username, t_chat_id in zip(non_missing, non_missing_chat_id):
                            self.send_function(surrogate_message(t_chat_id, t_username), invitation, reply=False)
                            self.set_state(t_chat_id, {'name': 'invite_to_event.confirm', 'event_id': event_id})
                    callback = callback_tmp
                else:
                    response = 'Ладно, не буду создавать это мероприятие.'
                new_state = {}
            elif state_name == 'invite_to_event.confirm':
                processed = text.lower().strip()
                answer_code = None
                if processed == 'да':
                    response = 'Отлично, ждём вас!'
                    answer_code = 1
                    # todo: turn on collector function
                elif processed == 'нет':
                    response = 'Очень жаль, что у вас не получится прийти.'
                    answer_code = 2
                    # todo: try to collect feedback
                elif processed in {'пока не знаю', 'не знаю'}:
                    response = 'Ну я тогда ещё разок позже спрошу.'
                    answer_code = 3
                    # todo: solve the ask-later problem
                else:
                    response = 'Пожалуйста, ответьте в точности одной из фраз - "да", "нет" или "пока не знаю"'
                if answer_code is not None:
                    new_state = {}
                    self.event_manager.record_invitation_result(
                        message.chat.username, state.get('event_id', None), answer_code)
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
        return response, callback
