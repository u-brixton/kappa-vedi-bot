class SessionManager:
    def __init__(self, connector):
        self.connector = connector
    def get_state(self, chat_id):
        return dict()
        # raise NotImplementedError()
        # we need Mongo to manage non-structured sessions
    def set_state(self, chat_id, state):
        raise NotImplementedError()
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
