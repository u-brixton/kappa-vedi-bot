import re


def is_like_telegram_login(text):
    return bool(re.match('[a-z0-9_]{5,}', text))
