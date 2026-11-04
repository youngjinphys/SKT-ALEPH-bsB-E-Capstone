#!/usr/bin/env python3
"""Run locally: enter a NEW test PIN privately; print only its salted hash."""
import getpass
import hashlib
import re
import secrets


def main():
    print('Use a new random 12-digit PIN. Save it in your password manager, not chat.')
    pin = getpass.getpass('New test PIN (hidden): ')
    if not re.fullmatch(r'[0-9]{12}', pin):
        raise SystemExit('Exactly 12 ASCII digits are required. No configuration was changed.')
    if pin != getpass.getpass('Repeat test PIN (hidden): '):
        raise SystemExit('PINs do not match. No configuration was changed.')
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(pin.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    print('\nPaste only this value into Vercel CAPSTONE_TEST_PIN_HASH (Production, Sensitive):')
    print(f'scrypt${salt.hex()}${digest.hex()}')
    print('Do not send your PIN in chat. This tool stores no files and makes no network requests.')

if __name__ == '__main__':
    main()
