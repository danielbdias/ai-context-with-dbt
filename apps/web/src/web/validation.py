"""Form input validation."""


def clean_message(raw: str, max_length: int) -> str | None:
    """Return the trimmed message, or None when it is not acceptable.

    Browsers submit newlines as CRLF, which would count twice against the
    limit, so they are normalized first. NUL bytes are rejected because
    Postgres cannot store them.
    """
    message = raw.replace("\r\n", "\n").strip()
    if not message or len(message) > max_length or "\x00" in message:
        return None
    return message
