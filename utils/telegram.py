
from telebot import types


def render_markup(suggests=None, max_columns=3, initial_ratio=2):
    if suggests is None or len(suggests) == 0:
        return types.ReplyKeyboardRemove(selective=False)
    markup = types.ReplyKeyboardMarkup(row_width=max(1, min(max_columns, int(len(suggests) / initial_ratio))))
    markup.add(*suggests)
    return markup
