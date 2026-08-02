"""Tests for the app.security package (Stage 10.9)."""

from __future__ import annotations

import base64
import os
import time

import pytest

from app.security import (
    AWSSecretsBackend,
    AuditRepository,
    AuditService,
    AuditEventType,
    AuditSeverity,
    AuthContext,
    AuthMethod,
    AzureBackend,
    ComplianceFramework,
    ComplianceManager,
    ControlStatus,
    DataSubjectRequestStatus,
    DataSubjectRequestType,
    Decision,
    DecryptionError,
    EncryptionAlgorithm,
    EncryptionKey,
    EncryptionService,
    Envelope,
    EnvironmentBackend,
    FieldCipher,
    GoogleBackend,
    HSMAdapter,
    IncidentStatus,
    IncidentManager,
    KeyExpiredError,
    KeyManagementError,
    KeyManager,
    KeyRevokedError,
    KeyVersionError,
    KMSAdapter,
    KeyPurpose,
    KeyStatus,
    KubernetesBackend,
    MonitoringService,
    PIIDetector,
    PIIKind,
    Policy,
    PolicyEffect,
    PolicyResult,
    PrivacyService,
    Secret,
    SecretBackendError,
    SecretKind,
    SecretManager,
    SecretNotFoundError,
    SecurityAlert,
    SecurityConfig,
    SecurityLogger,
    SecurityManager,
    SecurityMetricsTracker,
    Session,
    SessionStatus,
    SimulatedHSMAdapter,
    SplunkSink,
    StdoutSink,
    StorageEncryption,
    Subject,
    TenantValidationError,
    ThreatDetector,
    ThreatEvent,
    ThreatSeverity,
    ThreatType,
    VaultBackend,
    ZeroTrustEnforcer,
    create_audit_service,
    create_compliance_manager,
    create_encryption_service,
    create_incident_manager,
    create_key_manager,
    create_monitoring_service,
    create_privacy_service,
    create_secret_manager,
    create_security_manager,
    create_threat_detector,
    create_zero_trust_enforcer,
    generate_id,
)
from app.security.audit import AuditIntegrityError
from app.security.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ComplianceError,
    DataSubjectRequestError,
    IncidentError,
    MonitoringError,
    PolicyEvaluationError,
    SecurityError,
    SessionValidationError,
)
from app.security.monitoring import DatadogSink, ElasticSink, SiemRegistry
from app.security.privacy import MaskedResult
from app.security.secrets import SecretBackendRegistry, create_secret_backend
from app.security.threat import ThreatError
from app.security.zero_trust import CredentialValidator


def make_config(**kwargs):
    return SecurityConfig(**kwargs)


def make_logger(config=None):
    return SecurityLogger(config or make_config())


def make_metrics(config=None):
    return SecurityMetricsTracker(config or make_config())


def make_secret(name="db-password", value="s3cr3t", **kwargs):
    return Secret(id=generate_id("secret"), name=name, value=value, **kwargs)


class FakeVaultTransport:
    def __init__(self):
        self.store: dict[str, dict] = {}
        self.calls = []
        self.fail = None

    async def __call__(self, backend, method, url, body=None):
        self.calls.append((method, url))
        if self.fail:
            raise self.fail
        if method == "GET":
            name = url.rsplit("/", 1)[-1]
            if name not in self.store:
                return {}
            return {"data": {"data": dict(self.store[name])}}
        if method in ("POST", "PUT"):
            name = url.rsplit("/", 1)[-1]
            self.store[name] = body.get("data", body)
            return {"data": {}}
        if method == "DELETE":
            name = url.rsplit("/", 1)[-1]
            self.store.pop(name, None)
            return {"data": {}}
        if method == "LIST":
            return {"data": {"keys": sorted(self.store)}}
        return {}


class FakeKubeTransport:
    def __init__(self):
        self.store: dict[str, dict] = {}
        self.fail = None

    async def __call__(self, backend, method, url, body=None):
        if self.fail:
            raise self.fail
        if url.endswith("/secrets"):
            return {"items": [{"metadata": {"name": n}} for n in self.store]}
        name = url.rsplit("/", 1)[-1]
        if method == "GET":
            if name not in self.store:
                return {}
            return {
                "data": {
                    "value": base64.b64encode(self.store[name]["value"].encode()).decode(),
                    "kind": self.store[name]["kind"],
                }
            }
        if method in ("POST", "PUT"):
            self.store[name] = dict(body.get("stringData") or {"value": body["value"], "kind": "opaque"})
            return {"data": {}}
        if method == "DELETE":
            self.store.pop(name, None)
            return {"data": {}}


class FakeAWSClient:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.fail = None

    def get_secret_value(self, SecretId):
        if self.fail:
            raise self.fail
        if SecretId not in self.store:
            raise KeyError(SecretId)
        return {"SecretString": self.store[SecretId]}

    def create_secret(self, Name, SecretString):
        if self.fail:
            raise self.fail
        self.store[Name] = SecretString

    def delete_secret(self, SecretId):
        if self.fail:
            raise self.fail
        self.store.pop(SecretId, None)

    def list_secrets(self):
        if self.fail:
            raise self.fail
        return {"SecretList": [{"Name": n} for n in self.store]}


class FakeAzureTransport:
    def __init__(self):
        self.store: dict[str, dict] = {}

    async def __call__(self, backend, method, url, body=None):
        path = url.split("?")[0]
        name = path.rsplit("/", 1)[-1]
        if path.endswith("/secrets") and method == "GET":
            return {"value": [{"id": f"https://vault/secrets/{n}"} for n in self.store]}
        if method == "GET":
            if name not in self.store:
                return {}
            return dict(self.store[name])
        if method in ("PUT", "POST"):
            self.store[name] = dict(body)
            return {"value": body["value"]}
        if method == "DELETE":
            self.store.pop(name, None)
            return {}
        return {}


class FakeGoogleClient:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.fail = None

    def access_secret_version(self, request):
        if self.fail:
            raise self.fail
        name = request["name"]
        key = name.split("/")[3]
        if key not in self.store:
            raise KeyError(key)
        return {"payload": {"data": base64.b64encode(self.store[key].encode()).decode()}}

    def create_secret(self, request):
        pass

    def add_secret_version(self, request):
        if self.fail:
            raise self.fail
        name = request["parent"]
        key = name.split("/")[3]
        self.store[key] = base64.b64decode(request["payload"]["data"].encode()).decode()

    def delete_secret(self, request):
        if self.fail:
            raise self.fail
        self.store.pop(request["name"].split("/")[3], None)

    def list_secrets(self, request):
        if self.fail:
            raise self.fail
        return {"secrets": [{"name": f"projects/{request['parent']}/secrets/{k}"} for k in self.store]}


class FakeKMSClient:
    def __init__(self):
        self.wrapped: dict[str, bytes] = {}
        self.generated: list[str] = []
        self.destroyed: list[str] = []

    def encrypt(self, key_id, plaintext):
        self.wrapped[key_id] = plaintext
        return b"kms-wrapped:" + plaintext

    def decrypt(self, key_id, ciphertext):
        return ciphertext.replace(b"kms-wrapped:", b"")

    def generate(self, purpose):
        self.generated.append(purpose)
        return os.urandom(32)

    def destroy(self, key_id):
        self.destroyed.append(key_id)


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


class TestSecurityConfig:
    def test_defaults(self):
        config = make_config()
        assert config.secret_backend == "environment"
        assert config.encryption_algorithm == "aes-256-gcm"
        assert config.envelope_enabled is True
        assert config.zero_trust_enforce is True
        assert config.audit_immutable is True
        assert config.audit_hash_secret == "audit-chain-secret"
        assert config.audit_retention_days == 365
        assert config.pii_masking_mode == "partial"
        assert config.siem_backend == "stdout"

    def test_unknown_kwargs_rejected(self):
        with pytest.raises(TypeError):
            make_config(bogus_option=1)

    def test_as_dict_roundtrip(self):
        config = make_config(node_id="n1")
        as_dict = config.as_dict()
        assert as_dict["node_id"] == "n1"
        assert as_dict["secret_backend"] == "environment"
        assert "secret_config" in as_dict
        rebuilt = SecurityConfig(**as_dict)
        assert rebuilt.node_id == "n1"

    def test_node_id_override_keeps_rest(self):
        config = make_config()
        rebuilt = SecurityConfig(**{**config.as_dict(), "node_id": "node-other"})
        assert rebuilt.node_id == "node-other"
        assert rebuilt.secret_backend == config.secret_backend

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("SEC_SECRET_BACKEND", "vault")
        monkeypatch.setenv("SEC_MAX_SESSION_AGE_SECONDS", "120")
        config = SecurityConfig.from_env()
        assert config.secret_backend == "vault"
        assert config.max_session_age_seconds == 120

    def test_from_env_defaults(self, monkeypatch):
        monkeypatch.delenv("SEC_SECRET_BACKEND", raising=False)
        config = SecurityConfig.from_env()
        assert config.secret_backend == "environment"

    def test_secret_config_passthrough(self):
        config = make_config(secret_config={"address": "http://vault:8200"})
        assert config.secret_config["address"] == "http://vault:8200"


# ---------------------------------------------------------------------------
# logging + metrics
# ---------------------------------------------------------------------------


class TestSecurityLogger:
    def test_log_event_prefix(self):
        logger = make_logger()
        logger.log_event("secret_read", name="x")
        assert logger.events[-1]["event"] == "security_secret_read"
        assert logger.events[-1]["data"]["name"] == "x"

    def test_ring_buffer_limited(self):
        logger = make_logger(make_config(log_events=True))
        for i in range(1050):
            logger.log_event(f"e{i}")
        assert len(logger.events) == 1000

    def test_log_events_disabled(self):
        logger = make_logger(make_config(log_events=False))
        logger.log_event("silent")
        assert logger.events == []


class TestSecurityMetricsTracker:
    def test_record_and_counts(self):
        metrics = make_metrics()
        metrics.record("reads", component="secrets")
        metrics.record("reads", component="secrets")
        assert metrics.counts()["reads"] == 2

    def test_by_component(self):
        metrics = make_metrics()
        metrics.record("a", component="x")
        metrics.record("b", component="y")
        assert metrics.by_component()["x"]["a"] == 1

    def test_summary(self):
        metrics = make_metrics()
        metrics.record("a", component="x", amount=3)
        summary = metrics.summary()
        assert summary["counts"]["a"] == 3


# ---------------------------------------------------------------------------
# secrets
# ---------------------------------------------------------------------------


class TestEnvironmentBackend:
    def test_get_set_delete_list(self, monkeypatch):
        backend = EnvironmentBackend(make_config(secret_config={"prefix": "TESTSEC_"}))
        monkeypatch.setenv("TESTSEC_FOO", "bar")
        secret = asyncio_run(backend.get("TESTSEC_FOO"))
        assert secret.value == "bar"
        assert secret.name == "TESTSEC_FOO"

        stored = asyncio_run(backend.set(make_secret(name="TESTSEC_NEW", value="v")))
        assert stored.value == "v"
        assert os.environ.get("TESTSEC_NEW") == "v"

        names = asyncio_run(backend.list())
        assert "TESTSEC_FOO" in names

        assert asyncio_run(backend.delete("TESTSEC_NEW")) is True
        assert asyncio_run(backend.delete("TESTSEC_NEW")) is False

    def test_get_missing_raises(self):
        backend = EnvironmentBackend(make_config())
        with pytest.raises(SecretNotFoundError):
            asyncio_run(backend.get("SEC_TOTALLY_MISSING_VAR"))

    def test_set_creates_env(self, monkeypatch):
        backend = EnvironmentBackend(make_config())
        asyncio_run(backend.set(make_secret(name="TMP_TEST_SEC_VAR", value="v")))
        assert os.environ["TMP_TEST_SEC_VAR"] == "v"
        monkeypatch.delenv("TMP_TEST_SEC_VAR", raising=False)


class TestVaultBackend:
    def test_get_set_list_delete(self):
        transport = FakeVaultTransport()
        backend = VaultBackend(make_config(secret_config={"address": "http://v:8200"}), transport=transport)
        asyncio_run(backend.set(make_secret(name="db", value="pw", kind=SecretKind.DATABASE)))
        secret = asyncio_run(backend.get("db"))
        assert secret.value == "pw"
        assert secret.kind == SecretKind.DATABASE
        assert asyncio_run(backend.list()) == ["db"]
        assert asyncio_run(backend.delete("db")) is True
        with pytest.raises(SecretNotFoundError):
            asyncio_run(backend.get("db"))

    def test_transport_failure_raises(self):
        transport = FakeVaultTransport()
        transport.fail = RuntimeError("down")
        backend = VaultBackend(make_config(), transport=transport)
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.get("x"))

    def test_missing_secret_raises_not_found(self):
        backend = VaultBackend(make_config(), transport=FakeVaultTransport())
        with pytest.raises(SecretNotFoundError):
            asyncio_run(backend.get("absent"))


class TestKubernetesBackend:
    def test_get_set_list_delete(self):
        transport = FakeKubeTransport()
        backend = KubernetesBackend(make_config(), transport=transport)
        asyncio_run(backend.set(make_secret(name="kube-sec", value="val")))
        secret = asyncio_run(backend.get("kube-sec"))
        assert secret.value == "val"
        assert asyncio_run(backend.list()) == ["kube-sec"]
        assert asyncio_run(backend.delete("kube-sec")) is True

    def test_missing_raises(self):
        backend = KubernetesBackend(make_config(), transport=FakeKubeTransport())
        with pytest.raises(SecretNotFoundError):
            asyncio_run(backend.get("absent"))


class TestAWSBackend:
    def test_get_set_list_delete(self):
        client = FakeAWSClient()
        backend = AWSSecretsBackend(make_config(), client=client)
        asyncio_run(backend.set(make_secret(name="aws-sec", value="v")))
        secret = asyncio_run(backend.get("aws-sec"))
        assert secret.value == "v"
        assert asyncio_run(backend.list()) == ["aws-sec"]
        assert asyncio_run(backend.delete("aws-sec")) is True

    def test_requires_client(self):
        backend = AWSSecretsBackend(make_config())
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.get("x"))

    def test_missing_raises(self):
        client = FakeAWSClient()
        backend = AWSSecretsBackend(make_config(), client=client)
        with pytest.raises(SecretNotFoundError):
            asyncio_run(backend.get("absent"))

    def test_client_failure_raises(self):
        client = FakeAWSClient()
        client.fail = RuntimeError("nope")
        backend = AWSSecretsBackend(make_config(), client=client)
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.list())


class TestAzureBackend:
    def test_get_set_list_delete(self):
        transport = FakeAzureTransport()
        backend = AzureBackend(make_config(), transport=transport)
        asyncio_run(backend.set(make_secret(name="az-sec", value="v")))
        secret = asyncio_run(backend.get("az-sec"))
        assert secret.value == "v"
        assert "az-sec" in asyncio_run(backend.list())
        assert asyncio_run(backend.delete("az-sec")) is True

    def test_missing_raises(self):
        backend = AzureBackend(make_config(), transport=FakeVaultTransport())
        with pytest.raises(SecretNotFoundError):
            asyncio_run(backend.get("absent"))


class TestGoogleBackend:
    def test_get_set_list_delete(self):
        client = FakeGoogleClient()
        backend = GoogleBackend(make_config(), client=client)
        asyncio_run(backend.set(make_secret(name="gcp-sec", value="v")))
        secret = asyncio_run(backend.get("gcp-sec"))
        assert secret.value == "v"
        assert asyncio_run(backend.list()) == ["gcp-sec"]
        assert asyncio_run(backend.delete("gcp-sec")) is True

    def test_requires_client(self):
        backend = GoogleBackend(make_config())
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.get("x"))


class TestSecretBackendRegistry:
    def test_create_all_backends(self):
        registry = SecretBackendRegistry()
        config = make_config()
        assert isinstance(registry.create(config), EnvironmentBackend)
        assert isinstance(registry.create(make_config(secret_backend="vault")), VaultBackend)
        assert isinstance(registry.create(make_config(secret_backend="kubernetes")), KubernetesBackend)
        assert isinstance(registry.create(make_config(secret_backend="aws")), AWSSecretsBackend)
        assert isinstance(registry.create(make_config(secret_backend="azure")), AzureBackend)
        assert isinstance(registry.create(make_config(secret_backend="google")), GoogleBackend)

    def test_unknown_backend_raises(self):
        with pytest.raises(SecretBackendError):
            SecretBackendRegistry().create(make_config(secret_backend="nope"))

    def test_register_custom(self):
        registry = SecretBackendRegistry()
        registry.register("custom", lambda config, **kw: EnvironmentBackend(config))
        assert isinstance(registry.create(make_config(secret_backend="custom")), EnvironmentBackend)

    def test_create_secret_backend_di(self):
        assert isinstance(create_secret_backend(make_config()), EnvironmentBackend)


class TestSecretManager:
    def test_get_set_rotate_delete(self):
        manager = create_secret_manager(make_config())
        stored = asyncio_run(manager.set_secret("k1", "v1"))
        assert stored.value == "v1"
        secret = asyncio_run(manager.get_secret("k1"))
        assert secret.value == "v1"
        rotated = asyncio_run(manager.rotate_secret("k1", "v2"))
        assert rotated.value == "v2"
        assert rotated.version == 2
        assert asyncio_run(manager.get_secret("k1", bypass_cache=True)).value == "v2"
        assert asyncio_run(manager.delete_secret("k1")) is True
        with pytest.raises(SecretNotFoundError):
            asyncio_run(manager.get_secret("k1", bypass_cache=True))

    def test_cache_ttl(self):
        manager = create_secret_manager(make_config(secret_cache_ttl=0.001))
        asyncio_run(manager.set_secret("c1", "v"))
        os.environ.pop("c1", None)
        time.sleep(0.01)
        with pytest.raises(SecretNotFoundError):
            asyncio_run(manager.get_secret("c1"))

    def test_rotate_missing_creates(self):
        manager = create_secret_manager(make_config())
        rotated = asyncio_run(manager.rotate_secret("brand-new", "nv"))
        assert rotated.version == 1
        assert rotated.value == "nv"

    def test_rotate_missing_current_ok(self):
        manager = create_secret_manager(make_config())
        asyncio_run(manager.rotate_secret("new2", "nv"))
        assert asyncio_run(manager.get_secret("new2")).value == "nv"

    def test_list_secrets(self, monkeypatch):
        manager = create_secret_manager(make_config(secret_config={"prefix": "LISTP_"}))
        monkeypatch.setenv("LISTP_A", "1")
        names = asyncio_run(manager.list_secrets())
        assert "LISTP_A" in names

    def test_start_stop(self):
        manager = create_secret_manager(make_config())
        asyncio_run(manager.start())
        asyncio_run(manager.start())
        assert manager.status()["running"] is True
        asyncio_run(manager.stop())
        asyncio_run(manager.stop())
        assert manager.status()["running"] is False

    def test_unknown_backend_raises(self):
        with pytest.raises(SecretBackendError):
            create_secret_manager(make_config(secret_backend="nope"))


# ---------------------------------------------------------------------------
# crypto
# ---------------------------------------------------------------------------


class TestAESCipher:
    def test_gcm_roundtrip(self):
        from app.security.crypto import AESCipher

        cipher = AESCipher(EncryptionAlgorithm.AES_256_GCM)
        key = b"k" * 32
        ct, iv, tag = cipher.encrypt(b"hello world", key)
        assert cipher.decrypt(ct, key, iv, tag) == b"hello world"

    def test_gcm_tamper_detected(self):
        from app.security.crypto import AESCipher

        cipher = AESCipher(EncryptionAlgorithm.AES_256_GCM)
        key = b"k" * 32
        ct, iv, tag = cipher.encrypt(b"hello", key)
        tampered = bytearray(ct)
        tampered[0] ^= 0xFF
        with pytest.raises(DecryptionError):
            cipher.decrypt(bytes(tampered), key, iv, tag)

    def test_cbc_roundtrip(self):
        from app.security.crypto import AESCipher

        cipher = AESCipher(EncryptionAlgorithm.AES_256_CBC)
        key = b"k" * 32
        ct, iv, _tag = cipher.encrypt(b"block data", key)
        assert cipher.decrypt(ct, key, iv) == b"block data"

    def test_cbc_short_payload(self):
        from app.security.crypto import AESCipher

        cipher = AESCipher(EncryptionAlgorithm.AES_256_CBC)
        key = b"k" * 32
        ct, iv, _ = cipher.encrypt(b"", key)
        assert cipher.decrypt(ct, key, iv) == b""

    def test_invalid_algorithm(self):
        from app.security.crypto import AESCipher

        from app.security.exceptions import DecryptionError, EncryptionError

        cipher = AESCipher("bogus")  # type: ignore[arg-type]
        with pytest.raises(EncryptionError):
            cipher.encrypt(b"x", b"k" * 32)
        with pytest.raises(DecryptionError):
            cipher.decrypt(b"x", b"k" * 32, b"i" * 16)

    def test_str_key(self):
        from app.security.crypto import AESCipher

        cipher = AESCipher(EncryptionAlgorithm.AES_256_GCM)
        key = "0123456789abcdef0123456789abcdef"
        ct, iv, tag = cipher.encrypt(b"x", key)
        assert cipher.decrypt(ct, key, iv, tag) == b"x"

    def test_gcm_missing_tag_rejected(self):
        from app.security.crypto import AESCipher

        cipher = AESCipher(EncryptionAlgorithm.AES_256_GCM)
        key = b"k" * 32
        ct, iv, _ = cipher.encrypt(b"data", key)
        with pytest.raises(DecryptionError):
            cipher.decrypt(ct, key, iv, b"")


class TestEncryptionService:
    def make_service(self, **config_kwargs):
        key_manager = create_key_manager(make_config(**config_kwargs))
        config = key_manager.config
        service = create_encryption_service(config, key_provider=key_manager.key_provider)
        return key_manager, service

    def test_envelope_encrypt_decrypt(self):
        key_manager, service = self.make_service()
        envelope = service.envelope_encrypt(b"top secret")
        assert envelope.key_id == key_manager.current_key().id
        assert envelope.wrapped_key
        assert service.envelope_decrypt(envelope) == b"top secret"

    def test_no_envelope(self):
        _km, service = self.make_service(envelope_enabled=False)
        envelope = service.envelope_encrypt(b"plainish")
        assert envelope.wrapped_key == ""
        assert service.envelope_decrypt(envelope) == b"plainish"

    def test_roundtrip_with_key_id(self):
        key_manager, service = self.make_service()
        key = key_manager.rotate()
        envelope = service.encrypt(b"data", key_id=key.id, version=key.version)
        assert service.decrypt(envelope) == b"data"

    def test_encrypt_missing_key_raises(self):
        _km, service = self.make_service()
        with pytest.raises(KeyManagementError):
            service.encrypt(b"x", key_id="does-not-exist")

    def test_no_key_provider_raises(self):
        service = EncryptionService(make_config())
        with pytest.raises(KeyManagementError):
            service.envelope_encrypt(b"x")

    def test_decrypt_tampered_ciphertext(self):
        key_manager, service = self.make_service()
        envelope = service.envelope_encrypt(b"secret")
        envelope.ciphertext = base64.b64encode(b"\x00" * 8).decode()
        with pytest.raises(DecryptionError):
            service.envelope_decrypt(envelope)

    def test_decrypt_revoked_key(self):
        key_manager, service = self.make_service()
        envelope = service.envelope_encrypt(b"secret")
        key_manager.revoke(envelope.key_id)
        with pytest.raises(KeyManagementError):
            service.envelope_decrypt(envelope)

    def test_decrypt_no_provider(self):
        service = EncryptionService(make_config())
        envelope = Envelope(
            key_id="k1", key_version=1, algorithm="aes-256-gcm",
            iv=base64.b64encode(b"i" * 16).decode(), tag="", ciphertext=base64.b64encode(b"c").decode(),
        )
        with pytest.raises(KeyManagementError):
            service.envelope_decrypt(envelope)

    def test_unwrap_corrupt(self):
        key_manager, service = self.make_service()
        envelope = service.envelope_encrypt(b"secret")
        envelope.wrapped_key = "garbage"
        with pytest.raises(DecryptionError):
            service.envelope_decrypt(envelope)


class TestFieldCipher:
    def test_string_roundtrip(self):
        key_manager = create_key_manager(make_config())
        service = create_encryption_service(key_manager.config, key_provider=key_manager.key_provider)
        field = FieldCipher(service)
        wrapped = field.encrypt_field("secret-value")
        assert isinstance(wrapped, dict) and "__enc__" in wrapped
        assert field.decrypt_field(wrapped) == "secret-value"

    def test_scalars_passthrough(self):
        key_manager = create_key_manager(make_config())
        service = create_encryption_service(key_manager.config, key_provider=key_manager.key_provider)
        field = FieldCipher(service)
        assert field.encrypt_field(None) is None
        assert field.encrypt_field(42) == 42
        assert field.encrypt_field(1.5) == 1.5
        assert field.encrypt_field(True) is True

    def test_dict_and_list_roundtrip(self):
        key_manager = create_key_manager(make_config())
        service = create_encryption_service(key_manager.config, key_provider=key_manager.key_provider)
        field = FieldCipher(service)
        payload = {"user": "alice@x.com", "tags": ["a", "b"], "nested": {"x": "y"}}
        wrapped = field.encrypt_field(payload)
        assert field.decrypt_field(wrapped) == payload

    def test_bytes_roundtrip(self):
        key_manager = create_key_manager(make_config())
        service = create_encryption_service(key_manager.config, key_provider=key_manager.key_provider)
        field = FieldCipher(service)
        assert field.decrypt_field(field.encrypt_field(b"\x00\x01")) == "\x00\x01"


class TestStorageEncryption:
    def test_roundtrip(self):
        key_manager = create_key_manager(make_config())
        service = create_encryption_service(key_manager.config, key_provider=key_manager.key_provider)
        storage = StorageEncryption(service)
        wrapped = storage.encrypt_value("stored-value")
        assert isinstance(wrapped, dict)
        assert storage.decrypt_value(wrapped) == "stored-value"

    def test_purpose_binding(self):
        key_manager = create_key_manager(make_config())
        service = create_encryption_service(key_manager.config, key_provider=key_manager.key_provider)
        storage = StorageEncryption(service)
        wrapped = storage.encrypt_value("v", purpose="tenant-1")
        assert storage.decrypt_value(wrapped) == "v"

    def test_tamper_detect(self):
        key_manager = create_key_manager(make_config())
        service = create_encryption_service(key_manager.config, key_provider=key_manager.key_provider)
        storage = StorageEncryption(service)
        digest = storage.tamper_detect("value")
        assert digest == storage.tamper_detect("value")
        assert digest != storage.tamper_detect("other")


# ---------------------------------------------------------------------------
# keys
# ---------------------------------------------------------------------------


class TestKeyManager:
    def test_initial_key_created(self):
        km = create_key_manager(make_config())
        assert km.current_key().usable()
        assert km.current_key().version == 1

    def test_rotation_increments_version(self):
        km = create_key_manager(make_config())
        first = km.current_key()
        second = km.rotate()
        assert second.version == 2
        assert first.status == KeyStatus.RETIRED
        assert first.rotated_at > 0

    def test_find_by_version(self):
        km = create_key_manager(make_config())
        km.rotate()
        assert km.find_by_version(2).version == 2
        assert km.find_by_version(99) is None

    def test_revoke_rotates_current(self):
        km = create_key_manager(make_config())
        current = km.current_key()
        assert km.revoke(current.id) is True
        assert km.current_key().id != current.id
        assert current.status == KeyStatus.REVOKED
        assert km.revoke("missing") is False

    def test_expire(self):
        km = create_key_manager(make_config())
        current = km.current_key()
        km.expire(current.id)
        assert km.current_key().id != current.id

    def test_destroy(self):
        km = create_key_manager(make_config())
        current = km.current_key()
        assert km.destroy(current.id) is True
        assert km.current_key().id != current.id
        assert current.status == KeyStatus.DESTROYED
        assert current.material == b""
        assert km.destroy("missing") is False

    def test_key_provider_lookup(self):
        km = create_key_manager(make_config())
        key = km.current_key()
        assert km.key_provider(key.id, key.version) is key
        assert km.key_provider("current", 0) is key
        assert km.key_provider("missing", 1) is None

    def test_key_provider_version_mismatch(self):
        km = create_key_manager(make_config())
        key = km.current_key()
        with pytest.raises(KeyVersionError):
            km.key_provider(key.id, 99)

    def test_key_provider_revoked(self):
        km = create_key_manager(make_config())
        key = km.current_key()
        km.revoke(key.id)
        with pytest.raises(KeyRevokedError):
            km.key_provider(key.id, key.version)

    def test_key_provider_expired(self):
        km = create_key_manager(make_config())
        key = km.current_key()
        key.expires_at = time.time() - 1
        with pytest.raises(KeyExpiredError):
            km.key_provider(key.id, key.version)

    def test_auto_rotation_due(self):
        km = create_key_manager(make_config(key_rotation_days=90))
        assert km.auto_rotation_due() is False
        key = km.current_key()
        key.created_at = time.time() - 91 * 86400
        assert km.auto_rotation_due() is True

    def test_auto_rotation_disabled(self):
        km = create_key_manager(make_config(key_rotation_days=0))
        assert km.auto_rotation_due() is False

    def test_enforce_rotation(self):
        km = create_key_manager(make_config(key_rotation_days=1))
        key = km.current_key()
        key.created_at = time.time() - 2 * 86400
        assert km.enforce_rotation() is True
        assert km.current_key().id != key.id
        assert km.enforce_rotation() is False

    def test_rotate_with_material(self):
        km = create_key_manager(make_config())
        material = b"m" * 32
        key = km.rotate_with_material(material)
        assert key.material == material

    def test_hsm_backed(self):
        hsm = SimulatedHSMAdapter()
        km = create_key_manager(make_config(), hsm=hsm)
        key = km.current_key()
        assert len(key.material) == 32
        wrapped = hsm.wrap(key.id, key.material)
        assert hsm.unwrap(key.id, wrapped) == key.material
        assert km.status()["hsm"] == "simulated"

    def test_hsm_unwrap_tampered(self):
        hsm = SimulatedHSMAdapter()
        material = os.urandom(32)
        wrapped = bytearray(hsm.wrap("k1", material))
        wrapped[0] ^= 0xFF
        with pytest.raises(KeyManagementError):
            hsm.unwrap("k1", bytes(wrapped))

    def test_hsm_generate_and_destroy(self):
        hsm = SimulatedHSMAdapter()
        material = hsm.generate(KeyPurpose.ENCRYPTION)
        assert len(material) == 32
        hsm.destroy("k1")

    def test_kms_adapter(self):
        client = FakeKMSClient()
        kms = KMSAdapter(client)
        material = kms.generate(KeyPurpose.ENCRYPTION)
        assert len(material) == 32
        wrapped = kms.wrap("key-1", material)
        assert kms.unwrap("key-1", wrapped) == material
        kms.destroy("key-1")
        assert client.destroyed == ["key-1"]

    def test_kms_requires_client(self):
        with pytest.raises(KeyManagementError):
            KMSAdapter()

    def test_status(self):
        km = create_key_manager(make_config())
        status = km.status()
        assert status["current_version"] >= 1
        assert status["rotation_days"] == 90


# ---------------------------------------------------------------------------
# zero trust
# ---------------------------------------------------------------------------


def make_subject(subject_id="alice", tenant="acme"):
    return Subject(id=subject_id, tenant=tenant, roles=["admin"], groups=["eng"])


def allow_policy(**kwargs):
    return Policy(
        id=kwargs.pop("id", generate_id("pol")),
        name=kwargs.pop("name", "allow-all"),
        effect=PolicyEffect.ALLOW,
        actions=kwargs.pop("actions", ["*"]),
        resources=kwargs.pop("resources", ["*"]),
        priority=kwargs.pop("priority", 0),
    )


class TestZeroTrustEnforcer:
    def test_policy_deny_by_default(self):
        zt = create_zero_trust_enforcer(make_config())
        result = zt.check(make_subject(), "read", "svc:1")
        assert result.allowed is False
        assert result.decision == Decision.DENY
        assert "no policy matched" in result.reasons

    def test_allow_policy(self):
        zt = create_zero_trust_enforcer(make_config())
        zt.add_policy(allow_policy(actions=["read"], resources=["svc:*"]))
        result = zt.check(make_subject(), "read", "svc:1")
        assert result.allowed is True
        assert result.matched_policy
        assert result.decision == Decision.ALLOW

    def test_deny_policy_wins(self):
        zt = create_zero_trust_enforcer(make_config())
        zt.add_policy(allow_policy(actions=["read"]))
        zt.add_policy(Policy(id="deny1", name="deny", effect=PolicyEffect.DENY, actions=["read"], priority=100))
        result = zt.check(make_subject(), "read", "svc:1")
        assert result.allowed is False
        assert "matched deny policy" in result.reasons

    def test_subject_scoping(self):
        zt = create_zero_trust_enforcer(make_config())
        zt.add_policy(Policy(id="p1", name="alice-only", subjects=["alice"], actions=["read"]))
        assert zt.check(make_subject(), "read", "svc:1").allowed is True
        assert zt.check(make_subject("bob"), "read", "svc:1").allowed is False

    def test_conditions(self):
        zt = create_zero_trust_enforcer(make_config())
        zt.add_policy(Policy(id="p1", name="role-gate", actions=["read"], conditions={"role": "admin"}))
        assert zt.check(make_subject(), "read", "svc:1").allowed is True
        bob = Subject(id="bob", tenant="acme", roles=["user"])
        assert zt.check(bob, "read", "svc:1").allowed is False

    def test_conditions_tenant(self):
        zt = create_zero_trust_enforcer(make_config())
        zt.add_policy(Policy(id="p1", name="t", actions=["read"], conditions={"tenant": "acme"}))
        assert zt.check(make_subject(), "read", "svc:1").allowed is True
        assert zt.check(make_subject(tenant="other"), "read", "svc:1").allowed is False

    def test_conditions_action_resource(self):
        zt = create_zero_trust_enforcer(make_config())
        zt.add_policy(Policy(id="p1", name="a", actions=["read"], conditions={"action": "read", "resource": "svc:1"}))
        assert zt.check(make_subject(), "read", "svc:1").allowed is True
        assert zt.check(make_subject(), "write", "svc:1").allowed is False

    def test_conditions_unknown_key_fails_closed(self):
        zt = create_zero_trust_enforcer(make_config())
        zt.add_policy(Policy(id="p1", name="c", actions=["read"], conditions={"mystery": 1}))
        assert zt.check(make_subject(), "read", "svc:1").allowed is False

    def test_conditions_raise_policy_error(self):
        zt = create_zero_trust_enforcer(make_config())
        zt.add_policy(Policy(id="p1", name="c", actions=["read"], conditions={"action": ["read"]}))

        def boom():
            raise ValueError("boom")

        class Trap:
            def __bool__(self):
                raise ValueError("boom")

        original = zt._evaluate_conditions

        def raising(conditions, subject, action, resource):
            raise ValueError("boom")

        zt._evaluate_conditions = raising
        try:
            with pytest.raises(PolicyEvaluationError):
                zt.check(make_subject(), "read", "svc:1")
        finally:
            zt._evaluate_conditions = original

    def test_tenant_mismatch(self):
        zt = create_zero_trust_enforcer(make_config())
        zt.add_policy(allow_policy())
        with pytest.raises(TenantValidationError):
            zt.check(make_subject(), "read", "svc:1", tenant="other")

    def test_authenticate_success(self):
        zt = create_zero_trust_enforcer(make_config())
        zt.register_credential_validator(AuthMethod.PASSWORD, lambda ctx: True)
        context = zt.authenticate(make_subject(), AuthMethod.PASSWORD)
        assert context.session is not None
        assert context.session.subject_id == "alice"

    def test_authenticate_failure_locks(self):
        zt = create_zero_trust_enforcer(make_config(max_failed_attempts=2, lockout_seconds=60))
        zt.register_credential_validator(AuthMethod.PASSWORD, lambda ctx: False)
        for _ in range(2):
            with pytest.raises(AuthenticationError):
                zt.authenticate(make_subject(), AuthMethod.PASSWORD)
        assert zt.is_locked_out("alice") is True
        with pytest.raises(AuthenticationError):
            zt.authenticate(make_subject(), AuthMethod.PASSWORD)
        zt.reset_failures("alice")
        assert zt.is_locked_out("alice") is False

    def test_lockout_expires(self):
        zt = create_zero_trust_enforcer(make_config(max_failed_attempts=1, lockout_seconds=60))
        zt.register_credential_validator(AuthMethod.PASSWORD, lambda ctx: False)
        with pytest.raises(AuthenticationError):
            zt.authenticate(make_subject(), AuthMethod.PASSWORD)
        assert zt.is_locked_out("alice") is True
        zt._lockout_until["alice"] = time.time() - 1
        assert zt.is_locked_out("alice") is False

    def test_no_validator(self):
        zt = create_zero_trust_enforcer(make_config())
        with pytest.raises(AuthenticationError):
            zt.authenticate(make_subject(), AuthMethod.PASSWORD)

    def test_mfa_required(self):
        zt = create_zero_trust_enforcer(make_config(require_mfa=True))
        zt.register_credential_validator(AuthMethod.PASSWORD, lambda ctx: True)
        zt.register_mfa_validator(AuthMethod.PASSWORD, lambda ctx: True)
        context = zt.authenticate(make_subject(), AuthMethod.PASSWORD)
        assert context.mfa_verified is True

    def test_mfa_required_no_validator(self):
        zt = create_zero_trust_enforcer(make_config(require_mfa=True))
        zt.register_credential_validator(AuthMethod.PASSWORD, lambda ctx: True)
        with pytest.raises(AuthenticationError):
            zt.authenticate(make_subject(), AuthMethod.PASSWORD)

    def test_mfa_failure(self):
        zt = create_zero_trust_enforcer(make_config(require_mfa=True))
        zt.register_credential_validator(AuthMethod.PASSWORD, lambda ctx: True)
        zt.register_mfa_validator(AuthMethod.PASSWORD, lambda ctx: False)
        with pytest.raises(AuthenticationError):
            zt.authenticate(make_subject(), AuthMethod.PASSWORD)

    def test_authorize_with_session(self):
        zt = create_zero_trust_enforcer(make_config())
        zt.add_policy(allow_policy(actions=["read"]))
        session = zt.create_session(make_subject())
        context = AuthContext(subject=make_subject(), session=session)
        result = zt.authorize(context, "read", "svc:1")
        assert result.allowed is True
        assert session.last_seen > 0

    def test_authorize_revoked_session(self):
        zt = create_zero_trust_enforcer(make_config())
        zt.add_policy(allow_policy())
        session = zt.create_session(make_subject())
        zt.revoke_session(session.id)
        context = AuthContext(subject=make_subject(), session=session)
        with pytest.raises(SessionValidationError):
            zt.authorize(context, "read", "svc:1")

    def test_authorize_expired_session(self):
        zt = create_zero_trust_enforcer(make_config())
        zt.add_policy(allow_policy())
        session = zt.create_session(make_subject(), ttl=-1)
        context = AuthContext(subject=make_subject(), session=session)
        with pytest.raises(SessionValidationError):
            zt.authorize(context, "read", "svc:1")

    def test_authorize_idle_session(self):
        zt = create_zero_trust_enforcer(make_config(session_idle_timeout_seconds=10))
        zt.add_policy(allow_policy())
        session = zt.create_session(make_subject())
        session.last_seen = time.time() - 60
        context = AuthContext(subject=make_subject(), session=session)
        with pytest.raises(SessionValidationError):
            zt.authorize(context, "read", "svc:1")

    def test_get_session_expires(self):
        zt = create_zero_trust_enforcer(make_config())
        session = zt.create_session(make_subject(), ttl=-5)
        fetched = zt.get_session(session.id)
        assert fetched.status == SessionStatus.EXPIRED
        assert zt.get_session("missing") is None

    def test_revoke_all_for_subject(self):
        zt = create_zero_trust_enforcer(make_config())
        s1 = zt.create_session(make_subject())
        s2 = zt.create_session(make_subject())
        other = zt.create_session(make_subject("bob"))
        assert zt.revoke_all_for_subject("alice") == 2
        assert zt.get_session(s1.id).status == SessionStatus.REVOKED
        assert zt.get_session(s2.id).status == SessionStatus.REVOKED
        assert zt.get_session(other.id).status == SessionStatus.ACTIVE

    def test_policy_list_and_priority(self):
        zt = create_zero_trust_enforcer(make_config())
        zt.add_policies([allow_policy(id="a"), allow_policy(id="b")])
        assert len(zt.policies()) == 2

    def test_enforce_disabled_allows_no_policy(self):
        zt = create_zero_trust_enforcer(make_config(zero_trust_enforce=False))
        result = zt.check(make_subject(), "read", "svc:1")
        assert result.allowed is False

    def test_status(self):
        zt = create_zero_trust_enforcer(make_config())
        zt.add_policy(allow_policy())
        status = zt.status()
        assert status["policies"] == 1
        assert status["enforce"] is True


# ---------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------


class TestAuditRepository:
    def test_append_and_find(self):
        repo = AuditRepository(make_config())
        record = repo.append("login", "alice", "authenticate", "auth", "success", event_type=AuditEventType.AUTHENTICATION)
        assert record.seq == 1
        assert record.signature
        assert record.hash
        assert repo.count() == 1
        assert repo.find(actor="alice")[0].seq == 1
        assert repo.find(seq=1)[0].event == "login"
        assert repo.find(event="login")[0].actor == "alice"
        assert repo.find(action="authenticate")[0].resource == "auth"
        assert repo.find(outcome="fail") == []
        assert repo.find(event_type=AuditEventType.AUTHENTICATION)[0].seq == 1
        assert repo.find(severity=AuditSeverity.INFO)[0].seq == 1
        assert repo.find(after=time.time() - 10)[0].seq == 1
        assert repo.find(before=time.time() + 10)[0].seq == 1
        assert repo.find(resource="other") == []

    def test_chain_linking(self):
        repo = AuditRepository(make_config())
        r1 = repo.append("a", "x", "act", "res")
        r2 = repo.append("b", "y", "act", "res")
        assert r2.previous_hash == r1.signature
        assert repo.status()["last_seq"] == 2

    def test_verify_integrity_clean(self):
        repo = AuditRepository(make_config())
        repo.append("a", "x", "act", "res")
        repo.append("b", "y", "act", "res")
        assert repo.verify_integrity() == []

    def test_verify_detects_tamper(self):
        repo = AuditRepository(make_config())
        repo.append("a", "x", "act", "res")
        record = repo.append("b", "y", "act", "res")
        record.outcome = "tampered"
        violations = repo.verify_integrity()
        assert any(v["reason"] == "signature mismatch" for v in violations)

    def test_verify_detects_broken_link(self):
        repo = AuditRepository(make_config())
        repo.append("a", "x", "act", "res")
        record = repo.append("b", "y", "act", "res")
        record.previous_hash = "forged"
        violations = repo.verify_integrity()
        assert any(v["reason"] == "broken link" for v in violations)

    def test_get(self):
        repo = AuditRepository(make_config())
        repo.append("a", "x", "act", "res")
        assert repo.get(1) is not None
        assert repo.get(2) is None
        assert repo.get(0) is None

    def test_prune_immutable(self):
        repo = AuditRepository(make_config(audit_retention_days=1))
        r1 = repo.append("old", "x", "act", "res")
        r1.timestamp = time.time() - 10 * 86400
        r2 = repo.append("new", "y", "act", "res")
        r3 = repo.append("new2", "z", "act", "res")
        removed = repo.prune()
        assert removed == 1
        assert repo.count() == 2
        assert repo.verify_integrity() == []

    def test_prune_non_immutable(self):
        repo = AuditRepository(make_config(audit_immutable=False, audit_retention_days=1))
        r1 = repo.append("old", "x", "act", "res")
        r1.timestamp = time.time() - 10 * 86400
        repo.append("new", "y", "act", "res")
        removed = repo.prune()
        assert removed == 1
        assert repo.count() == 1

    def test_export(self):
        repo = AuditRepository(make_config())
        repo.append("a", "x", "act", "res")
        exported = repo.export()
        assert exported[0]["seq"] == 1

    def test_immutable_prune_keeps_chain(self):
        repo = AuditRepository(make_config(audit_retention_days=1))
        r1 = repo.append("old", "x", "act", "res")
        r1.timestamp = time.time() - 10 * 86400
        repo.append("new", "y", "act", "res")
        repo.append("new2", "z", "act", "res")
        repo.prune()
        assert repo.verify_integrity() == []

    def test_prune_all(self):
        repo = AuditRepository(make_config(audit_retention_days=1))
        r1 = repo.append("old", "x", "act", "res")
        r1.timestamp = time.time() - 10 * 86400
        removed = repo.prune()
        assert removed == 0
        assert repo.count() == 1


class TestAuditService:
    def test_log_disabled(self):
        service = create_audit_service(make_config(audit_enabled=False))
        assert service.log("e", "a", "act") is None

    def test_log_enabled(self):
        service = create_audit_service(make_config())
        record = service.log("e", "a", "act", "res")
        assert record is not None

    def test_typed_events(self):
        service = create_audit_service(make_config())
        service.log_authentication("alice", "success")
        service.log_authentication("alice", "failure")
        service.log_authorization("alice", "success")
        service.log_authorization("alice", "denied")
        service.log_secret("admin", "rotate", "db-password")
        service.log_secret("admin", "delete", "db-password")
        service.log_admin("admin", "restart", "gateway", "failed")
        assert service.repository.count() == 7
        authz = service.repository.find(event_type=AuditEventType.AUTHORIZATION)
        assert authz[0].severity == AuditSeverity.INFO
        assert authz[1].severity == AuditSeverity.CRITICAL
        assert service.verify() == []
        assert service.status()["enabled"] is True


# ---------------------------------------------------------------------------
# privacy
# ---------------------------------------------------------------------------


class TestPIIDetector:
    def test_detect_email_phone_ssn(self):
        detector = PIIDetector()
        text = "Contact alice@example.com or 555-123-4567; ssn 123-45-6789"
        fields = detector.detect(text)
        kinds = {f.kind for f in fields}
        assert PIIKind.EMAIL in kinds
        assert PIIKind.PHONE in kinds
        assert PIIKind.SSN in kinds

    def test_detect_credit_card_and_ip(self):
        detector = PIIDetector()
        text = "card 4111 1111 1111 1111 from 192.168.0.1"
        fields = detector.detect(text)
        kinds = {f.kind for f in fields}
        assert PIIKind.CREDIT_CARD in kinds
        assert PIIKind.IP_ADDRESS in kinds

    def test_detect_dob_address_name(self):
        detector = PIIDetector()
        text = "born 1990-05-05, name: Jane Doe, lives at 10 Main Street"
        fields = detector.detect(text)
        kinds = {f.kind for f in fields}
        assert PIIKind.DATE_OF_BIRTH in kinds
        assert PIIKind.NAME in kinds
        assert PIIKind.ADDRESS in kinds

    def test_mask_partial(self):
        detector = PIIDetector()
        result = detector.mask("email alice@example.com here")
        assert result.masked == 1
        assert "alice@example.com" not in result.text
        assert "alic" in result.text
        assert result.text.endswith("here")

    def test_mask_full(self):
        detector = PIIDetector()
        result = detector.mask("email alice@example.com here", mode="full")
        assert "alice@example.com" not in result.text
        assert "***" in result.text

    def test_no_pii(self):
        detector = PIIDetector()
        result = detector.mask("nothing sensitive here")
        assert result.masked == 0
        assert result.text == "nothing sensitive here"

    def test_custom_patterns(self):
        detector = PIIDetector(patterns={PIIKind.NAME: __import__("re").compile(r"FOO\d+")})
        result = detector.mask("FOO123")
        assert result.masked == 1

    def test_field_locations_sorted(self):
        detector = PIIDetector()
        text = "a@b.com and 123-45-6789"
        fields = detector.detect(text)
        locations = [f.location[0] for f in fields]
        assert locations == sorted(locations)


class TestPrivacyService:
    def test_detect_disabled(self):
        service = create_privacy_service(make_config(pii_detection_enabled=False))
        assert service.detect("a@b.com") == []
        result = service.mask("a@b.com")
        assert result.text == "a@b.com"

    def test_mask(self):
        service = create_privacy_service(make_config())
        result = service.mask("contact a@b.com please")
        assert result.masked == 1

    def test_redact(self):
        service = create_privacy_service(make_config())
        assert "a@b.com" not in service.redact("contact a@b.com")

    def test_dsar_lifecycle(self):
        service = create_privacy_service(make_config())
        service.register_data_provider(lambda subject, kind: {"records": [1, 2]})
        request = service.submit_request("alice@x.com", DataSubjectRequestType.ACCESS)
        assert request.status == DataSubjectRequestStatus.PENDING
        assert service.get_request(request.id) is request
        assert service.get_request("missing") is None
        fulfilled = service.fulfill_request(request.id)
        assert fulfilled.status == DataSubjectRequestStatus.FULFILLED
        assert fulfilled.result["data"]["records"] == [1, 2]
        assert service.list_requests("alice@x.com")[0].id == request.id
        assert service.list_requests("bob") == []

    def test_dsar_erasure(self):
        service = create_privacy_service(make_config())
        service.register_data_eraser(lambda subject, scope: True)
        request = service.submit_request("alice@x.com", DataSubjectRequestType.ERASURE)
        fulfilled = service.fulfill_request(request.id)
        assert fulfilled.result["erased"] is True

    def test_dsar_rectification(self):
        service = create_privacy_service(make_config())
        service.register_data_eraser(lambda subject, scope: True)
        request = service.submit_request("alice@x.com", DataSubjectRequestType.RECTIFICATION)
        assert service.fulfill_request(request.id).status == DataSubjectRequestStatus.FULFILLED

    def test_dsar_portability(self):
        service = create_privacy_service(make_config())
        service.register_data_provider(lambda subject, kind: ["a", "b"])
        request = service.submit_request("alice@x.com", DataSubjectRequestType.PORTABILITY)
        assert service.fulfill_request(request.id).result["data"] == ["a", "b"]

    def test_dsar_missing(self):
        service = create_privacy_service(make_config())
        with pytest.raises(DataSubjectRequestError):
            service.fulfill_request("missing")

    def test_dsar_no_provider(self):
        service = create_privacy_service(make_config())
        request = service.submit_request("alice@x.com", DataSubjectRequestType.ACCESS)
        with pytest.raises(DataSubjectRequestError):
            service.fulfill_request(request.id)
        assert request.status == DataSubjectRequestStatus.PENDING

    def test_dsar_double_fulfill(self):
        service = create_privacy_service(make_config())
        service.register_data_provider(lambda subject, kind: {})
        request = service.submit_request("a@x.com", DataSubjectRequestType.ACCESS)
        service.fulfill_request(request.id)
        with pytest.raises(DataSubjectRequestError):
            service.fulfill_request(request.id)

    def test_expire_stale(self):
        service = create_privacy_service(make_config())
        request = service.submit_request("a@x.com", DataSubjectRequestType.ACCESS)
        request.created_at = time.time() - 2 * 86400
        assert service.expire_stale_requests(ttl_seconds=3600) == 1
        assert request.status == DataSubjectRequestStatus.EXPIRED

    def test_status(self):
        service = create_privacy_service(make_config())
        status = service.status()
        assert status["masking_mode"] == "partial"


# ---------------------------------------------------------------------------
# compliance
# ---------------------------------------------------------------------------


class TestComplianceManager:
    def test_default_frameworks(self):
        manager = create_compliance_manager(make_config())
        assert ComplianceFramework.SOC2 in manager.frameworks()
        assert ComplianceFramework.ISO27001 in manager.frameworks()
        assert ComplianceFramework.GDPR in manager.frameworks()
        assert ComplianceFramework.CCPA in manager.frameworks()

    def test_framework_subset(self):
        manager = create_compliance_manager(make_config(compliance_frameworks=["soc2", "gdpr"]))
        assert manager.frameworks() == [ComplianceFramework.SOC2, ComplianceFramework.GDPR]

    def test_report_generation(self):
        manager = create_compliance_manager(make_config())
        report = manager.generate_report(ComplianceFramework.GDPR)
        assert report.controls
        assert report.status()["implemented"] >= 1
        assert report.readiness() > 0

    def test_report_disabled_framework_raises(self):
        manager = create_compliance_manager(make_config(compliance_frameworks=["soc2"]))
        with pytest.raises(ComplianceError):
            manager.generate_report("ccpa")

    def test_report_by_string(self):
        manager = create_compliance_manager(make_config())
        report = manager.generate_report("iso27001")
        assert report.framework == ComplianceFramework.ISO27001

    def test_evidence_provider(self):
        manager = create_compliance_manager(
            make_config(), evidence_provider=lambda control_id, framework: {"artifact": "audit.zip"}
        )
        report = manager.generate_report(ComplianceFramework.SOC2)
        assert report.controls[0].evidence["artifact"] == "audit.zip"

    def test_custom_status_override(self):
        manager = create_compliance_manager(make_config())
        manager.set_control_status("soc2", "CC6.1", ControlStatus.IMPLEMENTED)
        report = manager.generate_report(ComplianceFramework.SOC2)
        control = next(c for c in report.controls if c.id == "CC6.1")
        assert control.status == ControlStatus.IMPLEMENTED

    def test_findings_generated(self):
        manager = create_compliance_manager(make_config())
        report = manager.generate_report(ComplianceFramework.CCPA)
        assert any(f.severity == ThreatSeverity.HIGH for f in report.findings)

    def test_readiness(self):
        manager = create_compliance_manager(make_config())
        readiness = manager.readiness()
        assert 0.0 <= readiness <= 100.0

    def test_summary(self):
        manager = create_compliance_manager(make_config())
        summary = manager.summary()
        assert "soc2" in summary["frameworks"]


# ---------------------------------------------------------------------------
# threat detection
# ---------------------------------------------------------------------------


class TestThreatDetector:
    def test_report_and_severity(self):
        detector = create_threat_detector(make_config())
        event = detector.report(ThreatType.BRUTE_FORCE, source="10.0.0.1", details={"attempts": 3})
        assert event.id
        assert event.severity == ThreatSeverity.HIGH
        assert event.source == "10.0.0.1"
        assert detector.recent_events()[0].id == event.id

    def test_analyze_brute_force(self):
        detector = create_threat_detector(make_config(brute_force_threshold=3))
        for _ in range(3):
            detector.report(ThreatType.BRUTE_FORCE, source="10.0.0.9")
        signals = detector.analyze()
        assert "brute_force:10.0.0.9" in signals

    def test_analyze_credential_stuffing(self):
        detector = create_threat_detector(make_config(brute_force_threshold=2))
        detector.report(ThreatType.CREDENTIAL_STUFFING, source="10.0.0.8")
        detector.report(ThreatType.CREDENTIAL_STUFFING, source="10.0.0.8")
        assert "credential_stuffing:10.0.0.8" in detector.analyze()

    def test_analyze_token_replay(self):
        detector = create_threat_detector(make_config(token_replay_threshold=2))
        detector.report(ThreatType.TOKEN_REPLAY, source="10.0.0.7")
        detector.report(ThreatType.TOKEN_REPLAY, source="10.0.0.7")
        assert "token_replay:10.0.0.7" in detector.analyze()

    def test_analyze_anomaly(self):
        detector = create_threat_detector(make_config(brute_force_threshold=2, token_replay_threshold=2))
        detector.report(ThreatType.BRUTE_FORCE, source="10.0.0.6")
        detector.report(ThreatType.CREDENTIAL_STUFFING, source="10.0.0.6")
        detector.report(ThreatType.TOKEN_REPLAY, source="10.0.0.6")
        detector.report(ThreatType.ANOMALY, source="10.0.0.6")
        assert "anomaly:10.0.0.6" in detector.analyze()

    def test_analyze_disabled(self):
        detector = create_threat_detector(make_config(threat_detection_enabled=False))
        detector.report(ThreatType.BRUTE_FORCE, source="x")
        assert detector.analyze() == []

    def test_window_expiry(self):
        detector = create_threat_detector(make_config(brute_force_threshold=1, threat_window_seconds=1))
        detector.report(ThreatType.BRUTE_FORCE, source="10.0.0.5")
        detector._events[0].timestamp = time.time() - 60
        assert detector.analyze() == []

    def test_clear(self):
        detector = create_threat_detector(make_config())
        detector.report(ThreatType.ANOMALY)
        detector.clear()
        assert detector.recent_events() == []

    def test_severity_mapping(self):
        detector = create_threat_detector(make_config())
        assert detector.report(ThreatType.DATA_EXFILTRATION).severity == ThreatSeverity.CRITICAL
        assert detector.report(ThreatType.MALWARE).severity == ThreatSeverity.CRITICAL
        assert detector.report(ThreatType.TOKEN_REPLAY).severity == ThreatSeverity.MEDIUM
        assert detector.report(ThreatType.ANOMALY).severity == ThreatSeverity.LOW

    def test_enabled_flag(self):
        assert create_threat_detector(make_config(threat_detection_enabled=False)).enabled() is False
        assert create_threat_detector(make_config()).enabled() is True


class TestIncidentManager:
    def make_incident_manager(self, **kwargs):
        config = make_config(**kwargs)
        detector = create_threat_detector(config)
        return create_incident_manager(config, detector=detector)

    def test_escalate_from_events(self):
        manager = self.make_incident_manager(brute_force_threshold=2)
        manager.register_event(ThreatEvent(id="t1", threat_type=ThreatType.BRUTE_FORCE, source="10.0.0.1"))
        incidents = manager.register_event(ThreatEvent(id="t2", threat_type=ThreatType.BRUTE_FORCE, source="10.0.0.1"))
        assert len(incidents) == 1
        incident = incidents[0]
        assert incident.summary == "brute_force:10.0.0.1"
        assert incident.status == IncidentStatus.OPEN
        assert manager.get_incident(incident.id) is incident
        assert manager.get_incident("missing") is None

    def test_events_merge_into_open_incident(self):
        manager = self.make_incident_manager(brute_force_threshold=1)
        manager.register_event(ThreatEvent(id="t1", threat_type=ThreatType.BRUTE_FORCE, source="10.0.0.2"))
        second = manager.register_event(ThreatEvent(id="t2", threat_type=ThreatType.BRUTE_FORCE, source="10.0.0.2"))
        assert second == []
        incidents = manager.list_incidents()
        assert len(incidents) == 1
        assert len(incidents[0].threat_events) == 2

    def test_manual_escalate(self):
        manager = self.make_incident_manager()
        incident = manager.escalate("anomaly:10.0.0.3")
        assert manager.get_incident(incident.id).summary == "anomaly:10.0.0.3"

    def test_update_status(self):
        manager = self.make_incident_manager()
        incident = manager.escalate("anomaly:10.0.0.4")
        updated = manager.update_status(incident.id, IncidentStatus.RESOLVED, summary="contained")
        assert updated.status == IncidentStatus.RESOLVED
        assert updated.resolved_at > 0
        assert updated.summary == "contained"
        with pytest.raises(IncidentError):
            manager.update_status("missing", IncidentStatus.CLOSED)

    def test_list_incidents_filtered(self):
        manager = self.make_incident_manager()
        incident = manager.escalate("anomaly:10.0.0.5")
        assert manager.list_incidents(IncidentStatus.OPEN)[0].id == incident.id
        assert manager.list_incidents(IncidentStatus.CLOSED) == []

    def test_handler_invoked(self):
        manager = self.make_incident_manager(brute_force_threshold=1)
        seen = []
        manager.add_handler(lambda incident: seen.append(incident.id))
        incidents = manager.register_event(ThreatEvent(id="t1", threat_type=ThreatType.BRUTE_FORCE, source="10.0.0.9"))
        assert seen == [incidents[0].id]

    def test_handler_exception_swallowed(self):
        manager = self.make_incident_manager(brute_force_threshold=1)

        def bad(incident):
            raise RuntimeError("handler bug")

        manager.add_handler(bad)
        incidents = manager.register_event(ThreatEvent(id="t1", threat_type=ThreatType.BRUTE_FORCE, source="10.0.0.9"))
        assert len(incidents) == 1

    def test_count(self):
        manager = self.make_incident_manager()
        manager.escalate("a:1")
        manager.escalate("b:2")
        assert manager.count()["open"] == 2


# ---------------------------------------------------------------------------
# monitoring
# ---------------------------------------------------------------------------


class TestMonitoringService:
    def test_stdout_alert(self, capsys):
        manager = create_monitoring_service(make_config())
        alert = asyncio_run(manager.send_alert("brute force", ThreatSeverity.HIGH, source="threat"))
        assert alert.id
        assert manager.alert_count() == 1
        assert manager.recent_alerts()[0].id == alert.id
        captured = capsys.readouterr()
        assert "security_alert" in captured.out

    def test_alert_pending_before_start(self):
        manager = create_monitoring_service(make_config(monitoring_enabled=False))
        alert = asyncio_run(manager.send_alert("quiet"))
        assert manager.alert_count() == 1
        assert manager.status()["enabled"] is False

    def test_start_stop(self):
        manager = create_monitoring_service(make_config())
        asyncio_run(manager.start())
        asyncio_run(manager.start())
        assert manager.status()["running"] is True
        asyncio_run(manager.stop())
        asyncio_run(manager.stop())
        assert manager.status()["running"] is False

    def test_status(self):
        manager = create_monitoring_service(make_config())
        assert manager.status()["backend"] == "stdout"

    def test_custom_sink(self):
        class FakeSink(StdoutSink):
            def __init__(self, config):
                super().__init__(config)
                self.payloads = []

            async def emit(self, payload):
                self.payloads.append(payload)
                return True

        sink = FakeSink(make_config())
        manager = create_monitoring_service(make_config(), sink=sink)
        asyncio_run(manager.send_alert("hello"))
        assert sink.payloads[0]["message"] == "hello"

    def test_emit_failure_raises(self):
        class BrokenSink(StdoutSink):
            async def emit(self, payload):
                raise MonitoringError("down")

        manager = create_monitoring_service(make_config(), sink=BrokenSink(make_config()))
        with pytest.raises(MonitoringError):
            asyncio_run(manager.send_alert("boom"))


class TestSiemSinks:
    class FakeSiemTransport:
        def __init__(self):
            self.calls = []
            self.response = {}
            self.fail = None

        async def __call__(self, backend, method, url, body=None):
            self.calls.append((method, url, body))
            if self.fail:
                raise self.fail
            return self.response

    def test_splunk_emit(self):
        transport = self.FakeSiemTransport()
        sink = SplunkSink(make_config(siem_config={"token": "t"}), transport=transport)
        assert asyncio_run(sink.emit({"message": "x"})) is True
        assert transport.calls[0][0] == "POST"
        assert transport.calls[0][2]["event"]["message"] == "x"

    def test_splunk_error_code(self):
        transport = self.FakeSiemTransport()
        transport.response = {"code": 5}
        sink = SplunkSink(make_config(), transport=transport)
        assert asyncio_run(sink.emit({"message": "x"})) is False

    def test_splunk_failure(self):
        transport = self.FakeSiemTransport()
        transport.fail = RuntimeError("down")
        sink = SplunkSink(make_config(), transport=transport)
        with pytest.raises(MonitoringError):
            asyncio_run(sink.emit({"message": "x"}))

    def test_elastic_emit(self):
        transport = self.FakeSiemTransport()
        transport.response = {"result": "created"}
        sink = ElasticSink(make_config(), transport=transport)
        assert asyncio_run(sink.emit({"message": "x"})) is True

    def test_elastic_missing_result(self):
        transport = self.FakeSiemTransport()
        transport.response = {"result": "noop"}
        sink = ElasticSink(make_config(), transport=transport)
        assert asyncio_run(sink.emit({"message": "x"})) is False

    def test_elastic_failure(self):
        transport = self.FakeSiemTransport()
        transport.fail = RuntimeError("down")
        sink = ElasticSink(make_config(), transport=transport)
        with pytest.raises(MonitoringError):
            asyncio_run(sink.emit({}))

    def test_datadog_emit(self):
        transport = self.FakeSiemTransport()
        transport.response = None
        sink = DatadogSink(make_config(), transport=transport)
        assert asyncio_run(sink.emit({"message": "x"})) is True
        assert transport.calls[0][2]["message"] == '{"message": "x"}'

    def test_datadog_failure(self):
        transport = self.FakeSiemTransport()
        transport.fail = RuntimeError("down")
        sink = DatadogSink(make_config(), transport=transport)
        with pytest.raises(MonitoringError):
            asyncio_run(sink.emit({}))

    def test_registry(self):
        registry = SiemRegistry()
        assert isinstance(registry.create(make_config()), StdoutSink)
        assert isinstance(registry.create(make_config(siem_backend="splunk")), SplunkSink)
        assert isinstance(registry.create(make_config(siem_backend="elastic")), ElasticSink)
        assert isinstance(registry.create(make_config(siem_backend="datadog")), DatadogSink)
        with pytest.raises(MonitoringError):
            registry.create(make_config(siem_backend="nope"))


# ---------------------------------------------------------------------------
# manager facade
# ---------------------------------------------------------------------------


class TestSecurityManager:
    def test_initialize_shutdown(self):
        manager = create_security_manager(make_config())
        asyncio_run(manager.initialize())
        asyncio_run(manager.initialize())
        assert manager.status()["initialized"] is True
        asyncio_run(manager.shutdown())
        asyncio_run(manager.shutdown())
        assert manager.status()["initialized"] is False

    def test_secret_roundtrip(self):
        manager = create_security_manager(make_config())
        asyncio_run(manager.set_secret("svc-token", "abc"))
        secret = asyncio_run(manager.get_secret("svc-token"))
        assert secret.value == "abc"
        rotated = asyncio_run(manager.rotate_secret("svc-token", "def"))
        assert rotated.version == 2

    def test_encrypt_decrypt(self):
        manager = create_security_manager(make_config())
        wrapped = manager.encrypt(b"payload")
        assert manager.decrypt(wrapped) == b"payload"

    def test_field_storage_helpers(self):
        manager = create_security_manager(make_config())
        wrapped = manager.encrypt_field({"token": "secret"})
        assert manager.decrypt_field(wrapped) == {"token": "secret"}
        stored = manager.encrypt_storage("value", purpose="t1")
        assert manager.decrypt_storage(stored) == "value"

    def test_zero_trust_helpers(self):
        manager = create_security_manager(make_config())
        manager.add_policy(Policy(id="p1", name="read", actions=["read"]))
        result = manager.check(make_subject(), "read", "svc:1")
        assert result.allowed is True
        manager.zero_trust.register_credential_validator(AuthMethod.PASSWORD, lambda ctx: True)
        context = manager.authenticate(make_subject(), AuthMethod.PASSWORD)
        assert context.session is not None
        result = manager.authorize(context, "read", "svc:1")
        assert result.allowed is True

    def test_audit_helper(self):
        manager = create_security_manager(make_config())
        record = manager.audit("admin_action", "admin", "restart", "gateway")
        assert record.seq == 1
        assert manager.verify_audit() == []

    def test_privacy_helpers(self):
        manager = create_security_manager(make_config())
        result = manager.mask_pii("email a@b.com")
        assert result.masked == 1
        manager.privacy.register_data_provider(lambda s, k: {"x": 1})
        request = manager.submit_dsar("alice", DataSubjectRequestType.ACCESS)
        assert manager.fulfill_dsar(request.id).status == DataSubjectRequestStatus.FULFILLED

    def test_compliance_helpers(self):
        manager = create_security_manager(make_config())
        report = manager.compliance_report("soc2")
        assert report.controls
        assert manager.compliance_readiness() > 0

    def test_threat_helpers(self):
        manager = create_security_manager(make_config())
        event = manager.report_threat(ThreatType.BRUTE_FORCE, source="10.0.0.1")
        assert event.id
        incident = manager.escalate_incident("anomaly:10.0.0.2")
        assert manager.resolve_incident(incident.id).status == IncidentStatus.RESOLVED

    def test_alert_helper(self):
        manager = create_security_manager(make_config())
        alert = asyncio_run(manager.send_alert("alert!"))
        assert isinstance(alert, SecurityAlert)

    def test_status_complete(self):
        manager = create_security_manager(make_config())
        asyncio_run(manager.initialize())
        status = manager.status()
        assert status["node_id"]
        assert "secrets" in status
        assert "keys" in status
        assert "zero_trust" in status
        assert "audit" in status
        assert "privacy" in status
        assert "compliance" in status
        assert "threat" in status
        assert "monitoring" in status

    def test_injected_components(self):
        config = make_config()
        keys = create_key_manager(config)
        secrets = create_secret_manager(config)
        zt = create_zero_trust_enforcer(config)
        audit_service = create_audit_service(config)
        privacy = create_privacy_service(config)
        compliance = create_compliance_manager(config)
        threat = create_threat_detector(config)
        incidents = create_incident_manager(config, detector=threat)
        monitoring = create_monitoring_service(config)
        encryption = create_encryption_service(config, key_provider=keys.key_provider)
        manager = create_security_manager(
            config,
            keys=keys,
            secrets=secrets,
            zero_trust=zt,
            audit=audit_service,
            privacy=privacy,
            compliance=compliance,
            threat=threat,
            incidents=incidents,
            monitoring=monitoring,
            encryption=encryption,
        )
        assert manager.keys is keys
        assert manager.secrets is secrets
        assert manager.zero_trust is zt
        assert manager.audit_service is audit_service
        assert manager.encryption is encryption

    def test_node_id_override(self):
        base = make_config()
        rebuilt = SecurityConfig(**{**base.as_dict(), "node_id": "node-a"})
        manager = create_security_manager(rebuilt)
        assert manager.status()["node_id"] == "node-a"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# coverage edge cases
# ---------------------------------------------------------------------------


class TestCoverageEdges:
    def test_vault_token_file_and_namespace(self, tmp_path):
        token_file = tmp_path / "token"
        token_file.write_text("vault-token\n")
        config = make_config(secret_config={"token_file": str(token_file), "namespace": "team-a"})
        backend = VaultBackend(config, transport=FakeVaultTransport())
        assert backend._headers["X-Vault-Token"] == "vault-token"
        assert backend._headers["X-Vault-Namespace"] == "team-a"

    def test_vault_missing_token_file(self, tmp_path):
        config = make_config(secret_config={"token_file": str(tmp_path / "absent")})
        backend = VaultBackend(config, transport=FakeVaultTransport())
        assert "X-Vault-Token" not in backend._headers

    def test_vault_operation_failures(self):
        transport = FakeVaultTransport()
        transport.fail = RuntimeError("down")
        backend = VaultBackend(make_config(), transport=transport)
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.set(make_secret(name="x")))
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.delete("x"))
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.list())

    def test_vault_get_non_dict(self):
        class NonDictTransport(FakeVaultTransport):
            async def __call__(self, backend, method, url, body=None):
                return None

        backend = VaultBackend(make_config(), transport=NonDictTransport())
        with pytest.raises(SecretNotFoundError):
            asyncio_run(backend.get("x"))

    def test_kube_token_file(self, tmp_path):
        token_file = tmp_path / "token"
        token_file.write_text("kube-token")
        config = make_config(secret_config={"token_file": str(token_file)})
        backend = KubernetesBackend(config, transport=FakeKubeTransport())
        assert backend._headers["Authorization"] == "Bearer kube-token"

    def test_kube_missing_token_file(self, tmp_path):
        config = make_config(secret_config={"token_file": str(tmp_path / "absent")})
        backend = KubernetesBackend(config, transport=FakeKubeTransport())
        assert "Authorization" not in backend._headers

    def test_kube_operation_failures(self):
        transport = FakeKubeTransport()
        transport.fail = RuntimeError("down")
        backend = KubernetesBackend(make_config(), transport=transport)
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.get("x"))
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.set(make_secret(name="x")))
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.delete("x"))
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.list())

    def test_aws_operation_failures(self):
        client = FakeAWSClient()
        client.fail = RuntimeError("down")
        backend = AWSSecretsBackend(make_config(), client=client)
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.get("x"))
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.set(make_secret(name="x")))
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.delete("x"))

    def test_azure_operation_failures(self):
        transport = FakeAzureTransport()

        class FailingTransport(FakeAzureTransport):
            async def __call__(self, backend, method, url, body=None):
                raise RuntimeError("down")

        backend = AzureBackend(make_config(), transport=FailingTransport())
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.get("x"))
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.set(make_secret(name="x")))
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.delete("x"))
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.list())

    def test_google_operation_failures(self):
        client = FakeGoogleClient()
        client.fail = RuntimeError("down")
        backend = GoogleBackend(make_config(), client=client)
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.get("x"))
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.set(make_secret(name="x")))
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.delete("x"))
        with pytest.raises(SecretBackendError):
            asyncio_run(backend.list())

    def test_google_list_non_dict(self):
        class OddClient(FakeGoogleClient):
            def list_secrets(self, request):
                return None

        backend = GoogleBackend(make_config(), client=OddClient())
        assert asyncio_run(backend.list()) == []

    def test_environment_backend_default_prefix(self, monkeypatch):
        monkeypatch.setenv("SOMETHING_ELSE", "1")
        monkeypatch.setenv("SECRET_A", "1")
        backend = EnvironmentBackend(make_config())
        assert asyncio_run(backend.list()) == ["SECRET_A"]

    def test_secret_manager_rotate_vault_metadata(self):
        transport = FakeVaultTransport()
        manager = create_secret_manager(
            make_config(secret_backend="vault", secret_config={"address": "http://v:8200"}),
            transport=transport,
        )
        asyncio_run(manager.set_secret("db", "pw", kind=SecretKind.DATABASE, metadata={"owner": "team-a"}))
        rotated = asyncio_run(manager.rotate_secret("db", "pw2"))
        assert rotated.version == 2
        assert rotated.kind == SecretKind.DATABASE
        assert rotated.metadata["owner"] == "team-a"
        assert asyncio_run(manager.get_secret("db", bypass_cache=True)).value == "pw2"

    def test_cbc_str_key(self):
        from app.security.crypto import AESCipher

        cipher = AESCipher(EncryptionAlgorithm.AES_256_CBC)
        key = "0123456789abcdef0123456789abcdef"
        ct, iv, _ = cipher.encrypt(b"data", key)
        assert cipher.decrypt(ct, key, iv) == b"data"

    def test_resolve_current_missing(self):
        from app.security.crypto import EncryptionService

        service = EncryptionService(make_config(), key_provider=lambda key_id, version: None)
        with pytest.raises(KeyManagementError):
            service.envelope_encrypt(b"x")

    def test_key_manager_missing_operations(self):
        km = create_key_manager(make_config())
        assert km.expire("missing") is False
        assert km.get_key("missing") is None
        assert len(km.keys()) >= 1
        km._current_id = ""
        with pytest.raises(KeyManagementError):
            km.current_key()

    def test_key_manager_hsm_destroy(self):
        hsm = SimulatedHSMAdapter()
        km = create_key_manager(make_config(), hsm=hsm)
        old = km.rotate()
        assert km.destroy(old.id) is True

    def test_audit_prune_multiple_old(self):
        repo = AuditRepository(make_config(audit_retention_days=1))
        r1 = repo.append("old1", "x", "act", "res")
        r1.timestamp = time.time() - 10 * 86400
        r2 = repo.append("old2", "y", "act", "res")
        r2.timestamp = time.time() - 5 * 86400
        repo.append("new", "z", "act", "res")
        removed = repo.prune()
        assert removed == 2
        assert repo.count() == 1
        assert repo.verify_integrity() == []

    def test_zero_trust_edge_paths(self):
        zt = create_zero_trust_enforcer(make_config())
        assert zt.revoke_session("missing") is False
        zt.add_policy(allow_policy())
        context = AuthContext(subject=make_subject(), method=AuthMethod.PASSWORD)
        with pytest.raises(TenantValidationError):
            zt.authorize(context, "read", "svc:1", tenant="other")
        denied = zt.authorize(context, "write", "svc:1")
        assert denied.allowed is False
        with pytest.raises(TenantValidationError):
            zt.check(make_subject(), "read", "svc:1", tenant="other")

    def test_zero_trust_attribute_conditions(self):
        zt = create_zero_trust_enforcer(make_config())
        zt.add_policy(Policy(id="p1", name="attr", actions=["read"], conditions={"attribute": ("region", "us-east-1")}))
        ok = Subject(id="alice", tenant="acme", attributes={"region": "us-east-1"})
        bad = Subject(id="bob", tenant="acme", attributes={"region": "eu-west-1"})
        assert zt.check(ok, "read", "svc:1").allowed is True
        assert zt.check(bad, "read", "svc:1").allowed is False

    def test_policy_resource_wildcard(self):
        from app.security.models import Policy

        policy = Policy(id="p", name="n", resources=["svc:1.*"])
        subject = make_subject()
        assert policy.matches(subject, "read", "svc:1.data") is True
        assert policy.matches(subject, "read", "svc:2.data") is False

    def test_model_to_dicts(self):
        from app.security.models import (
            ComplianceReport,
            Control,
            DataSubjectRequest,
            Envelope,
            Finding,
            Incident,
            PIIField,
            PolicyResult,
            SecurityAlert,
            Session,
            ThreatEvent,
        )

        secret = make_secret()
        assert secret.to_dict()["name"] == "db-password"
        key = EncryptionKey(id="k1")
        assert key.to_dict()["status"] == "active"
        session = Session(id="s1", subject_id="alice")
        assert session.to_dict()["tenant"] == "default"
        result = PolicyResult(allowed=True, decision=Decision.ALLOW)
        assert result.to_dict()["decision"] == "allow"
        assert PolicyResult(allowed=False, decision=Decision.DENY).to_dict()["matched_policy"] == ""
        field = PIIField(kind=PIIKind.EMAIL, location=(0, 5), value="a@b.c")
        assert field.to_dict()["kind"] == "email"
        request = DataSubjectRequest(id="d1", subject="alice")
        assert request.to_dict()["request_type"] == "access"
        control = Control(id="c1", name="n")
        assert control.to_dict()["status"] == "not_implemented"
        finding = Finding(id="f1")
        assert finding.to_dict()["severity"] == "medium"
        event = ThreatEvent(id="t1")
        assert event.to_dict()["threat_type"] == "anomaly"
        incident = Incident(id="i1", summary="s")
        assert incident.to_dict()["summary"] == "s"
        alert = SecurityAlert(id="a1")
        assert alert.to_dict()["severity"] == "medium"
        envelope = Envelope.from_dict({"key_id": "k", "iv": "i", "tag": "t", "ciphertext": "c"})
        assert envelope.key_version == 1
        report = ComplianceReport(framework=ComplianceFramework.SOC2, controls=[Control(id="c", name="n", status=ControlStatus.IMPLEMENTED)])
        assert report.to_dict()["readiness"] == 100.0

    def test_siem_headers(self):
        config = make_config(siem_config={"token": "t", "api_key": "k"})
        splunk = SplunkSink(config, transport=None)
        assert splunk._headers()["Authorization"] == "Splunk t"
        elastic = ElasticSink(config, transport=None)
        assert elastic._headers["Authorization"] == "ApiKey k"
        datadog = DatadogSink(config, transport=None)
        assert datadog.url.startswith("https://http-intake")

    def test_siem_registry_custom(self):
        registry = SiemRegistry()
        registry.register("custom", lambda config: StdoutSink(config))
        assert isinstance(registry.create(make_config(siem_backend="custom")), StdoutSink)

    def test_privacy_detection_metrics(self):
        service = create_privacy_service(make_config())
        fields = service.detect("a@b.com and b@c.com")
        assert len(fields) == 2
        assert service.status()["detection_enabled"] is True

    def test_pii_full_mask_short_value(self):
        detector = PIIDetector()
        result = detector.mask("ssn 123-45-6789", mode="full")
        assert result.text.count("***") == 1

    def test_incident_escalate_with_meta(self):
        manager = create_incident_manager(make_config())
        incident = manager.escalate("anomaly:1.1.1.1")
        assert incident.id

    def test_manager_initialize_with_usable_key(self):
        manager = create_security_manager(make_config())
        asyncio_run(manager.initialize())
        asyncio_run(manager.initialize())
        asyncio_run(manager.shutdown())
        assert manager.status()["initialized"] is False
