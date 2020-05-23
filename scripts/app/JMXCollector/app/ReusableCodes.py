import time
from functools import reduce

# Lambda function to fetch current time in millis when needed in an int format
current_milli_time = lambda: int(round(time.time() * 1000))


def flatten(d, pref=''):
    return(reduce(
        lambda new_d, kv:
            isinstance(kv[1], dict) and {**new_d, **flatten(kv[1], pref + kv[0])} or {**new_d, pref + kv[0]: kv[1]},
            d.items(),
            {}))
