

def render_text_profile(profile):
    result = '\n'.join([
        '<b>{} {}</b>'.format(profile.get('first_name', ''), profile.get('last_name', '')),
        '<b>Чем занимаюсь</b>',
        '{}'.format(profile.get('activity', '')),
        '<b>О чем могу рассказать</b>',
        '{}'.format(profile.get('topics', '')),
        '<b>Контакты</b>',
        profile.get('contacts', 't.me/{}'.format(profile.get('username', ''))),
        '<a href="kv-peoplebook.herokuapp.com/person/{}">как это выглядит на сайте</a>'.format(
            profile.get('username', 'does_not_exist')
        )
    ])
    return result
