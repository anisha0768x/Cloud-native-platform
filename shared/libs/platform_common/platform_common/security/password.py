"""
Password hashing (bcrypt, used directly).

WHY bcrypt directly instead of passlib: passlib is effectively
unmaintained and has a known incompatibility with bcrypt>=4.1 (it probes
the backend using an API bcrypt removed), which surfaced as a real test
failure while building this service — using the underlying library
directly avoids depending on an abandoned compatibility shim.
"""

import bcrypt

_MAX_BCRYPT_BYTES = 72  # bcrypt's hard input-length limit


def hash_password(plain_password: str) -> str:
    password_bytes = plain_password.encode("utf-8")[:_MAX_BCRYPT_BYTES]
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode("utf-8")[:_MAX_BCRYPT_BYTES]
    try:
        return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))
    except ValueError:
        # Malformed/foreign hash format — treat as "does not match" rather
        # than raising, so a bad stored hash can't crash the login endpoint.
        return False
