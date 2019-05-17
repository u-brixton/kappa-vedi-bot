import re


def is_like_telegram_login(text):
    return bool(re.match('[a-z0-9_]{5,}', text))


def is_like_yes(text):
    return bool(re.match('да|ага|конечно', text))


def is_like_no(text):
    return bool(re.match('нет', text))
