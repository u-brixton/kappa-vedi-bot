

def render_text_profile(profile, editable=True):
    rows = [
        '<b>{} {}</b>'.format(profile.get('first_name', ''), profile.get('last_name', '')),
        '<b>Чем занимаюсь</b>',
        '{}'.format(profile.get('activity', '')),
        '<b>О чем могу рассказать</b>',
        '{}'.format(profile.get('topics', '')),
        '<b>Контакты</b>',
        profile.get('contacts', 't.me/{}'.format(profile.get('username', ''))),
        '<a href="kv-peoplebook.herokuapp.com/person/{}">как это выглядит на сайте</a>'.format(
            profile.get('username', 'does_not_exist')
        ),
    ]
    if editable:
        rows.extend([
            '/set_pb_name     - редактировать имя',
            '/set_pb_surname  - редактировать фамилию',
            '/set_pb_activity - редактировать занятия',
            '/set_pb_topics   - редактировать интересные темы',
            '/set_pb_photo    - редактировать фото',
            '/set_pb_contacts - редактировать контакты',
        ])
    return '\n'.join(rows)
