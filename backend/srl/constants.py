from urllib.parse import urlparse

YOUTUBE_ALLOWED_HOSTS: set[str] = {
    "www.youtube.com",
    "youtube.com",
    "youtu.be",
    "m.youtube.com",
}


def is_youtube_url(
    url: str,
) -> bool:
    """Return True if `url` is an http(s) URL on an allowed YouTube host."""
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and parsed.netloc in YOUTUBE_ALLOWED_HOSTS
