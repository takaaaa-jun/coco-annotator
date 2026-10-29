import re


def image_search_query(value):
    """Treat a numeric start-end search as an inclusive database image ID range."""
    text = value.strip()
    if not text:
        return {}

    match = re.fullmatch(r'([0-9]+)\s*-\s*([0-9]+)', text)
    if match is None:
        return {'file_name__icontains': value}

    start, end = (int(part) for part in match.groups())
    if not 1 <= start <= end <= 9223372036854775807:
        raise ValueError('画像IDの範囲は1以上で、開始番号が終了番号以下になるよう指定してください。')
    return {'id__gte': start, 'id__lte': end}
