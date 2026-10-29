import re


def image_search_query(value):
    """Search five-digit numeric filenames by range, independently of DB IDs."""
    text = value.strip()
    if not text:
        return {}

    match = re.fullmatch(r'([0-9]+)\s*-\s*([0-9]+)', text)
    if match is None:
        return {'file_name__icontains': value}

    start, end = (int(part) for part in match.groups())
    if not 1 <= start <= end <= 99999:
        raise ValueError('ファイル番号の範囲は1〜99999で、開始番号が終了番号以下になるよう指定してください。')
    return {'__raw__': {'file_name': {
        '$gte': '{:05d}.'.format(start),
        '$lt': '{:05d}/'.format(end),
        '$regex': r'^[0-9]{5}\.[^.]+$',
    }}}
