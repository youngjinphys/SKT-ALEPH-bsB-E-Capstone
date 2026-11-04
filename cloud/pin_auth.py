"""Explicitly time-limited test login. Never enabled by a default credential.

Attempts and opaque sessions live in PostgreSQL, not a serverless worker's RAM.
The optional second code is another shared secret, NOT independent MFA.
"""
import hashlib
import hmac
import os
import re
import secrets
import time
from dataclasses import dataclass

from fastapi import HTTPException
from .state import SupabaseStore, StorageUnavailable

COOKIE = '__Host-aleph_test_session'
TTL = 900
HASH_RE = re.compile(r'scrypt\$([a-f0-9]{32})\$([a-f0-9]{64})')

@dataclass(frozen=True)
class Config:
    pin_hash: str
    extra_hash: str
    expires: int
    starts: int

    @property
    def version(self):
        return hashlib.sha256(f'{self.pin_hash}|{self.extra_hash}|{self.starts}|{self.expires}'.encode()).hexdigest()


def config():
    if os.getenv('CAPSTONE_TEST_PIN_ENABLED') != 'true':
        return None
    pin = os.getenv('CAPSTONE_TEST_PIN_HASH', '')
    extra = os.getenv('CAPSTONE_TEST_ACCESS_CODE_HASH', '')
    try:
        expires = int(os.getenv('CAPSTONE_TEST_PIN_EXPIRES_AT', ''))
        starts = int(os.getenv('CAPSTONE_TEST_PIN_STARTS_AT', ''))
    except ValueError:
        return None
    if not HASH_RE.fullmatch(pin) or (extra and not HASH_RE.fullmatch(extra)):
        return None
    if not (starts <= time.time() < expires and 0 < expires - starts <= 14 * 86400):
        return None
    return Config(pin, extra, expires, starts)


def matches(value, encoded):
    match = HASH_RE.fullmatch(encoded)
    if not match or not isinstance(value, str) or not 1 <= len(value) <= 128:
        return False
    actual = hashlib.scrypt(value.encode(), salt=bytes.fromhex(match[1]), n=16384, r=8, p=1, dklen=32)
    return hmac.compare_digest(actual, bytes.fromhex(match[2]))


def rpc(name, body):
    try:
        return SupabaseStore().rpc(name, body)
    except StorageUnavailable:
        raise HTTPException(503, '테스트 로그인 저장소를 확인할 수 없습니다.') from None


def fingerprint(token):
    return hashlib.sha256(token.encode()).hexdigest()


def login(body):
    cfg = config()
    if not cfg:
        raise HTTPException(503, '테스트 PIN 로그인이 비활성화되었거나 기간이 만료되었습니다.')
    # Always reserve an attempt BEFORE hashing/checking credentials. RPC serializes
    # every worker using a global singleton row; spoofed IPs cannot bypass it.
    allowed = rpc('aleph_test_auth_attempt', {})
    if allowed is not True:
        raise HTTPException(429, '로그인 시도 제한에 도달했습니다. 잠시 후 다시 시도하세요.')
    pin = body.get('pin')
    valid_pin = isinstance(pin, str) and bool(re.fullmatch(r'[0-9]{8,12}', pin))
    pin_ok = matches(pin, cfg.pin_hash) if valid_pin else False
    extra_ok = matches(body.get('access_code'), cfg.extra_hash) if cfg.extra_hash else True
    if not (pin_ok and extra_ok):
        raise HTTPException(401, 'PIN 또는 추가 코드가 올바르지 않습니다.')
    token = secrets.token_urlsafe(32)
    seconds = min(TTL, cfg.expires - int(time.time()))
    if seconds <= 0:
        raise HTTPException(401, '테스트 로그인 기간이 만료되었습니다.')
    result = rpc('aleph_test_auth_session', {'operation': 'create', 'token_hash': fingerprint(token),
                 'config_version': cfg.version, 'lifetime_seconds': seconds})
    if result is not True:
        raise HTTPException(503, '테스트 세션을 생성하지 못했습니다.')
    return token, seconds


def identity(request):
    cfg = config()
    token = request.cookies.get(COOKIE, '')
    if not cfg or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return None
    result = rpc('aleph_test_auth_session', {'operation': 'check', 'token_hash': fingerprint(token),
                 'config_version': cfg.version, 'lifetime_seconds': 0})
    return 'test-pin-operator' if result is True else None


def logout(request):
    token = request.cookies.get(COOKIE, '')
    if re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        rpc('aleph_test_auth_session', {'operation': 'delete', 'token_hash': fingerprint(token),
            'config_version': '', 'lifetime_seconds': 0})


def cookie(response, token='', seconds=0):
    response.set_cookie(COOKIE, token, max_age=seconds, secure=True, httponly=True,
                        samesite='strict', path='/')
