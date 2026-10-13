"""Existing PBKDF2 reviewer accounts remain compatible."""
import hashlib
import hmac
import re


def authenticate(accounts, username, password):
    user = accounts.get(username.strip())
    if not user or not isinstance(password, str):
        return False
    try:
        salt = bytes.fromhex(user['salt'])
        expected = user['password_hash']
        if len(salt) < 16 or not re.fullmatch(r'[0-9a-fA-F]{64}', expected):
            return False
        digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 300000).hex()
        return hmac.compare_digest(digest, expected.lower())
    except (ValueError, TypeError, KeyError):
        return False
