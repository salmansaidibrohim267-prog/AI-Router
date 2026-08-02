"""Key management: versioned key lifecycle, HSM and KMS adapters.

The ``KeyManager`` owns the current encryption key, supports versioned rotation,
revocation and expiry, and can wrap material in a hardware security module (HSM)
or cloud KMS via injectable adapters. ``key_provider(key_id, version)`` is
exposed for wiring into :mod:`app.security.crypto`.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from abc import ABC, abstractmethod
from typing import Any

from .config import SecurityConfig
from .exceptions import KeyExpiredError, KeyManagementError, KeyRevokedError, KeyVersionError
from .logging import SecurityLogger
from .metrics import SecurityMetricsTracker
from .models import EncryptionAlgorithm, EncryptionKey, KeyPurpose, KeyStatus, generate_id


class HSMAdapter(ABC):
    """Hardware security module adapter protocol."""

    name = "hsm"

    @abstractmethod
    def generate(self, purpose: KeyPurpose) -> bytes:
        """Generate raw key material."""

    @abstractmethod
    def wrap(self, key_id: str, material: bytes) -> bytes:
        """Encrypt key material for transport/storage."""

    @abstractmethod
    def unwrap(self, key_id: str, wrapped: bytes) -> bytes:
        """Decrypt previously wrapped key material."""

    @abstractmethod
    def destroy(self, key_id: str) -> None:
        """Destroy material permanently."""


class SimulatedHSMAdapter(HSMAdapter):
    """In-process HSM emulation (XOR cipher with a device secret) for tests
    and non-hardened deployments. Never use in production."""

    name = "simulated"

    def __init__(self, device_secret: bytes = b"simulated-hsm-device-secret") -> None:
        self._secret = device_secret

    def generate(self, purpose: KeyPurpose) -> bytes:
        return os.urandom(32)

    def _xor(self, data: bytes) -> bytes:
        secret = self._secret
        result = bytearray(len(data))
        for i, byte in enumerate(data):
            result[i] = byte ^ secret[i % len(secret)]
        return bytes(result)

    def wrap(self, key_id: str, material: bytes) -> bytes:
        mac = hmac.new(self._secret, key_id.encode() + material, hashlib.sha256).digest()
        return self._xor(material) + b"\x00" + mac

    def unwrap(self, key_id: str, wrapped: bytes) -> bytes:
        payload, _sep, mac = wrapped.rpartition(b"\x00")
        material = self._xor(payload)
        expected = hmac.new(self._secret, key_id.encode() + material, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected):
            raise KeyManagementError("HSM unwrap integrity check failed")
        return material

    def destroy(self, key_id: str) -> None:
        return None


class KMSAdapter:
    """Cloud KMS adapter wrapping an injectable client.

    ``client`` must expose ``encrypt(key_id, plaintext) -> bytes``,
    ``decrypt(key_id, ciphertext) -> bytes``, ``generate(key_id) -> bytes`` and
    ``destroy(key_id)``.
    """

    name = "kms"

    def __init__(self, client: Any = None) -> None:
        self.client = client
        if client is None:
            raise KeyManagementError("kms adapter requires an injected client")

    def generate(self, purpose: KeyPurpose) -> bytes:
        return self.client.generate(purpose.value)

    def wrap(self, key_id: str, material: bytes) -> bytes:
        return self.client.encrypt(key_id, material)

    def unwrap(self, key_id: str, wrapped: bytes) -> bytes:
        return self.client.decrypt(key_id, wrapped)

    def destroy(self, key_id: str) -> None:
        self.client.destroy(key_id)


class KeyManager:
    """Versioned encryption key lifecycle with optional HSM/KMS backing."""

    def __init__(
        self,
        config: SecurityConfig | None = None,
        hsm: HSMAdapter | None = None,
        logger: SecurityLogger | None = None,
        metrics: SecurityMetricsTracker | None = None,
    ) -> None:
        self.config = config if config is not None else SecurityConfig()
        self.hsm = hsm
        self.logger = logger if logger is not None else SecurityLogger(self.config)
        self.metrics = metrics if metrics is not None else SecurityMetricsTracker(self.config)
        self._keys: dict[str, EncryptionKey] = {}
        self._current_id = ""
        self._ensure_initial_key()

    # -- lifecycle -------------------------------------------------------------

    def _ensure_initial_key(self) -> None:
        if not self._current_id:
            self.rotate()

    def generate_material(self, purpose: KeyPurpose) -> bytes:
        if self.hsm is not None:
            return self.hsm.generate(purpose)
        return os.urandom(32)

    def rotate(self) -> EncryptionKey:
        """Create a new current key and retire the previous one."""
        algorithm = EncryptionAlgorithm(self.config.encryption_algorithm)
        version = 1
        if self._current_id:
            previous = self._keys[self._current_id]
            version = previous.version + 1
            if previous.status == KeyStatus.ACTIVE:
                previous.status = KeyStatus.RETIRED
                previous.rotated_at = time.time()
        key = EncryptionKey(
            id=generate_id("key"),
            purpose=KeyPurpose.ENCRYPTION,
            algorithm=algorithm,
            material=self.generate_material(KeyPurpose.ENCRYPTION),
            version=version,
        )
        self._keys[key.id] = key
        self._current_id = key.id
        self.metrics.record("key_rotations", component="keys")
        self.logger.log_event("key_rotated", key_id=key.id, version=version)
        return key

    def rotate_with_material(self, material: bytes) -> EncryptionKey:
        key = self.rotate()
        key.material = material
        return key

    def revoke(self, key_id: str) -> bool:
        key = self._keys.get(key_id)
        if key is None:
            return False
        key.status = KeyStatus.REVOKED
        key.revoked_at = time.time()
        if key.id == self._current_id:
            self.rotate()
        self.metrics.record("key_revocations", component="keys")
        self.logger.log_event("key_revoked", key_id=key_id)
        return True

    def expire(self, key_id: str) -> bool:
        key = self._keys.get(key_id)
        if key is None:
            return False
        key.status = KeyStatus.EXPIRED
        key.expires_at = time.time()
        if key.id == self._current_id:
            self.rotate()
        return True

    def destroy(self, key_id: str) -> bool:
        key = self._keys.get(key_id)
        if key is None:
            return False
        if self.hsm is not None:
            self.hsm.destroy(key_id)
        if key.id == self._current_id:
            self._current_id = ""
            self.rotate()
        key.status = KeyStatus.DESTROYED
        key.material = b""
        self.metrics.record("key_destroys", component="keys")
        return True

    # -- lookup ----------------------------------------------------------------

    def get_key(self, key_id: str) -> EncryptionKey | None:
        return self._keys.get(key_id)

    def current_key(self) -> EncryptionKey:
        if not self._current_id:
            raise KeyManagementError("no current key")
        return self._keys[self._current_id]

    def keys(self) -> list[EncryptionKey]:
        return list(self._keys.values())

    def find_by_version(self, version: int) -> EncryptionKey | None:
        for key in self._keys.values():
            if key.version == version:
                return key
        return None

    def key_provider(self, key_id: str, version: int) -> EncryptionKey | None:
        """Wires into EncryptionService: resolves a usable key by id+version."""
        if key_id == "current":
            key = self.current_key()
        else:
            key = self._keys.get(key_id)
            if key is not None and version and key.version != version:
                raise KeyVersionError(f"key {key_id} version mismatch: expected {version}")
        if key is None:
            return None
        if key.status == KeyStatus.REVOKED:
            raise KeyRevokedError(f"key {key.id} revoked")
        if key.status == KeyStatus.EXPIRED or key.is_expired():
            raise KeyExpiredError(f"key {key.id} expired")
        return key if key.usable() else None

    # -- policies --------------------------------------------------------------

    def auto_rotation_due(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        key = self.current_key()
        if self.config.key_rotation_days <= 0:
            return False
        return bool(key and now - key.created_at >= self.config.key_rotation_days * 86400)

    def enforce_rotation(self, now: float | None = None) -> bool:
        """Rotate when the current key passed its configured lifetime."""
        if self.auto_rotation_due(now):
            self.rotate()
            return True
        return False

    def status(self) -> dict[str, Any]:
        return {
            "key_count": len(self._keys),
            "current_key_id": self._current_id,
            "current_version": self.current_key().version if self._current_id else 0,
            "hsm": self.hsm.name if self.hsm is not None else None,
            "rotation_days": self.config.key_rotation_days,
        }


def create_key_manager(config: SecurityConfig | None = None, **overrides: Any) -> KeyManager:
    config = config if config is not None else SecurityConfig()
    hsm = overrides.pop("hsm", None)
    logger = overrides.pop("logger", None) or SecurityLogger(config)
    metrics = overrides.pop("metrics", None) or SecurityMetricsTracker(config)
    return KeyManager(config, hsm, logger, metrics)
