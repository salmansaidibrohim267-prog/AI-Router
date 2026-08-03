"""Cryptographic primitives: AES-256-GCM/CBC, envelope encryption, field and
storage encryption.

All ciphertext is base64 encoded so values stay JSON-safe. Envelope mode wraps
data keys with a master key (from the ``KeyManager``); ``key_provider(key_id,
version)`` is injectable for tests and alternative KMS wiring.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Any, Callable

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .config import SecurityConfig
from .exceptions import DecryptionError, EncryptionError, KeyManagementError
from .logging import SecurityLogger
from .metrics import SecurityMetricsTracker
from .models import EncryptionAlgorithm, EncryptionKey, Envelope

_KeyProvider = Callable[[str, int], EncryptionKey | None]
Data = str | bytes | dict | list | int | float | bool | None


def _encode(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _decode(data: str | bytes) -> bytes:
    return base64.b64decode(data)


class AESCipher:
    """Raw AES-256 encryption supporting GCM (authenticated) and CBC modes."""

    def __init__(
        self,
        algorithm: EncryptionAlgorithm = EncryptionAlgorithm.AES_256_GCM,
        metrics: SecurityMetricsTracker | None = None,
    ) -> None:
        self.algorithm = algorithm
        self.metrics = metrics

    def _key_bytes(self, key: bytes | str) -> bytes:
        if isinstance(key, str):
            key = key.encode()
        return key

    def encrypt(self, plaintext: bytes, key: bytes | str) -> tuple[bytes, bytes, bytes]:
        """Return (ciphertext, iv, tag); CBC mode returns an empty tag."""
        key = self._key_bytes(key)
        iv = os.urandom(16)
        if self.algorithm == EncryptionAlgorithm.AES_256_GCM:
            cipher = Cipher(algorithms.AES(key), modes.GCM(iv))
            encryptor = cipher.encryptor()
            ciphertext = encryptor.update(plaintext) + encryptor.finalize()
            if self.metrics:
                self.metrics.record("encrypt_operations", component="crypto")
            return ciphertext, iv, encryptor.tag
        if self.algorithm == EncryptionAlgorithm.AES_256_CBC:
            pad = 16 - len(plaintext) % 16
            padded = plaintext + bytes([pad]) * pad
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
            encryptor = cipher.encryptor()
            ciphertext = encryptor.update(padded) + encryptor.finalize()
            if self.metrics:
                self.metrics.record("encrypt_operations", component="crypto")
            return ciphertext, iv, b""
        raise EncryptionError(f"unsupported algorithm {getattr(self.algorithm, 'value', self.algorithm)}")

    def decrypt(self, ciphertext: bytes, key: bytes | str, iv: bytes, tag: bytes = b"") -> bytes:
        """Decrypt and authenticate; raises DecryptionError on integrity failure."""
        key = self._key_bytes(key)
        try:
            if self.algorithm == EncryptionAlgorithm.AES_256_GCM:
                cipher = Cipher(algorithms.AES(key), modes.GCM(iv, tag))
                decryptor = cipher.decryptor()
                plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            elif self.algorithm == EncryptionAlgorithm.AES_256_CBC:
                cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
                decryptor = cipher.decryptor()
                padded = decryptor.update(ciphertext) + decryptor.finalize()
                pad = padded[-1]
                if not 1 <= pad <= 16:
                    raise DecryptionError("invalid padding")
                plaintext = padded[:-pad]
            else:
                raise DecryptionError(f"unsupported algorithm {getattr(self.algorithm, 'value', self.algorithm)}")
        except DecryptionError:
            raise
        except Exception as exc:
            raise DecryptionError(f"decryption failed: {exc}") from exc
        if self.metrics:
            self.metrics.record("decrypt_operations", component="crypto")
        return plaintext


class EncryptionService:
    """High-level encryption using a KeyManager (or direct key) with envelope support."""

    def __init__(
        self,
        config: SecurityConfig | None = None,
        cipher: AESCipher | None = None,
        key_provider: _KeyProvider | None = None,
        logger: SecurityLogger | None = None,
        metrics: SecurityMetricsTracker | None = None,
    ) -> None:
        self.config = config if config is not None else SecurityConfig()
        self.cipher = cipher if cipher is not None else AESCipher(EncryptionAlgorithm(self.config.encryption_algorithm))
        self.key_provider = key_provider
        self.logger = logger if logger is not None else SecurityLogger(self.config)
        self.metrics = metrics if metrics is not None else SecurityMetricsTracker(self.config)

    def _resolve_key(self, key_id: str, version: int) -> EncryptionKey:
        if self.key_provider is None:
            raise KeyManagementError("no key provider configured")
        key = self.key_provider(key_id, version)
        if key is None or not key.usable():
            raise KeyManagementError(f"key {key_id} v{version} unavailable")
        return key

    # -- envelope --------------------------------------------------------------

    def envelope_encrypt(self, plaintext: bytes, key: EncryptionKey | None = None) -> Envelope:
        """Encrypt with a data key; in envelope mode wrap it with a master key."""
        data_key = key
        wrapped_key = ""
        if data_key is None:
            if self.key_provider is None:
                raise KeyManagementError("no key provider configured")
            data_key = self._resolve_current()
        if self.config.envelope_enabled:
            master = self._resolve_current()
            wrapped_key = self._wrap_key(data_key.material, master)
        ciphertext, iv, tag = self.cipher.encrypt(plaintext, data_key.material)
        if self.metrics:
            self.metrics.record("envelope_encrypts", component="crypto")
        self.logger.log_event("envelope_encrypted", key_id=data_key.id, version=data_key.version)
        return Envelope(
            key_id=data_key.id,
            key_version=data_key.version,
            algorithm=self.config.encryption_algorithm,
            iv=_encode(iv),
            tag=_encode(tag),
            ciphertext=_encode(ciphertext),
            wrapped_key=wrapped_key,
        )

    def envelope_decrypt(self, envelope: Envelope) -> bytes:
        """Decrypt an envelope, unwrapping the data key when wrapped."""
        key = self.key_provider(envelope.key_id, envelope.key_version) if self.key_provider else None
        if key is None or not key.usable():
            raise KeyManagementError(f"key {envelope.key_id} v{envelope.key_version} unavailable")
        material = key.material
        if envelope.wrapped_key:
            master = self._resolve_current()
            material = self._unwrap_key(envelope.wrapped_key, master)
        try:
            plaintext = self.cipher.decrypt(
                _decode(envelope.ciphertext),
                material,
                _decode(envelope.iv),
                _decode(envelope.tag) if envelope.tag else b"",
            )
        except DecryptionError as exc:
            if self.metrics:
                self.metrics.record("decrypt_failures", component="crypto")
            raise exc
        if self.metrics:
            self.metrics.record("envelope_decrypts", component="crypto")
        return plaintext

    # -- convenience -----------------------------------------------------------

    def encrypt(self, plaintext: bytes, key_id: str = "", version: int = 1) -> Envelope:
        key = None
        if key_id:
            key = self._resolve_key(key_id, version)
        return self.envelope_encrypt(plaintext, key)

    def decrypt(self, envelope: Envelope) -> bytes:
        return self.envelope_decrypt(envelope)

    def _resolve_current(self) -> EncryptionKey:
        key = self.key_provider("current", 0) if self.key_provider else None
        if key is None or not key.usable():
            raise KeyManagementError("no usable current key")
        return key

    def _wrap_key(self, data_key: bytes, master: EncryptionKey) -> str:
        ciphertext, iv, tag = self.cipher.encrypt(data_key, master.material)
        return "|".join([_encode(iv), _encode(tag), _encode(ciphertext)])

    def _unwrap_key(self, wrapped: str, master: EncryptionKey) -> bytes:
        try:
            iv_b64, tag_b64, ciphertext_b64 = wrapped.split("|")
            return self.cipher.decrypt(
                _decode(ciphertext_b64),
                master.material,
                _decode(iv_b64),
                _decode(tag_b64) if tag_b64 else b"",
            )
        except (ValueError, DecryptionError) as exc:
            raise DecryptionError(f"key unwrap failed: {exc}") from exc


class FieldCipher:
    """Encrypts individual data fields while preserving type and shape."""

    def __init__(self, service: EncryptionService | None = None) -> None:
        self.service = service if service is not None else EncryptionService()

    def encrypt_field(self, value: Any, key_id: str = "") -> Any:
        """Encrypt a value; strings/bytes become envelope dicts, containers recurse."""
        if value is None or isinstance(value, (int, float, bool)):
            return value
        if isinstance(value, str):
            envelope = self.service.encrypt(value.encode(), key_id=key_id)
            return {"__enc__": envelope.to_dict()}
        if isinstance(value, bytes):
            envelope = self.service.encrypt(value, key_id=key_id)
            return {"__enc__": envelope.to_dict()}
        if isinstance(value, dict):
            return {k: self.encrypt_field(v, key_id=key_id) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.encrypt_field(v, key_id=key_id) for v in value]
        return self.encrypt_field(str(value), key_id=key_id)

    def decrypt_field(self, value: Any) -> Any:
        """Reverse :meth:`encrypt_field`."""
        if isinstance(value, dict) and set(value) == {"__enc__"}:
            envelope = Envelope.from_dict(value["__enc__"])
            return self.service.decrypt(envelope).decode()
        if isinstance(value, dict):
            return {k: self.decrypt_field(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.decrypt_field(v) for v in value]
        return value


class StorageEncryption:
    """Whole-value encryption for at-rest storage with AAD binding."""

    def __init__(self, service: EncryptionService | None = None, aad: bytes = b"ai-router-storage") -> None:
        self.service = service if service is not None else EncryptionService()
        self.aad = aad

    def encrypt_value(self, value: str, key_id: str = "", purpose: str = "") -> str:
        digest = hmac.new(self.aad, purpose.encode(), hashlib.sha256).digest()
        payload = digest + value.encode()
        envelope = self.service.encrypt(payload, key_id=key_id)
        return envelope.to_dict()

    def decrypt_value(self, wrapped: dict[str, Any] | str) -> str:
        envelope = Envelope.from_dict(wrapped)
        payload = self.service.decrypt(envelope)
        return payload[32:].decode()

    def tamper_detect(self, value: str) -> bytes:
        """HMAC over a value for integrity checks outside the cipher."""
        return hmac.new(self.aad, value.encode(), hashlib.sha256).hexdigest().encode()


def create_encryption_service(config: SecurityConfig | None = None, **overrides: Any) -> EncryptionService:
    config = config if config is not None else SecurityConfig()
    cipher = overrides.pop("cipher", None)
    key_provider = overrides.pop("key_provider", None)
    logger = overrides.pop("logger", None) or SecurityLogger(config)
    metrics = overrides.pop("metrics", None) or SecurityMetricsTracker(config)
    if cipher is None:
        cipher = AESCipher(EncryptionAlgorithm(config.encryption_algorithm), metrics)
    return EncryptionService(config, cipher, key_provider, logger, metrics)
