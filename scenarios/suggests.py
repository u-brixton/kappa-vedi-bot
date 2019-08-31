from scenarios.coffee import TAKE_PART, NOT_TAKE_PART


def make_standard_suggests(database, user_object):
    suggests = []

    if database.is_at_least_guest(user_object):
        suggests.append('Покажи встречи')
        suggests.append('Мой пиплбук')
        suggests.append(TAKE_PART if not user_object.get('wants_next_coffee') else NOT_TAKE_PART)

    if database.is_admin(user_object):
        suggests.append('Создать встречу')
        suggests.append('Добавить членов')

    return suggests
