from __future__ import annotations

import pytest

from omniai.security.secrets import SecretBox


def test_round_trip_encrypt_decrypt():
    box = SecretBox("a-secret-key-of-sufficient-length-please")
    cipher = box.encrypt("openai-key-1234567890")
    assert cipher != "openai-key-1234567890"
    assert box.decrypt(cipher) == "openai-key-1234567890"


def test_empty_string_passes_through():
    box = SecretBox("a-secret-key-of-sufficient-length-please")
    assert box.encrypt("") == ""
    assert box.decrypt("") == ""


def test_decrypt_with_wrong_key_raises():
    box_a = SecretBox("first-key-1234567890123456789012")
    box_b = SecretBox("second-key-2222222222222222222222")
    cipher = box_a.encrypt("hello")
    with pytest.raises(ValueError):
        box_b.decrypt(cipher)


def test_decrypt_garbage_raises():
    box = SecretBox("any-key-that-is-long-enough-12345")
    with pytest.raises(ValueError):
        box.decrypt("not-a-real-fernet-token")
