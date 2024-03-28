import hashlib
from collections import OrderedDict


def hash_string_md5(s):
    if isinstance(s, int):
        s = str(s)
    return hashlib.md5(s.encode('utf-8')).hexdigest()


def resolve_secure_params(queries):
    result_queries = OrderedDict(queries)

    sorted_hashed_values = sorted(hash_string_md5(value) for value in result_queries.values())

    sign = "ABCDEF00G"
    for hashed_value in sorted_hashed_values:
        sign += hashed_value

    result_queries['sign'] = hash_string_md5(sign)

    return result_queries