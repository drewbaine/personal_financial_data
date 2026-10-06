"""Encryption for secrets stored in the database (Plaid access tokens)."""

from cryptography.fernet import Fernet


class MissingEncryptionKey(RuntimeError):
    pass


def generate_key() -> str:
    return Fernet.generate_key().decode()


class TokenCipher:
    def __init__(self, key: str):
        if not key:
            raise MissingEncryptionKey("FINANCE_ENCRYPTION_KEY is not set. Generate one with `finance gen-key`.")
        self._fernet = Fernet(key.encode())

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()
