import re

MIN_LENGTH_EXCLUSIVE = 8  # password must be MORE than 8 characters
MAX_BYTES = 72  # bcrypt only uses the first 72 bytes

RULES = [
    ("length", "More than 8 characters", lambda p: len(p) > MIN_LENGTH_EXCLUSIVE),
    ("upper", "At least one uppercase letter", lambda p: re.search(r"[A-Z]", p) is not None),
    ("lower", "At least one lowercase letter", lambda p: re.search(r"[a-z]", p) is not None),
    ("special", "At least one special character", lambda p: re.search(r"[^A-Za-z0-9]", p) is not None),
]


def password_errors(password: str) -> list[str]:
    """Return the list of unmet rules; empty means the password is valid."""
    password = password or ""
    errors = [label for _, label, check in RULES if not check(password)]
    if len(password.encode("utf-8")) > MAX_BYTES:
        errors.append(f"At most {MAX_BYTES} bytes long")
    return errors


def is_valid_password(password: str) -> bool:
    return not password_errors(password)
