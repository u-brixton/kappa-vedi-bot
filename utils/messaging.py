MAX_LEN = 4000
MESSAGE_SEPARATOR = '<NEW_MESSAGE>'


def split_message(text, max_len=MAX_LEN, sep=MESSAGE_SEPARATOR):
    chunks = text.split(sep)
    result = []
    while len(chunks) > 0:
        prefix = chunks.pop(0)
        if prefix.strip() == '':
            continue
        if len(prefix) <= max_len:
            result.append(prefix.strip())
            continue
        # todo: try to preserve HTML structure
        sep_pos = prefix[:max_len].rfind('\n\n')
        if sep_pos == -1:
            sep_pos = prefix[:max_len].rfind('\n')
        if sep_pos == -1:
            sep_pos = prefix[:max_len].rfind(' ')
        if sep_pos == -1:
            sep_pos = max_len
        prefix, suffix = prefix[:sep_pos], prefix[sep_pos:]
        result.append(prefix.strip())
        chunks.insert(0, suffix)
    return result
