from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _derive_fernet_key(material: str) -> bytes:
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


class SecretBox:
    def __init__(self, key_material: str) -> None:
        if not key_material:
            raise ValueError("ENCRYPTION_KEY must be set.")
        self._fernet = Fernet(_derive_fernet_key(key_material))

    def encrypt(self, plaintext: str) -> str:
        if plaintext == "":
            return ""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, token: str) -> str:
        if not token:
            return ""
        try:
            return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Failed to decrypt secret material.") from exc
