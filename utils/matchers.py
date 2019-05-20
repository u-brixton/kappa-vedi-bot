import re
import pymorphy2

morph = pymorphy2.MorphAnalyzer()


def inflect_first_word(text, case):
    words = text.split()
    first_word = morph.parse(words[0])[0].inflect({case}).word
    return ' '.join([first_word] + words[1:])


def is_like_telegram_login(text):
    return bool(re.match('[a-z0-9_]{5,}', text))


def is_like_yes(text):
    return bool(re.match('да|ага|конечно', text))


def is_like_no(text):
    return bool(re.match('нет', text))


def normalize_username(username):
    if username is not None:
        return username.lower().strip().strip('@')
    return None