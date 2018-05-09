import telebot


def surrogate_message(chat_id, username='DUMMY', text='DUMMY'):
    obj = {
        'message_id': 'DUMMY',
        'date': 'DUMMY',
        'chat': {'id': str(chat_id), 'type': 'DUMMY', 'username': str(username)},
        'text': str(text),
    }
    return telebot.types.Message.de_json(obj)
