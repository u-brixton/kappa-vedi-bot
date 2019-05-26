
import os

import cloudinary
import cloudinary.uploader
import re

import tempfile


def photo_url_from_message(bot, message):
    url = None
    with tempfile.TemporaryDirectory() as temp_dir:
        filename = load_photo_from_message(bot, message, directory=temp_dir)
        if filename is not None:
            url = upload_photo_to_cloudinary(filename)
    return url


def load_photo_from_message(bot, message, directory='offline'):
    file_info = None
    file_name = None
    if message.photo is not None:
        for p in message.photo:
            file_info = bot.get_file(p.file_id)
            file_name = file_info.file_path.replace('/', '__')
    elif message.document is not None:
        file_info = bot.get_file(message.document.file_id)
        file_name = message.document.file_name
    if file_info is None:
        return None

    downloaded_file = bot.download_file(file_info.file_path)
    full_file_name = os.path.join(directory, file_name)
    with open(full_file_name, 'wb') as f:
        f.write(downloaded_file)

    return full_file_name


def upload_photo_to_cloudinary(full_file_name):
    cloudinary_url = os.getenv('CLOUDINARY_URL')
    if cloudinary_url is None:
        print('no url')
        return None
    matched = re.match('cloudinary://(.*):(.*)@(.*)', cloudinary_url)
    assert len(matched.groups()) == 3
    api_key, api_secret, cloud_name = matched.groups()

    uploaded = cloudinary.uploader.upload(
        full_file_name,
        api_secret=api_secret,
        api_key=api_key,
        cloud_name=cloud_name
    )
    return uploaded['url']
