import hashlib
import hmac
import os

from .database import connect


def hash_password(password, salt=None):
    salt = salt or os.urandom(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=64)
    return salt, key


def verify_password(password, salt, expected):
    try:
        _, actual = hash_password(password, salt)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def bootstrap_admin(username, password):
    salt, hashed = hash_password(password)
    with connect() as conn:
        row = conn.execute("SELECT role FROM users WHERE username=?", (username,)).fetchone()
        if row:
            if row["role"] != "admin":
                raise ValueError("Bootstrap username already belongs to a non-admin account")
            return
        conn.execute("INSERT INTO users(username,password_hash,salt,role) VALUES(?,?,?,'admin')",
                     (username, hashed, salt))
