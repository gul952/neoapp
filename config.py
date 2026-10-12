import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
SECRET_KEY_FILE = os.path.join(BASE_DIR, ".secret_key")


def _get_or_create_secret_key():
    """Uses SECRET_KEY from the environment if set (preferred for a real
    deployment). Otherwise, generates a random key the first time this app
    ever runs on this machine and saves it to a local file so every
    subsequent run reuses the SAME key (changing it would silently log
    everyone out and invalidate every session). This file is specific to
    one installation and should never be copied/shared/committed anywhere.
    """
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key

    if os.path.exists(SECRET_KEY_FILE):
        with open(SECRET_KEY_FILE, "r") as f:
            return f.read().strip()

    new_key = secrets.token_hex(32)
    with open(SECRET_KEY_FILE, "w") as f:
        f.write(new_key)
    return new_key


class Config:
    SECRET_KEY = _get_or_create_secret_key()

    # Defaults to a single local file - neosepsis.db - sitting next to this app.
    # No external database server needed. If the department ever wants a
    # shared Postgres server instead, only this line changes.
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'neosepsis.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
