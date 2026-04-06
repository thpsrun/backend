import re

_TIME_PATTERN = re.compile(
    r"(?:(\d+)h\s*)?" r"(?:(\d+)m\s*)?" r"(?:(\d+)s\s*)?" r"(?:(\d+)ms)?",
)


def parse_time(time_str: str) -> float:
    """Parse a human-readable time string into float seconds.

    Accepts format produced by convert_time(): "1h 23m 45s 678ms".
    All components are optional but at least one must be present.

    Arguments:
        time_str: Time string like "1h 23m 45s 678ms", "45m 12s", "30s 500ms", etc.

    Returns:
        Time in seconds as a float.

    Raises:
        ValueError: If the string cannot be parsed or contains no time components.
    """
    time_str = time_str.strip()
    if not time_str:
        raise ValueError("Empty time string")

    match = _TIME_PATTERN.fullmatch(time_str)
    if not match:
        raise ValueError(f"Cannot parse time string: {time_str!r}")

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    milliseconds = int(match.group(4) or 0)

    total = hours * 3600.0 + minutes * 60.0 + seconds + milliseconds / 1000.0

    if total == 0 and not any(match.group(i) for i in range(1, 5)):
        raise ValueError(f"Cannot parse time string: {time_str!r}")

    return total
