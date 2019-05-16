from utils.telegram_api import surrogate_message
from utils.base_workflow import BaseSessionManager, update_dict
from datetime import datetime


def format_event_description(event_dict):
    result = 'Мероприятие:'
    for key, title in [
        ['place', 'место'],
        ['time', 'время'],
        ['program', 'программа'],
        ['cost', 'взнос'],
        ['chat', 'чат'],
    ]:
        if key in event_dict:
            result = result + '\n\t{}: \t{},'.format(title, event_dict.get(key))
    result = result + '\n'
    return result


class SessionManager(BaseSessionManager):
    def get_response(self, state, message):
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
                new_state = update_dict(state, {'name': 'create_event.time',
                                                'place': text})
            elif state_name == 'create_event.time':
                # todo: validate the time format, ask again if needed
                response = 'Теперь введите краткую программу мероприятия:'
                new_state = update_dict(state, {'name': 'create_event.program',
                                                'time': text})
            elif state_name == 'create_event.program':
                response = 'Теперь введите размер взноса на мероприятие:'
                new_state = update_dict(state, {'name': 'create_event.cost',
                                                'program': text})
            elif state_name == 'create_event.cost':
                new_state = update_dict(state, {'name': 'create_event.confirm',
                                                'cost': text})
                response = 'Отлично! Сейчас я создам ' + format_event_description(new_state) \
                    + '\nВведите "да", если действительно хотите его создать и разослать приглашения:'
            elif state_name == 'create_event.confirm':
                if text.lower().strip() == 'да':
                    event_id = self.event_manager.add_event(
                        {'place': state['place'],
                         'time': datetime.strptime(state['time'],
                                                   "%d.%m.%Y %H:%M"),
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
                        for t_username, t_chat_id in zip(non_missing,
                                                         non_missing_chat_id):
                            self.send_function(
                                surrogate_message(t_chat_id, t_username),
                                invitation, reply=False)
                            self.set_state(t_chat_id,
                                           {'name': 'invite_to_event.confirm',
                                            'event_id': event_id})

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
                        message.chat.username, state.get('event_id', None),
                        answer_code)
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
        return new_state, response, callback
