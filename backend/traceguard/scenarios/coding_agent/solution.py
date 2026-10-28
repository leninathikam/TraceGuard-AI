import re

_PATTERN = re.compile(r"(\d+)([hms])")
_UNITS = {"h": 3600, "m": 60, "s": 60}


def parse_duration(text: str) -> int:
    """Return the total number of seconds in a duration like '1h30m' or '45s'."""
    total = 0
    for value, unit in _PATTERN.findall(text):
        total += int(value) * _UNITS[unit]
    return total
