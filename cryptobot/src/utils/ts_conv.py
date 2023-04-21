import datetime


def get_ms_from_str(date_time, str_format='%Y-%m-%d'):
    # print(int(datetime.datetime.now().timestamp() * 1000))
    return int(datetime.datetime.strptime(date_time, str_format).replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)


def get_str_from_ms(date_time, str_format='%Y-%m-%d'):
    return datetime.datetime.fromtimestamp(date_time / 1000, tz=datetime.timezone.utc).strftime(str_format)


if __name__ == "__main__":
    print(f'{__file__} main')
    ms = get_ms_from_str('2021-01-01')
    print(ms)
    print(get_str_from_ms(ms, '%Y-%m-%d %H:%M:%S'))


