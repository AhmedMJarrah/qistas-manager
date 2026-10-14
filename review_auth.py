"""Existing PBKDF2 reviewer accounts remain compatible."""
import hashlib
import hmac
import re

REVIEWER_NAMES = {'v1': 'ayah', 'v2': 'talal', 'v3': 'moath',
                  'v4': 'batoul', 'v5': 'aoon', 'v6': 'sadeen'}


def canonical_username(username):
    value = str(username or '').strip().casefold()
    return {name: key for key, name in REVIEWER_NAMES.items()}.get(value, value)


def reviewer_name(username):
    return REVIEWER_NAMES.get(canonical_username(username), str(username))


def canonical_accounts(accounts):
    """Accept old or named Secrets sections; keep immutable log identities v1..v6."""
    result = {}
    for name, user in accounts.items():
        key = canonical_username(name)
        account = dict(user)
        if key in REVIEWER_NAMES:
            account['display_name'] = REVIEWER_NAMES[key]
        if key in result and any(result[key].get(f) != account.get(f) for f in ('salt', 'password_hash')):
            raise ValueError('يوجد حسابان مختلفان لنفس المتطوع في Secrets. احتفظ بقسم واحد ببياناته الأصلية.')
        result[key] = account
    return result


def authenticate(accounts, username, password):
    user = accounts.get(canonical_username(username))
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
