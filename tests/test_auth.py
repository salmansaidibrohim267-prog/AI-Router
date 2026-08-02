from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

import pytest
from fastapi import Request

from app.auth import (
    APIKeyError,
    APIKeyManager,
    AccountInactiveError,
    AccountLockedError,
    AuthConfig,
    AuthLogger,
    AuthMiddleware,
    AuthMetricsTracker,
    AuthResult,
    AuthenticationManager,
    InvalidCredentialsError,
    InvalidTokenError,
    JWTManager,
    MFARequiredError,
    PermissionDeniedError,
    PermissionPolicy,
    Principal,
    ProviderNotFoundError,
    ServiceAccountError,
    ServiceAccountManager,
    SessionExpiredError,
    SessionLimitError,
    SessionManager,
    SigningKeyStore,
    TokenClaims,
    TokenDenylist,
    TokenExpiredError,
    TokenPair,
    TokenRevokedError,
    User,
    UserStatus,
    create_auth_manager,
    create_auth_middleware,
    hash_password,
    is_strong_password,
    verify_password,
)
from app.auth.api_keys import APIKeyManager as _APIKeyManager
from app.auth.exceptions import (
    AuthError,
    AuthenticationError,
    ProviderError,
    ProviderNotFoundError as _ProviderNotFoundError,
    SessionExpiredError as _SessionExpiredError,
)
from app.auth.hashing import hash_password as _hash_password
from app.auth.manager import _totp_code
from app.auth.models import APIKey, ProviderUser, ServiceAccount, Session, TokenClaims as _TC, TokenPair as _TP, User as _User, UserStatus as _US
from app.auth.providers import (
    CustomProvider,
    LDAPProvider,
    LocalProvider,
    OAuth2Provider,
    OIDCProvider,
    ProviderRegistry,
    SAMLProvider,
    create_provider,
    register_builtin_providers,
)
from app.auth.providers.base import AuthProvider
from app.auth.rbac import Principal as _Principal
from app.auth.repository import (
    APIKeyRepository,
    InMemoryUserRepository,
    ServiceAccountRepository,
    SessionRepository,
    UserRepository,
    generate_secret_token,
)
from app.auth.sessions import SessionManager as _SessionManager
from app.auth.tokens import _b64url_decode, _b64url_encode
from app.tenancy import AuditLogger, TenantManager, TenancyConfig
from app.tenancy.exceptions import TenantNotFoundError


def make_config(**kwargs):
    defaults = {"log_events": False, "track_metrics": True, "audit_enabled": False}
    defaults.update(kwargs)
    return AuthConfig(**defaults)


def make_manager(**kwargs):
    defaults = {"config": make_config()}
    defaults.update(kwargs)
    return create_auth_manager(**defaults)


def make_user(repo=None, username="alice", password="StrongPass123!", tenant_id="t1", **fields):
    manager = make_manager(users=repo) if repo is not None else make_manager()
    user = manager.register_user(username, password, tenant_id=tenant_id, **fields)
    return manager, user


def make_jwt(claims, kid="k1", key="secret"):
    def enc(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    header = enc({"alg": "HS256", "typ": "JWT", "kid": kid})
    body = enc(claims)
    sig = base64.urlsafe_b64encode(
        hmac.new(key.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    return f"{header}.{body}.{sig}"


class FakeASGIApp:
    def __init__(self, status=200):
        self.calls = []
        self.status = status

    async def __call__(self, scope, receive, send):
        self.calls.append(scope)
        await send(
            {
                "type": "http.response.start",
                "status": self.status,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": b"ok"})


def make_scope(headers=None, method="GET", path="/v1/chat"):
    pairs = [(k.encode(), v.encode()) for k, v in (headers or {}).items()]
    return {"type": "http", "method": method, "path": path, "headers": pairs}


async def run_asgi(middleware, scope):
    messages = []

    async def send(message):
        messages.append(message)

    async def receive():
        return {}

    await middleware(scope, receive, send)
    return messages


# ---------------------------------------------------------------- config

def test_auth_config_defaults():
    cfg = AuthConfig()
    assert cfg.access_token_ttl == 900
    assert cfg.refresh_token_ttl == 604800
    assert cfg.max_concurrent_sessions == 5
    assert cfg.public_paths == ("/health", "/metrics")
    assert cfg.require_auth is True


def test_auth_config_from_env(monkeypatch):
    monkeypatch.setenv("AUTH_ACCESS_TTL", "120")
    monkeypatch.setenv("AUTH_MAX_SESSIONS", "2")
    monkeypatch.setenv("AUTH_REQUIRE_AUTH", "0")
    monkeypatch.setenv("AUTH_PUBLIC_PATHS", "/public,/ping")
    cfg = AuthConfig.from_env()
    assert cfg.access_token_ttl == 120
    assert cfg.max_concurrent_sessions == 2
    assert cfg.require_auth is False
    assert cfg.public_paths == ("/public", "/ping")


# ---------------------------------------------------------------- hashing

def test_hash_password_roundtrip():
    stored = hash_password("hunter2", iterations=1000)
    assert stored.startswith("pbkdf2_sha256$1000$")
    assert verify_password("hunter2", stored) is True
    assert verify_password("wrong", stored) is False


def test_verify_password_malformed():
    assert verify_password("x", "") is False
    assert verify_password("x", "not-a-valid-format") is False
    assert verify_password("x", "pbkdf2_sha256$abc$zz$zz") is False


def test_is_strong_password():
    cfg = make_config(password_min_length=8)
    assert is_strong_password("Abcdef12!", cfg) is True
    assert is_strong_password("short1!", cfg) is False
    assert is_strong_password("abcdefgh!", cfg) is False
    assert is_strong_password("ABCDEFGH!", cfg) is False
    assert is_strong_password("Abcdefgh", cfg) is False
    assert is_strong_password("Abcdef12", cfg) is False
    mfa_cfg = make_config(mfa_enabled=True)
    assert is_strong_password("Abcdef12", mfa_cfg) is True


# ---------------------------------------------------------------- logging + statistics

def test_auth_logger(caplog):
    with caplog.at_level("INFO"):
        AuthLogger().log_event("login", tenant_id="t1", user_id="u1", extra_field=1)
    assert any("auth_login" in r.message for r in caplog.records)


def test_metrics_tracker():
    m = AuthMetricsTracker(make_config())
    m.record("login_success", "t1")
    m.record("login_success", "t1")
    m.record("login_failed", "t2")
    summary = m.summary()
    assert summary["events"]["login_success"] == 2
    assert summary["per_tenant"]["t1"]["login_success"] == 2
    m.reset()
    assert m.summary()["events"] == {}
    assert m.enabled is True
    disabled = AuthMetricsTracker(make_config(track_metrics=False))
    disabled.record("x")
    assert disabled.summary()["events"] == {}


# ---------------------------------------------------------------- models

def test_user_model():
    user = _User(id="u1", username="bob", roles=["admin"], tenant_id="t1")
    assert user.is_active is True
    assert user.is_locked is False
    locked = _User(id="u2", username="x", status=_US.LOCKED, locked_until=time.time() + 100)
    assert locked.is_locked is True
    d = user.to_dict()
    assert d["username"] == "bob"
    assert d["roles"] == ["admin"]


def test_session_model():
    s = Session(id="s1", user_id="u1")
    assert s.is_expired is False
    old = Session(id="s2", user_id="u1", expires_at=time.time() - 10)
    assert old.is_expired is True
    assert s.to_dict()["user_id"] == "u1"
    assert old.to_dict()["revoked"] is False


def test_token_claims_from_dict():
    claims = _TC.from_dict({"sub": "u1", "tenant_id": "t1", "roles": ["a"], "type": "refresh", "jti": "j", "sid": "s", "iat": 1, "exp": 2})
    assert claims.sub == "u1"
    assert claims.token_type == "refresh"
    assert claims.session_id == "s"
    assert claims.exp == 2.0
    empty = _TC.from_dict({})
    assert empty.sub == ""
    assert empty.roles == []


def test_token_pair_to_dict():
    pair = _TP(access_token="a", refresh_token="r", access_jti="j1", refresh_jti="j2", expires_in=60)
    d = pair.to_dict()
    assert d["token_type"] == "bearer"
    assert d["expires_in"] == 60


def test_api_key_and_service_account_models():
    key = APIKey(id="k1", tenant_id="t1", name="n", key_prefix="ak_", key_hash="h")
    assert key.is_expired is False
    old = APIKey(id="k2", tenant_id="t1", name="n", key_prefix="ak_", key_hash="h", expires_at=time.time() - 5)
    assert old.is_expired is True
    assert key.to_dict()["name"] == "n"
    acc = ServiceAccount(id="s1", tenant_id="t1", name="sa", token_hash="h")
    assert acc.is_expired is False
    assert acc.to_dict()["token_hash"] == "h"


def test_auth_result_to_dict():
    user = _User(id="u1", username="bob")
    result = AuthResult(user=user, method="local", mfa_required=True)
    d = result.to_dict()
    assert d["mfa_required"] is True
    assert d["user"]["id"] == "u1"
    assert AuthResult(user=None).to_dict()["user"] is None


# ---------------------------------------------------------------- tokens

def test_b64url_roundtrip():
    data = b"hello world"
    assert _b64url_decode(_b64url_encode(data)) == data
    assert _b64url_decode("aGVsbG8") == b"hello"


def test_signing_key_store():
    store = SigningKeyStore("secret", rotation_seconds=10, max_history=2)
    kid, key = store.current
    assert key == "secret"
    assert len(store.list_kids()) == 1
    assert store.get(kid) == "secret"
    assert store.get("nope") is None
    kid2, key2 = store.rotate("newsecret")
    assert key2 == "newsecret"
    assert kid2 != kid
    assert len(store.list_kids()) == 2
    assert store.get(kid) == "secret"
    assert store.should_rotate(now=time.time() + 100) is True
    assert store.should_rotate() is False
    store.rotate("third")
    assert len(store.list_kids()) == 2
    assert len(store.export_keys()) == 2
    assert store.current[0] != kid2


def test_token_denylist():
    dl = TokenDenylist()
    dl.revoke("j1", time.time() + 100)
    assert dl.is_revoked("j1") is True
    assert dl.is_revoked("j2") is False
    assert dl.size() == 1
    assert dl.is_revoked("j1", now=time.time() + 200) is False
    assert dl.size() == 0


def test_jwt_issue_parse_validate():
    jwt = JWTManager("secret", make_config())
    claims = TokenClaims(sub="u1", tenant_id="t1", roles=["viewer"])
    token = jwt.issue(claims)
    payload = jwt.parse(token)
    assert payload["sub"] == "u1"
    assert payload["type"] == "access"
    parsed = jwt.validate(token)
    assert parsed.sub == "u1"
    assert parsed.roles == ["viewer"]


def test_jwt_malformed():
    jwt = JWTManager("secret", make_config())
    with pytest.raises(InvalidTokenError):
        jwt.parse("not.a.token")
    with pytest.raises(InvalidTokenError):
        jwt.parse("a.b")
    with pytest.raises(InvalidTokenError):
        jwt.parse("!!.bb.ccc")
    with pytest.raises(InvalidTokenError):
        jwt.parse(make_jwt({"sub": "u"}, kid="unknown", key="secret"))
    with pytest.raises(InvalidTokenError):
        jwt.parse(make_jwt({"sub": "u"}, kid="k1", key="wrongkey"))
    with pytest.raises(InvalidTokenError):
        jwt.parse("e30.e30.sig")


def test_jwt_validate_types_and_expiry():
    jwt = JWTManager("secret", make_config(access_token_ttl=900))
    token = jwt.issue(TokenClaims(sub="u1", token_type="access"))
    with pytest.raises(InvalidTokenError):
        jwt.validate(token, token_type="refresh")
    expired = jwt.issue(TokenClaims(sub="u1", token_type="access", iat=time.time() - 1000, exp=time.time() - 100))
    with pytest.raises(TokenExpiredError):
        jwt.validate(expired)


def test_jwt_pair_and_revoke():
    jwt = JWTManager("secret", make_config())
    pair = jwt.issue_pair("u1", "t1", ["viewer"], "s1")
    assert jwt.validate(pair.access_token).session_id == "s1"
    assert jwt.validate(pair.refresh_token, token_type="refresh").sub == "u1"
    jti = jwt.revoke_token(pair.access_token)
    assert jti == pair.access_jti
    with pytest.raises(TokenRevokedError):
        jwt.validate(pair.access_token)


def test_jwt_rotate_pair():
    jwt = JWTManager("secret", make_config())
    pair = jwt.issue_pair("u1", "t1", ["viewer"], "s1")
    new_pair = jwt.rotate_pair(pair.refresh_token, "s1")
    assert new_pair.refresh_jti != pair.refresh_jti
    with pytest.raises(TokenRevokedError):
        jwt.validate(pair.refresh_token, token_type="refresh")


def test_jwt_rotate_keys_keeps_validation():
    jwt = JWTManager("secret", make_config())
    token = jwt.issue(TokenClaims(sub="u1"))
    kid = jwt.rotate_keys()
    assert kid
    assert jwt.validate(token).sub == "u1"
    assert jwt.parse(token)["sub"] == "u1"


# ---------------------------------------------------------------- sessions

def test_session_manager_create_and_validate():
    sm = _SessionManager(make_config())
    s = sm.create("u1", tenant_id="t1")
    assert s.id.startswith("ses_")
    assert sm.validate(s.id).id == s.id
    assert sm.touch(s.id).last_active > 0
    assert sm.repository.count_active("u1") == 1


def test_session_manager_missing_and_revoke():
    sm = _SessionManager(make_config())
    with pytest.raises(_SessionExpiredError):
        sm.get("nope")
    s = sm.create("u1")
    assert sm.revoke(s.id) is True
    with pytest.raises(_SessionExpiredError):
        sm.validate(s.id)


def test_session_manager_expired():
    sm = _SessionManager(make_config(session_absolute_timeout=1))
    s = sm.create("u1")
    time.sleep(1.1)
    with pytest.raises(_SessionExpiredError):
        sm.validate(s.id)
    assert sm.get(s.id).revoked is True


def test_session_manager_idle_timeout():
    sm = _SessionManager(make_config(session_idle_timeout=1))
    s = sm.create("u1")
    time.sleep(1.1)
    with pytest.raises(_SessionExpiredError):
        sm.touch(s.id)
    assert sm.get(s.id).revoked is True


def test_session_manager_limit_evict():
    sm = _SessionManager(make_config(max_concurrent_sessions=2, evict_oldest_on_limit=True))
    s1 = sm.create("u1", device="a")
    time.sleep(0.01)
    s2 = sm.create("u1", device="b")
    time.sleep(0.01)
    s3 = sm.create("u1", device="c")
    assert sm.get(s1.id).revoked is True
    assert sm.get(s2.id).revoked is False
    assert sm.get(s3.id).revoked is False
    assert sm.repository.count_active("u1") == 2


def test_session_manager_limit_raises():
    sm = _SessionManager(make_config(max_concurrent_sessions=2, evict_oldest_on_limit=False))
    sm.create("u1")
    sm.create("u1")
    with pytest.raises(SessionLimitError):
        sm.create("u1")


def test_session_manager_revoke_all_and_list():
    sm = _SessionManager(make_config())
    sm.create("u1", device="a")
    sm.create("u1", device="b")
    sm.create("u2", device="a")
    assert len(sm.list("u1")) == 2
    assert len(sm.list()) == 3
    assert sm.revoke_all("u1") == 2
    assert len(sm.list("u1")) == 0
    assert sm.repository.delete_for_user("u2") == 1


def test_session_repository_crud():
    repo = SessionRepository()
    s = Session(id="s1", user_id="u1")
    repo.create(s)
    assert repo.get("s1") is s
    assert repo.get("nope") is None
    s2 = Session(id="s1", user_id="u1", revoked=True)
    repo.update(s2)
    assert repo.get("s1").revoked is True
    assert repo.list_for_user("u1") == []
    repo.delete_for_user("u1")
    assert repo.get("s1") is None
    s3 = Session(id="s2", user_id="u2")
    repo.create(s3)
    assert repo.delete("s2") is True
    assert repo.delete("s2") is False
    s4 = Session(id="s3", user_id="u3")
    repo.create(s4)
    assert repo.list_all()[0].id == "s3"


# ---------------------------------------------------------------- repositories

def test_user_repository():
    repo = InMemoryUserRepository()
    u = User(id="u1", username="a", tenant_id="t1")
    repo.create(u)
    with pytest.raises(InvalidCredentialsError):
        repo.create(u)
    assert repo.get("u1") is u
    with pytest.raises(InvalidCredentialsError):
        repo.get("nope")
    assert repo.get_by_username("a", "t1").id == "u1"
    assert repo.get_by_username("a").id == "u1"
    with pytest.raises(InvalidCredentialsError):
        repo.get_by_username("a", "t2")
    with pytest.raises(InvalidCredentialsError):
        repo.get_by_username("nope")
    repo.update(u)
    with pytest.raises(InvalidCredentialsError):
        repo.update(User(id="nope", username="x"))
    repo.create(User(id="u2", username="b", tenant_id="t2"))
    assert len(repo.list("t1")) == 1
    assert len(repo.list()) == 2
    assert repo.delete("u2") is True
    assert repo.delete("u2") is False


def test_api_key_repository():
    repo = APIKeyRepository()
    k = APIKey(id="k1", tenant_id="t1", name="n", key_prefix="ak", key_hash="h1")
    repo.create(k)
    assert repo.get("k1") is k
    assert repo.get_by_hash("h1") is k
    assert repo.get_by_hash("nope") is None
    repo.create(APIKey(id="k2", tenant_id="t2", name="m", key_prefix="ak", key_hash="h2"))
    assert len(repo.list_for_tenant("t1")) == 1
    assert len(repo.list_all()) == 2
    repo.update(APIKey(id="k1", tenant_id="t1", name="n", key_prefix="ak", key_hash="h3"))
    assert repo.get("k1").key_hash == "h3"
    assert repo.delete("k2") is True
    assert repo.delete("k2") is False


def test_service_account_repository():
    repo = ServiceAccountRepository()
    repo.create(ServiceAccount(id="s1", tenant_id="t1", name="n", token_hash="h1"))
    assert repo.get("s1") is not None
    assert repo.get_by_token_hash("h1").id == "s1"
    assert repo.get_by_token_hash("nope") is None
    repo.create(ServiceAccount(id="s2", tenant_id="t2", name="m", token_hash="h2"))
    assert len(repo.list_for_tenant("t1")) == 1
    assert len(repo.list_all()) == 2
    assert repo.delete("s2") is True
    assert repo.delete("s2") is False


def test_generate_secret_token():
    assert generate_secret_token().startswith("tok_")
    assert generate_secret_token() != generate_secret_token()


# ---------------------------------------------------------------- rbac

def test_principal():
    user = _User(id="u1", username="bob", roles=["admin"], tenant_id="t1")
    p = _Principal.from_user(user)
    assert p.is_admin is True
    assert p.to_dict()["user_id"] == "u1"
    p2 = _Principal(user_id="u2", tenant_id="t1", roles=["viewer"], method="apikey", service=True)
    assert p2.is_admin is False
    assert p2.service is True


def test_permission_policy():
    policy = PermissionPolicy()
    viewer = _Principal(user_id="u1", tenant_id="t1", roles=["viewer"])
    admin = _Principal(user_id="u2", tenant_id="t1", roles=["admin"])
    assert policy.check(viewer, "read:chat") is True
    assert policy.check(viewer, "write:chat") is False
    assert policy.check(admin, "anything") is True
    assert policy.check(viewer, "read:chat", tenant_id="t2") is False
    policy.register_role("custom", {"deploy"})
    custom = _Principal(user_id="u3", tenant_id="t1", roles=["custom"])
    assert policy.check(custom, "deploy") is True
    assert policy.permissions_for(["custom"]) == {"deploy"}
    with pytest.raises(PermissionDeniedError) as exc:
        policy.enforce(viewer, "write:chat")
    assert exc.value.permission == "write:chat"
    assert exc.value.user_id == "u1"


def test_permission_policy_deny_and_scopes():
    policy = PermissionPolicy(deny_permissions={"read:secrets"})
    admin = _Principal(user_id="u2", tenant_id="t1", roles=["admin"])
    assert policy.check(admin, "read:secrets") is False
    scoped = _Principal(user_id="u1", tenant_id="t1", scopes=["read:chat"])
    assert policy.scopes_allow(scoped, "read:chat") is True
    assert policy.scopes_allow(scoped, "write:chat") is False
    all_scope = _Principal(user_id="u1", tenant_id="t1", scopes=["*"])
    assert policy.scopes_allow(all_scope, "anything") is True


# ---------------------------------------------------------------- providers

def test_local_provider_ok():
    cfg = make_config(password_hash_iterations=1000)
    manager = make_manager(config=cfg)
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    provider = manager.providers.get("local")
    assert isinstance(provider, LocalProvider)
    result = asyncio_run(provider.authenticate({"username": "alice", "password": "StrongPass123!", "tenant_id": "t1"}))
    assert result.id and result.username == "alice"


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)


def test_local_provider_missing_credentials():
    provider = LocalProvider(config=make_config())
    with pytest.raises(InvalidCredentialsError):
        asyncio_run(provider.authenticate({}))
    with pytest.raises(InvalidCredentialsError):
        asyncio_run(provider.authenticate({"username": "", "password": "x"}))


def test_local_provider_wrong_password_locks():
    cfg = make_config(password_hash_iterations=1000, max_login_attempts=2, lockout_seconds=300)
    manager = make_manager(config=cfg)
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    provider = manager.providers.get("local")
    for _ in range(2):
        with pytest.raises(InvalidCredentialsError):
            asyncio_run(provider.authenticate({"username": "alice", "password": "Wrong123!", "tenant_id": "t1"}))
    user = manager.users.get_by_username("alice", "t1")
    assert user.failed_attempts == 2
    assert user.locked_until > 0
    with pytest.raises(AccountLockedError) as exc:
        asyncio_run(provider.authenticate({"username": "alice", "password": "StrongPass123!", "tenant_id": "t1"}))
    assert exc.value.locked_until > 0


def test_local_provider_locked_then_reset():
    cfg = make_config(password_hash_iterations=1000)
    manager = make_manager(config=cfg)
    user = manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    user.locked_until = time.time() - 10
    user.status = UserStatus.ACTIVE
    manager.users.update(user)
    provider = manager.providers.get("local")
    result = asyncio_run(provider.authenticate({"username": "alice", "password": "StrongPass123!", "tenant_id": "t1"}))
    assert result.username == "alice"
    assert manager.users.get(user.id).failed_attempts == 0


def test_local_provider_inactive():
    cfg = make_config(password_hash_iterations=1000)
    manager = make_manager(config=cfg)
    user = manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    user.status = UserStatus.SUSPENDED
    manager.users.update(user)
    with pytest.raises(AccountInactiveError):
        asyncio_run(manager.providers.get("local").authenticate({"username": "alice", "password": "StrongPass123!", "tenant_id": "t1"}))
    user.status = UserStatus.DISABLED
    manager.users.update(user)
    with pytest.raises(AccountInactiveError):
        asyncio_run(manager.providers.get("local").authenticate({"username": "alice", "password": "StrongPass123!", "tenant_id": "t1"}))


def test_local_provider_register_and_find():
    provider = LocalProvider(config=make_config())
    user = provider.register_user(User(id="u9", username="zed"))
    assert provider.find_user("zed").id == "u9"
    assert provider.users is not None


def test_oauth2_provider_code_flow():
    def transport(url, payload):
        if "token" in url:
            return {"access_token": "at_123"}
        return {"sub": "s1", "username": "bob", "email": "bob@x.io", "roles": ["admin"], "name": "Bob"}
    provider = OAuth2Provider(
        token_endpoint="https://idp/token",
        userinfo_endpoint="https://idp/userinfo",
        client_id="cid",
        client_secret="csecret",
        transport=transport,
    )
    result = asyncio_run(provider.authenticate({"grant_type": "authorization_code", "code": "c1", "redirect_uri": "http://app/cb"}))
    assert result.id == "s1"
    assert result.email == "bob@x.io"
    assert result.roles == ["admin"]
    assert result.attributes["sub"] == "s1"


def test_oauth2_provider_other_grants():
    def transport(url, payload):
        return {"access_token": "at_1"}
    provider = OAuth2Provider(token_endpoint="https://idp/token", client_id="c", transport=transport)
    r1 = asyncio_run(provider.authenticate({"grant_type": "client_credentials", "access_token": "at_manual"}))
    assert r1.username.startswith("oauth_")
    r2 = asyncio_run(provider.authenticate({"grant_type": "password", "username": "bob", "password": "pw"}))
    assert r2.username.startswith("oauth_")
    with pytest.raises(ProviderError):
        asyncio_run(provider.authenticate({"grant_type": "nope"}))
    with pytest.raises(ProviderError):
        asyncio_run(provider.authenticate({"grant_type": "client_credentials"}))
    assert provider.metadata["name"] == "oauth2"


def test_oauth2_provider_failures():
    def transport(url, payload):
        return {"error": "denied"}
    provider = OAuth2Provider(token_endpoint="https://idp/token", client_id="c", transport=transport)
    with pytest.raises(ProviderError):
        asyncio_run(provider.authenticate({"grant_type": "authorization_code", "code": "c"}))
    with pytest.raises(ProviderError):
        asyncio_run(provider.authenticate({"grant_type": "password", "username": "b", "password": "p"}))


def test_oauth2_provider_transport_exception():
    def transport(url, payload):
        raise RuntimeError("boom")
    provider = OAuth2Provider(token_endpoint="https://idp/token", client_id="c", transport=transport)
    with pytest.raises(ProviderError):
        asyncio_run(provider.authenticate({"grant_type": "password", "username": "b", "password": "p"}))


def test_oidc_provider_valid_token():
    def make_id_token(claims, secret="clientsecret", kid="k1"):
        def enc(obj):
            return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
        header = enc({"alg": "HS256", "kid": kid})
        body = enc(claims)
        sig = base64.urlsafe_b64encode(hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
        return f"{header}.{body}.{sig}"
    now = time.time()
    claims = {"iss": "https://idp.example", "aud": "myclient", "sub": "sub_1", "exp": now + 300, "nbf": now - 10, "email": "a@b.io", "preferred_username": "alice", "roles": ["viewer"]}
    token = make_id_token(claims)
    provider = OIDCProvider(client_id="myclient", client_secret="clientsecret", issuer="https://idp.example")
    result = asyncio_run(provider.authenticate({"id_token": token}))
    assert result.id == "sub_1"
    assert result.email == "a@b.io"
    assert result.roles == ["viewer"]
    assert result.attributes["iss"] == "https://idp.example"


def test_oidc_provider_missing_token():
    provider = OIDCProvider(client_id="c")
    with pytest.raises(ProviderError):
        asyncio_run(provider.authenticate({}))


def test_oidc_provider_validation_failures():
    def make_id_token(claims, secret="s", kid="k1"):
        def enc(obj):
            return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
        header = enc({"alg": "HS256", "kid": kid})
        body = enc(claims)
        sig = base64.urlsafe_b64encode(hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
        return f"{header}.{body}.{sig}"
    now = time.time()
    provider = OIDCProvider(client_id="c", client_secret="s", issuer="https://idp")
    base = {"iss": "https://idp", "aud": "c", "sub": "s1", "exp": now + 300}
    with pytest.raises(InvalidTokenError):
        asyncio_run(provider.authenticate({"id_token": "a.b.c.d"}))
    with pytest.raises(InvalidTokenError):
        asyncio_run(provider.authenticate({"id_token": "!!.b.c"}))
    bad_sig = make_id_token(base, secret="other")
    with pytest.raises(InvalidTokenError):
        asyncio_run(provider.authenticate({"id_token": bad_sig}))
    bad_iss = make_id_token({**base, "iss": "https://evil"})
    with pytest.raises(InvalidTokenError):
        asyncio_run(provider.authenticate({"id_token": bad_iss}))
    bad_aud = make_id_token({**base, "aud": "other"})
    with pytest.raises(InvalidTokenError):
        asyncio_run(provider.authenticate({"id_token": bad_aud}))
    expired = make_id_token({**base, "exp": now - 10})
    with pytest.raises(InvalidTokenError):
        asyncio_run(provider.authenticate({"id_token": expired}))
    future = make_id_token({**base, "nbf": now + 1000})
    with pytest.raises(InvalidTokenError):
        asyncio_run(provider.authenticate({"id_token": future}))
    no_sub = make_id_token({"iss": "https://idp", "aud": "c", "exp": now + 300})
    with pytest.raises(InvalidTokenError):
        asyncio_run(provider.authenticate({"id_token": no_sub}))


def test_oidc_provider_alg_and_keys():
    def enc(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
    now = time.time()
    claims = {"iss": "https://idp", "aud": "c", "sub": "s1", "exp": now + 300}
    provider = OIDCProvider(client_id="c", client_secret="s", issuer="https://idp")
    header = enc({"alg": "RS256", "kid": "k1"})
    body = enc(claims)
    token = f"{header}.{body}.sig"
    with pytest.raises(InvalidTokenError):
        asyncio_run(provider.authenticate({"id_token": token}))
    with pytest.raises(InvalidTokenError):
        asyncio_run(provider.authenticate({"id_token": token}))


def test_oidc_provider_discovery():
    def transport(url, payload):
        return {"issuer": "https://idp"}
    def enc(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
    now = time.time()
    claims = {"iss": "https://idp", "aud": "c", "sub": "s1", "exp": now + 300}
    header = enc({"alg": "HS256", "kid": "k1"})
    body = enc(claims)
    sig = base64.urlsafe_b64encode(hmac.new(b"s", f"{header}.{body}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    token = f"{header}.{body}.{sig}"
    provider = OIDCProvider(client_id="c", client_secret="s", discovery_url="https://idp/.well-known", transport=transport)
    result = asyncio_run(provider.authenticate({"id_token": token}))
    assert result.id == "s1"
    assert provider._discover()["issuer"] == "https://idp"
    bad = OIDCProvider(client_id="c", discovery_url="https://idp/.well-known", transport=lambda u, p: {"bad": 1})
    assert bad._discover() == {"bad": 1}


def test_oidc_provider_discovery_failure():
    provider = OIDCProvider(client_id="c", discovery_url="https://idp/.well-known", transport=lambda u, p: "nope")
    with pytest.raises(ProviderError):
        provider._discover()


def test_ldap_provider_ok():
    def bind(username, password, tenant_id=""):
        return {"dn": f"cn={username},dc=x", "attributes": {"cn": username, "mail": f"{username}@x.io", "displayName": "Al", "memberOf": ["ROLE_A"]}}
    provider = LDAPProvider(bind=bind)
    result = asyncio_run(provider.authenticate({"username": "alice", "password": "pw", "tenant_id": "t1"}))
    assert result.id == "cn=alice,dc=x"
    assert result.email == "alice@x.io"
    assert result.roles == ["ROLE_A"]
    assert result.tenant_id == "t1"
    assert result.display_name == "Al"


def test_ldap_provider_failures():
    provider = LDAPProvider(bind=lambda u, p, t: None)
    with pytest.raises(InvalidCredentialsError):
        asyncio_run(provider.authenticate({}))
    with pytest.raises(InvalidCredentialsError):
        asyncio_run(provider.authenticate({"username": "a"}))
    with pytest.raises(InvalidCredentialsError):
        asyncio_run(provider.authenticate({"username": "a", "password": "p"}))
    failing = LDAPProvider(bind=lambda u, p, t: (_ for _ in ()).throw(RuntimeError("down")))
    with pytest.raises(ProviderError):
        asyncio_run(failing.authenticate({"username": "a", "password": "p"}))
    raising = LDAPProvider(bind=lambda u, p, t: (_ for _ in ()).throw(ProviderError("nope")))
    with pytest.raises(ProviderError):
        asyncio_run(raising.authenticate({"username": "a", "password": "p"}))


def test_saml_provider_ok():
    xml = """<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
      <saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
        <saml:Conditions NotBefore="2020-01-01T00:00:00Z" NotOnOrAfter="2099-01-01T00:00:00Z"/>
        <saml:Subject><saml:NameID>user-123</saml:NameID></saml:Subject>
        <saml:AttributeStatement>
          <saml:Attribute Name="email"><saml:AttributeValue>a@b.io</saml:AttributeValue></saml:Attribute>
          <saml:Attribute Name="cn"><saml:AttributeValue>alice</saml:AttributeValue></saml:Attribute>
          <saml:Attribute Name="displayName"><saml:AttributeValue>Alice</saml:AttributeValue></saml:Attribute>
          <saml:Attribute Name="roles"><saml:AttributeValue>admin,ops</saml:AttributeValue></saml:Attribute>
        </saml:AttributeStatement>
      </saml:Assertion>
    </samlp:Response>"""
    provider = SAMLProvider(entity_id="https://app")
    result = asyncio_run(provider.authenticate({"response": xml}))
    assert result.id == "user-123"
    assert result.email == "a@b.io"
    assert result.roles == ["admin", "ops"]
    assert result.display_name == "Alice"


def test_saml_provider_failures():
    provider = SAMLProvider(entity_id="https://app")
    with pytest.raises(InvalidCredentialsError):
        asyncio_run(provider.authenticate({}))
    with pytest.raises(ProviderError):
        asyncio_run(provider.authenticate({"response": "not-xml"}))
    strict = SAMLProvider(entity_id="https://app", verify_assertion=lambda raw: False)
    with pytest.raises(ProviderError):
        asyncio_run(strict.authenticate({"response": "<x/>"}))
    with pytest.raises(ProviderError):
        asyncio_run(provider.authenticate({"response": "<samlp:Response xmlns:samlp='urn:oasis:names:tc:SAML:2.0:protocol'><saml:Assertion xmlns:saml='urn:oasis:names:tc:SAML:2.0:assertion'/></samlp:Response>"}))


def test_saml_provider_time_windows():
    def xml(not_before, not_after):
        return f"""<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
          <saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
            <saml:Conditions NotBefore="{not_before}" NotOnOrAfter="{not_after}"/>
            <saml:Subject><saml:NameID>u1</saml:NameID></saml:Subject>
          </saml:Assertion>
        </samlp:Response>"""
    future = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))
    past = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600))
    provider = SAMLProvider(entity_id="https://app")
    with pytest.raises(InvalidCredentialsError):
        asyncio_run(provider.authenticate({"response": xml(future, "2099-01-01T00:00:00Z")}))
    with pytest.raises(InvalidCredentialsError):
        asyncio_run(provider.authenticate({"response": xml("2020-01-01T00:00:00Z", past)}))
    result = asyncio_run(provider.authenticate({"response": xml("garbage", "2099-01-01T00:00:00Z")}))
    assert result.id == "u1"


def test_custom_provider():
    def handler(credentials):
        return ProviderUser(id="cu1", username=credentials["username"])
    provider = CustomProvider(handler=handler)
    result = asyncio_run(provider.authenticate({"username": "zed"}))
    assert result.id == "cu1"
    bare = CustomProvider()
    with pytest.raises(ProviderError):
        asyncio_run(bare.authenticate({}))
    bad = CustomProvider(handler=lambda c: "nope")
    with pytest.raises(ProviderError):
        asyncio_run(bad.authenticate({}))
    failing = CustomProvider(handler=lambda c: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(ProviderError):
        asyncio_run(failing.authenticate({}))
    passing = CustomProvider(handler=lambda c: (_ for _ in ()).throw(ProviderError("x")))
    with pytest.raises(ProviderError):
        asyncio_run(passing.authenticate({}))


def test_provider_registry():
    registry = ProviderRegistry()
    provider = LocalProvider(config=make_config())
    registry.register(provider)
    assert registry.get("local") is provider
    assert registry.has("local") is True
    assert registry.names() == ["local"]
    assert registry.unregister("local") is True
    assert registry.has("local") is False
    with pytest.raises(ProviderNotFoundError):
        registry.get("local")


def test_create_provider_factory():
    assert isinstance(create_provider("local"), LocalProvider)
    assert isinstance(create_provider("custom", handler=lambda c: ProviderUser(id="1", username="u")), CustomProvider)
    assert isinstance(create_provider("oauth2", token_endpoint="https://x", client_id="c"), OAuth2Provider)
    assert isinstance(create_provider("oidc", client_id="c"), OIDCProvider)
    assert isinstance(create_provider("ldap"), LDAPProvider)
    assert isinstance(create_provider("saml", entity_id="e"), SAMLProvider)
    with pytest.raises(ProviderNotFoundError):
        create_provider("nope")
    registry = ProviderRegistry()
    register_builtin_providers(registry)
    register_builtin_providers(registry)
    assert registry.has("local") is True
    custom = CustomProvider(handler=lambda c: ProviderUser(id="1", username="u"))
    registry.register(custom)
    assert create_provider("custom", registry=registry) is custom


def test_auth_provider_base():
    class P(AuthProvider):
        async def authenticate(self, credentials):
            return ProviderUser(id="1", username="u")
    p = P(secret="hidden", visible=1)
    assert p.metadata["options"] == {"visible": 1}


# ---------------------------------------------------------------- api keys + service accounts

def test_api_key_manager_lifecycle():
    mgr = APIKeyManager(make_config())
    key, raw = mgr.generate("t1", "ci-key", scopes=["read"])
    assert raw.startswith("ak_")
    assert key.key_prefix == raw[:10]
    authed = mgr.authenticate(raw)
    assert authed.id == key.id
    assert authed.usage_count == 1
    with pytest.raises(APIKeyError):
        mgr.authenticate("ak_wrong")
    with pytest.raises(APIKeyError):
        mgr.authenticate(raw, require_scopes=["write"])
    assert mgr.authenticate(raw, require_scopes=["read"]).id == key.id
    assert mgr.revoke(key.id) is True
    with pytest.raises(APIKeyError):
        mgr.authenticate(raw)
    with pytest.raises(APIKeyError):
        mgr.revoke("nope")


def test_api_key_manager_expired_and_rotate_and_list():
    mgr = APIKeyManager(make_config())
    key, raw = mgr.generate("t1", "temp", ttl=1)
    time.sleep(1.1)
    with pytest.raises(APIKeyError):
        mgr.authenticate(raw)
    key2, raw2 = mgr.generate("t1", "k2")
    rotated, raw3 = mgr.rotate(key2.id)
    assert rotated.name == "k2"
    assert mgr.authenticate(raw3).id == rotated.id
    mgr.generate("t2", "other")
    assert len(mgr.list("t1")) == 3
    assert len(mgr.list()) == 4


def test_service_account_manager_lifecycle():
    mgr = ServiceAccountManager(make_config())
    acc, raw = mgr.create("t1", "deploy", scopes=["deploy"], description="ci")
    assert raw.startswith("sa_")
    authed = mgr.authenticate(raw)
    assert authed.id == acc.id
    assert authed.usage_count == 1
    with pytest.raises(ServiceAccountError):
        mgr.authenticate("sa_wrong")
    with pytest.raises(ServiceAccountError):
        mgr.authenticate(raw, require_scopes=["admin"])
    assert mgr.authenticate(raw, require_scopes=["deploy"]).id == acc.id
    assert mgr.revoke(acc.id) is True
    with pytest.raises(ServiceAccountError):
        mgr.authenticate(raw)
    with pytest.raises(ServiceAccountError):
        mgr.revoke("nope")
    acc2, raw2 = mgr.create("t1", "temp", ttl=1)
    time.sleep(1.1)
    with pytest.raises(ServiceAccountError):
        mgr.authenticate(raw2)
    rotated, raw3 = mgr.rotate(acc2.id)
    assert mgr.authenticate(raw3).id == rotated.id
    mgr.create("t2", "other")
    assert len(mgr.list("t1")) == 3
    assert len(mgr.list()) == 4


# ---------------------------------------------------------------- manager

def test_register_user_weak_password():
    manager = make_manager()
    with pytest.raises(InvalidCredentialsError):
        manager.register_user("weak", "short1!")


def test_login_success_and_validate():
    manager = make_manager()
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    result = asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1", device="laptop"))
    assert result.method == "local"
    assert isinstance(result.token_pair, TokenPair)
    assert result.session.device == "laptop"
    assert result.principal.user_id == result.user.id
    principal = manager.validate(result.token_pair.access_token)
    assert principal.user_id == result.user.id
    assert principal.tenant_id == "t1"
    assert principal.roles == ["viewer"]
    assert principal.method == "token"


def test_login_failure_metrics_and_audit():
    audit = AuditLogger(TenancyConfig(audit_enabled=True))
    manager = make_manager(audit=audit)
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    with pytest.raises(InvalidCredentialsError):
        asyncio_run(manager.login("alice", "wrongpass", tenant_id="t1"))
    summary = manager.get_metrics()
    assert summary["events"]["login_failed"] == 1
    assert audit.count() == 1
    assert audit.list()[0].action == "auth.login"
    assert audit.list()[0].outcome == "failure"


def test_login_unknown_user():
    manager = make_manager()
    with pytest.raises(InvalidCredentialsError):
        asyncio_run(manager.login("ghost", "whatever1", tenant_id="t1"))


def test_login_mfa_flow():
    cfg = make_config(mfa_enabled=True, password_hash_iterations=1000)
    manager = make_manager(config=cfg)
    secret = "JBSWY3DPEHPK3PXP"
    manager.register_user("alice", "StrongPass123!", tenant_id="t1", mfa_secret=secret)
    result = asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))
    assert result.mfa_required is True
    assert result.token_pair is None
    code = _totp_code(secret)
    result2 = asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1", mfa_code=code))
    assert result2.token_pair is not None
    assert asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1", mfa_code="000000")).token_pair is None


def test_login_with_provider_reconcile():
    cfg = make_config(password_hash_iterations=1000)
    manager = make_manager(config=cfg)
    def handler(credentials):
        return ProviderUser(id="ext1", username="external", email="e@x.io", roles=["operator"], tenant_id="t1")
    manager.providers.register(CustomProvider(name="custom", handler=handler) if False else CustomProvider(handler=handler))
    manager.providers.unregister("custom")
    manager.providers.register(CustomProvider(handler=handler))
    result = asyncio_run(manager.login_with("custom", {"token": "x"}, device="d"))
    assert result.principal.user_id == "ext1"
    assert result.principal.method == "custom"
    assert manager.users.get("ext1").roles == ["operator"]
    result2 = asyncio_run(manager.login_with("custom", {"token": "x"}))
    assert result2.principal.user_id == "ext1"


def test_login_with_oauth_provider():
    def transport(url, payload):
        return {"access_token": "at"}
    manager = make_manager()
    provider = OAuth2Provider(token_endpoint="https://idp/token", client_id="c", transport=transport)
    manager.providers.register(provider)
    result = asyncio_run(manager.login_with("oauth2", {"grant_type": "client_credentials", "access_token": "at"}, device="d"))
    assert result.principal.tenant_id == ""
    assert manager.users.get(result.principal.user_id) is not None


def test_login_tenant_manager_integration():
    tenant_manager = TenantManager(config=TenancyConfig())
    tenant_manager.create("Acme", tenant_id="t1")
    manager = make_manager(tenant_manager=tenant_manager)
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    result = asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))
    assert result.token_pair is not None
    with pytest.raises(AuthenticationError):
        asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t_missing"))


def test_login_session_limit():
    cfg = make_config(max_concurrent_sessions=2, evict_oldest_on_limit=False)
    manager = make_manager(config=cfg)
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))
    asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))
    with pytest.raises(SessionLimitError):
        asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))


def test_logout_refresh_rotate():
    manager = make_manager()
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    result = asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))
    pair = asyncio_run(manager.refresh(result.token_pair.refresh_token))
    assert pair.access_jti != result.token_pair.access_jti
    with pytest.raises(TokenRevokedError):
        asyncio_run(manager.refresh(result.token_pair.refresh_token))
    jti = asyncio_run(manager.logout(pair.refresh_token))
    assert jti == pair.refresh_jti
    with pytest.raises(SessionExpiredError):
        manager.validate(pair.access_token)


def test_refresh_invalid_session():
    manager = make_manager()
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    result = asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))
    asyncio_run(manager.revoke_session(result.session.id))
    with pytest.raises(SessionExpiredError):
        asyncio_run(manager.refresh(result.token_pair.refresh_token))


def test_validate_expired_token():
    manager = make_manager()
    claims = TokenClaims(sub="u1", token_type="access", iat=time.time() - 100, exp=time.time() - 10)
    with pytest.raises(TokenExpiredError):
        manager.validate(manager.tokens.issue(claims))


def test_authenticate_headers():
    manager = make_manager()
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    result = asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))
    principal = asyncio_run(manager.authenticate(headers={"Authorization": f"Bearer {result.token_pair.access_token}"}))
    assert principal.user_id == result.user.id
    with pytest.raises(InvalidCredentialsError):
        asyncio_run(manager.authenticate(headers={}))
    with pytest.raises(InvalidCredentialsError):
        asyncio_run(manager.authenticate(headers={"Authorization": "Basic abc"}))
    with pytest.raises(InvalidTokenError):
        asyncio_run(manager.authenticate(authorization="Bearer bad.token.here"))


def test_authenticate_api_key_and_service_principal():
    manager = make_manager()
    _, raw = manager.api_keys.generate("t1", "ci", scopes=["read"])
    principal = asyncio_run(manager.authenticate(headers={"Authorization": f"ApiKey {raw}"}))
    assert principal.service is True
    assert principal.method == "apikey"
    assert principal.scopes == ["read"]
    _, raw_token = manager.service_accounts.create("t1", "deploy")
    principal2 = asyncio_run(manager.authenticate(headers={"Authorization": f"Service {raw_token}"}))
    assert principal2.method == "service_account"
    assert principal2.user_id.startswith("sa:")
    with pytest.raises(APIKeyError):
        manager.authenticate_api_key("ak_bad")
    with pytest.raises(ServiceAccountError):
        manager.authenticate_service_account("sa_bad")


def test_change_password():
    manager = make_manager()
    user = manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    with pytest.raises(InvalidCredentialsError):
        manager.change_password(user.id, "Wrong123!", "NewPass456!")
    with pytest.raises(InvalidCredentialsError):
        manager.change_password(user.id, "StrongPass123!", "weak1!")
    assert manager.change_password(user.id, "StrongPass123!", "NewPass456!") is True
    result = asyncio_run(manager.login("alice", "NewPass456!", tenant_id="t1"))
    assert result.token_pair is not None
    with pytest.raises(InvalidCredentialsError):
        asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))


def test_revoke_sessions_and_rotate_keys():
    manager = make_manager()
    user = manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    result = asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))
    assert asyncio_run(manager.revoke_all_sessions(user.id)) == 1
    with pytest.raises(SessionExpiredError):
        manager.validate(result.token_pair.access_token)
    result2 = asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))
    assert asyncio_run(manager.revoke_session(result2.session.id)) is True
    with pytest.raises(SessionExpiredError):
        manager.validate(result2.token_pair.access_token)
    kid = asyncio_run(manager.rotate_signing_keys())
    assert kid
    assert asyncio_run(manager.revoke_all_sessions("nobody")) == 0


def test_manager_metrics_and_close():
    manager = make_manager()
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))
    summary = manager.get_metrics()
    assert summary["events"]["login_success"] == 1
    manager.close()
    assert manager.config.access_token_ttl == 900


def test_manager_providers_and_policy_accessors():
    manager = make_manager()
    assert manager.providers.has("local")
    assert isinstance(manager.policy, PermissionPolicy)
    assert isinstance(manager.sessions, SessionManager)
    assert isinstance(manager.tokens, JWTManager)
    assert isinstance(manager.api_keys, APIKeyManager)
    assert isinstance(manager.service_accounts, ServiceAccountManager)
    assert manager.users is not None


def test_audit_event_swallows_errors():
    class BoomAudit:
        def record(self, **kwargs):
            raise RuntimeError("audit down")
    manager = make_manager(audit=BoomAudit())
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    result = asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))
    assert result.token_pair is not None


def test_login_suspended_after_provider():
    manager = make_manager()
    user = manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    user.status = UserStatus.SUSPENDED
    manager.users.update(user)
    with pytest.raises(AccountInactiveError):
        asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))


# ---------------------------------------------------------------- middleware

def make_middleware(manager=None, **kw):
    manager = manager or make_manager()
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    return AuthMiddleware(FakeASGIApp(), manager, config=make_config(), **kw)


def test_middleware_public_path():
    mw = make_middleware()
    messages = asyncio_run(run_asgi(mw, make_scope(path="/health")))
    assert messages[0]["status"] == 200
    mw2 = AuthMiddleware(FakeASGIApp(), make_manager(), config=make_config(require_auth=False))
    messages = asyncio_run(run_asgi(mw2, make_scope(path="/anything")))
    assert messages[0]["status"] == 200


def test_middleware_authorized():
    manager = make_manager()
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    result = asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))
    mw = AuthMiddleware(FakeASGIApp(), manager, config=make_config())
    messages = asyncio_run(run_asgi(mw, make_scope(headers={"Authorization": f"Bearer {result.token_pair.access_token}"})))
    assert messages[0]["status"] == 200
    assert mw.manager is manager


def test_middleware_unauthorized_cases():
    manager = make_manager()
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    mw = AuthMiddleware(FakeASGIApp(), manager, config=make_config())
    messages = asyncio_run(run_asgi(mw, make_scope(headers={"Authorization": "Bearer bad"})))
    assert messages[0]["status"] == 401
    messages = asyncio_run(run_asgi(mw, make_scope(headers={})))
    assert messages[0]["status"] == 401
    expired = manager.tokens.issue(
        TokenClaims(sub="u1", iat=time.time() - 10, exp=time.time() - 5)
    )
    messages = asyncio_run(run_asgi(mw, make_scope(headers={"Authorization": f"Bearer {expired}"})))
    assert messages[0]["status"] == 401
    assert b"expired" in messages[1]["body"]


def test_middleware_api_key_ok():
    manager = make_manager()
    _, raw = manager.api_keys.generate("t1", "ci")
    mw = AuthMiddleware(FakeASGIApp(), manager, config=make_config())
    messages = asyncio_run(run_asgi(mw, make_scope(headers={"Authorization": f"ApiKey {raw}"})))
    assert messages[0]["status"] == 200


def test_middleware_permission_denied():
    manager = make_manager()
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    result = asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))
    mw = AuthMiddleware(
        FakeASGIApp(),
        manager,
        config=make_config(),
        required_permissions={"/v1/admin": "write:chat"},
    )
    messages = asyncio_run(run_asgi(mw, make_scope(path="/v1/admin", headers={"Authorization": f"Bearer {result.token_pair.access_token}"})))
    assert messages[0]["status"] == 403
    assert b"permission denied" in messages[1]["body"]


def test_middleware_server_error():
    manager = make_manager()
    mw = AuthMiddleware(FakeASGIApp(), manager, config=make_config())

    async def boom(headers=None, authorization=None):
        raise RuntimeError("internal")
    manager.authenticate = boom
    messages = asyncio_run(run_asgi(mw, make_scope(headers={"Authorization": "Bearer x"})))
    assert messages[0]["status"] == 500


def test_middleware_non_http_passthrough():
    mw = make_middleware()
    messages = asyncio_run(run_asgi(mw, {"type": "websocket", "headers": []}))
    assert messages[0]["status"] == 200


def test_middleware_fastapi_http():
    manager = make_manager()
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    result = asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))
    mw = AuthMiddleware(FakeASGIApp(), manager, config=make_config())

    async def call_next(request):
        return {"ok": True}

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/chat",
            "headers": [(b"authorization", f"Bearer {result.token_pair.access_token}".encode())],
            "query_string": b"",
            "server": ("test", 80),
            "client": ("test", 1234),
        }
    )
    response = asyncio_run(mw.fastapi_http(request, call_next))
    assert response == {"ok": True}

    bad_request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/chat",
            "headers": [(b"authorization", b"Bearer bad")],
            "query_string": b"",
            "server": ("test", 80),
            "client": ("test", 1234),
        }
    )
    response = asyncio_run(mw.fastapi_http(bad_request, call_next))
    assert response.status_code == 401

    public_request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [],
            "query_string": b"",
            "server": ("test", 80),
            "client": ("test", 1234),
        }
    )
    assert asyncio_run(mw.fastapi_http(public_request, call_next)) == {"ok": True}

    mw2 = AuthMiddleware(FakeASGIApp(), manager, config=make_config(), required_permissions={"/v1/admin": "write:chat"})
    admin_request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/admin",
            "headers": [(b"authorization", f"Bearer {result.token_pair.access_token}".encode())],
            "query_string": b"",
            "server": ("test", 80),
            "client": ("test", 1234),
        }
    )
    response = asyncio_run(mw2.fastapi_http(admin_request, call_next))
    assert response.status_code == 403

    manager2 = make_manager()
    mw3 = AuthMiddleware(FakeASGIApp(), manager2, config=make_config())
    manager2.authenticate = boom_auth
    error_request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/chat",
            "headers": [(b"authorization", b"Bearer x")],
            "query_string": b"",
            "server": ("test", 80),
            "client": ("test", 1234),
        }
    )
    response = asyncio_run(mw3.fastapi_http(error_request, call_next))
    assert response.status_code == 500


async def boom_auth(headers=None, authorization=None):
    raise RuntimeError("internal")


def test_create_auth_middleware_factory():
    manager = make_manager()
    mw = create_auth_middleware(FakeASGIApp(), manager, config=make_config())
    assert isinstance(mw, AuthMiddleware)


def test_middleware_metrics():
    manager = make_manager()
    metrics = AuthMetricsTracker(make_config())
    mw = AuthMiddleware(FakeASGIApp(), manager, config=make_config(), metrics=metrics)
    asyncio_run(run_asgi(mw, make_scope(headers={"Authorization": "Bearer bad"})))
    summary = metrics.summary()
    assert summary["events"].get("auth_failed", 0) == 1


# ---------------------------------------------------------------- coverage gaps

def test_default_transport_success_and_failure(monkeypatch):
    import urllib.request
    import io
    import json as _json

    class FakeResp:
        def __init__(self, data):
            self._data = data
        def read(self):
            return self._data
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    def fake_urlopen(url, timeout):
        return FakeResp(_json.dumps({"ok": True}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    from app.auth.providers.oauth2 import default_transport
    assert default_transport("https://x") == {"ok": True}

    def failing_urlopen(url, timeout):
        raise urllib.error.URLError("down")
    monkeypatch.setattr(urllib.request, "urlopen", failing_urlopen)
    with pytest.raises(ProviderError):
        default_transport("https://x")

    def bad_json(url, timeout):
        raise ValueError("not json")
    monkeypatch.setattr(urllib.request, "urlopen", bad_json)
    with pytest.raises(ProviderError):
        default_transport("https://x")


def test_default_ldap_bind(monkeypatch):
    import sys
    import types

    class FakeConnection:
        def __init__(self, server, user, password, auto_bind):
            self.unbound = False
        def unbind(self):
            self.unbound = True

    class FakeServer:
        def __init__(self, host, port, get_info):
            pass

    fake_ldap3 = types.ModuleType("ldap3")
    fake_ldap3.Server = FakeServer
    fake_ldap3.Connection = FakeConnection
    fake_ldap3.NONE = object()
    monkeypatch.setitem(sys.modules, "ldap3", fake_ldap3)
    from app.auth.providers.ldap import default_ldap_bind
    bind = default_ldap_bind("cn={username},{base_dn}", "dc=example,dc=com")
    result = bind("alice", "pw", "t1")
    assert result["dn"] == "cn=alice,dc=example,dc=com"
    assert result["attributes"]["mail"] == "alice"
    monkeypatch.setitem(sys.modules, "ldap3", None)
    with pytest.raises(ProviderError):
        bind("alice", "pw", "t1")
    monkeypatch.delitem(sys.modules, "ldap3", raising=False)


def test_local_provider_reset_locked_status():
    cfg = make_config(password_hash_iterations=1000)
    manager = make_manager(config=cfg)
    user = manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    user.status = UserStatus.LOCKED
    user.failed_attempts = 1
    user.locked_until = 0.0
    manager.users.update(user)
    result = asyncio_run(manager.providers.get("local").authenticate({"username": "alice", "password": "StrongPass123!", "tenant_id": "t1"}))
    assert result.id == user.id
    refreshed = manager.users.get(user.id)
    assert refreshed.status == UserStatus.ACTIVE
    assert refreshed.failed_attempts == 0


def test_login_with_suspended_reconciled_user():
    cfg = make_config(password_hash_iterations=1000)
    manager = make_manager(config=cfg)
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    suspended = manager.users.get_by_username("alice", "t1")
    suspended.status = UserStatus.SUSPENDED
    manager.users.update(suspended)

    def handler(credentials):
        return ProviderUser(id=suspended.id, username="alice", tenant_id="t1")
    manager.providers.register(CustomProvider(handler=handler))
    with pytest.raises(AccountInactiveError):
        asyncio_run(manager.login_with("custom", {}, device="d"))


def test_logout_session_already_revoked():
    manager = make_manager()
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    result = asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))
    asyncio_run(manager.revoke_session(result.session.id))
    jti = asyncio_run(manager.logout(result.token_pair.refresh_token))
    assert jti == result.token_pair.refresh_jti


def test_refresh_token_without_session():
    manager = make_manager()
    pair = manager.tokens.issue_pair("u1", "t1", ["viewer"], "")
    new_pair = asyncio_run(manager.refresh(pair.refresh_token))
    assert new_pair.refresh_jti != pair.refresh_jti


def test_middleware_permission_ok_and_authenticate_permission_error():
    manager = make_manager()
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    result = asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))
    mw = AuthMiddleware(
        FakeASGIApp(),
        manager,
        config=make_config(),
        required_permissions={"/v1/read": "read:chat"},
    )
    messages = asyncio_run(run_asgi(mw, make_scope(path="/v1/read", headers={"Authorization": f"Bearer {result.token_pair.access_token}"})))
    assert messages[0]["status"] == 200

    mw2 = AuthMiddleware(FakeASGIApp(), manager, config=make_config())

    async def denied(headers=None, authorization=None):
        raise PermissionDeniedError("read:chat", "u1")
    manager.authenticate = denied
    messages = asyncio_run(run_asgi(mw2, make_scope(headers={"Authorization": "Bearer x"})))
    assert messages[0]["status"] == 403


def test_oauth2_exchange_and_userinfo_failures():
    def transport(url, payload):
        if "token" in url:
            raise RuntimeError("token endpoint down")
        raise RuntimeError("userinfo down")
    provider = OAuth2Provider(token_endpoint="https://idp/token", userinfo_endpoint="https://idp/userinfo", client_id="c", transport=transport)
    with pytest.raises(ProviderError):
        asyncio_run(provider.authenticate({"grant_type": "authorization_code", "code": "c", "redirect_uri": "http://cb"}))
    with pytest.raises(ProviderError):
        asyncio_run(provider.authenticate({"grant_type": "password", "username": "b", "password": "p"}))

    def transport2(url, payload):
        if "token" in url:
            return {"access_token": "at"}
        return "not-a-dict"
    provider2 = OAuth2Provider(token_endpoint="https://idp/token", userinfo_endpoint="https://idp/userinfo", client_id="c", transport=transport2)
    with pytest.raises(ProviderError):
        asyncio_run(provider2.authenticate({"grant_type": "client_credentials", "access_token": "at"}))

    def transport3(url, payload):
        if "token" in url:
            return {"access_token": "at"}
        return {"foo": "bar"}
    provider3 = OAuth2Provider(token_endpoint="https://idp/token", userinfo_endpoint="https://idp/userinfo", client_id="c", transport=transport3)
    with pytest.raises(ProviderError):
        asyncio_run(provider3.authenticate({"grant_type": "client_credentials", "access_token": "at"}))


def test_oidc_discovery_and_decode_edge_cases():
    provider = OIDCProvider(client_id="c")
    assert provider._discover() == {}
    with pytest.raises(InvalidTokenError):
        asyncio_run(provider.authenticate({"id_token": "a.!!!.c"}))
    body = base64.urlsafe_b64encode(b"[1,2,3]").decode().rstrip("=")
    with pytest.raises(InvalidTokenError):
        asyncio_run(provider.authenticate({"id_token": f"a.{body}.c"}))
    provider2 = OIDCProvider(client_id="c", discovery_url="https://idp/d", transport=lambda u, p: (_ for _ in ()).throw(RuntimeError("down")))
    with pytest.raises(ProviderError):
        provider2._discover()
    provider3 = OIDCProvider(client_id="c", discovery_url="https://idp/d", transport=lambda u, p: "nope")
    with pytest.raises(ProviderError):
        provider3._discover()
    issuer_only = OIDCProvider(client_id="c", issuer="https://idp", client_secret="s", discovery_url="https://idp/d", transport=lambda u, p: {"issuer": "other"})
    now = time.time()
    claims = {"iss": "https://idp", "aud": "c", "sub": "s1", "exp": now + 300}
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "kid": "k1"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(hmac.new(b"s", f"{header}.{body}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    token = f"{header}.{body}.{sig}"
    result = asyncio_run(issuer_only.authenticate({"id_token": token}))
    assert result.id == "s1"


def test_saml_invalid_expiry_parse():
    provider = SAMLProvider(entity_id="https://app")
    xml = """<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol">
      <saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">
        <saml:Conditions NotBefore="2020-01-01T00:00:00Z" NotOnOrAfter="garbage"/>
        <saml:Subject><saml:NameID>u1</saml:NameID></saml:Subject>
      </saml:Assertion>
    </samlp:Response>"""
    result = asyncio_run(provider.authenticate({"response": xml}))
    assert result.id == "u1"


def test_as_list_helper():
    from app.auth.repository import _as_list
    assert _as_list(None) == []
    assert _as_list([1, 2]) == [1, 2]
    assert _as_list("x") == ["x"]
    assert _as_list(("a", "b")) == ["a", "b"]
    assert _as_list({1}) == [1]


def test_service_account_accessors_and_rotate_missing():
    mgr = ServiceAccountManager(make_config())
    assert mgr.repository is not None
    with pytest.raises(ServiceAccountError):
        mgr.rotate("nope")


def test_jwt_accessors_and_non_dict_payload():
    jwt = JWTManager("secret", make_config())
    assert jwt.key_store is not None
    assert jwt.denylist is not None
    body = base64.urlsafe_b64encode(b"[1,2]").decode().rstrip("=")
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "kid": jwt.key_store.current[0]}).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(hmac.new(b"secret", f"{header}.{body}".encode(), hashlib.sha256).digest()).decode().rstrip("=")
    with pytest.raises(InvalidTokenError):
        jwt.parse(f"{header}.{body}.{sig}")
    wrong = make_jwt({"sub": "u"}, kid=jwt.key_store.current[0], key="not-the-secret")
    with pytest.raises(InvalidTokenError):
        jwt.parse(wrong)


def test_middleware_fastapi_permission_ok_and_expired():
    manager = make_manager()
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    result = asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))
    mw = AuthMiddleware(
        FakeASGIApp(),
        manager,
        config=make_config(),
        required_permissions={"/v1/read": "read:chat"},
    )

    async def call_next(request):
        return {"ok": True}

    req = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/read",
            "headers": [(b"authorization", f"Bearer {result.token_pair.access_token}".encode())],
            "query_string": b"",
            "server": ("test", 80),
            "client": ("test", 1),
        }
    )
    assert asyncio_run(mw.fastapi_http(req, call_next)) == {"ok": True}

    expired = manager.tokens.issue(TokenClaims(sub="u1", iat=time.time() - 10, exp=time.time() - 5))
    mw2 = AuthMiddleware(FakeASGIApp(), manager, config=make_config())
    req2 = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/chat",
            "headers": [(b"authorization", f"Bearer {expired}".encode())],
            "query_string": b"",
            "server": ("test", 80),
            "client": ("test", 1),
        }
    )
    response = asyncio_run(mw2.fastapi_http(req2, call_next))
    assert response.status_code == 401


def test_api_key_accessor_and_rotate_missing():
    mgr = APIKeyManager(make_config())
    assert mgr.repository is not None
    with pytest.raises(APIKeyError):
        mgr.rotate("nope")


def test_login_provider_suspended_reconciled():
    cfg = make_config(password_hash_iterations=1000)
    manager = make_manager(config=cfg)
    suspended = manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    suspended.status = UserStatus.SUSPENDED
    manager.users.update(suspended)

    def handler(credentials):
        return ProviderUser(id=suspended.id, username="alice", tenant_id="t1")
    manager.providers.register(CustomProvider(handler=handler))
    with pytest.raises(AccountInactiveError):
        asyncio_run(manager.login("alice", "pw", tenant_id="t1", provider="custom"))


def test_logout_session_deleted_from_repo():
    manager = make_manager()
    manager.register_user("alice", "StrongPass123!", tenant_id="t1")
    result = asyncio_run(manager.login("alice", "StrongPass123!", tenant_id="t1"))
    manager.sessions.repository.delete(result.session.id)
    jti = asyncio_run(manager.logout(result.token_pair.refresh_token))
    assert jti == result.token_pair.refresh_jti


def test_oauth2_provider_error_passthrough():
    def transport(url, payload):
        raise ProviderError("down")
    provider = OAuth2Provider(token_endpoint="https://idp/token", client_id="c", transport=transport)
    with pytest.raises(ProviderError):
        asyncio_run(provider.authenticate({"grant_type": "authorization_code", "code": "c", "redirect_uri": "http://cb"}))


def test_oauth2_userinfo_transport_error():
    def transport(url, payload):
        if "token" in url:
            return {"access_token": "at"}
        raise RuntimeError("userinfo down")
    provider = OAuth2Provider(token_endpoint="https://idp/token", userinfo_endpoint="https://idp/userinfo", client_id="c", transport=transport)
    with pytest.raises(ProviderError):
        asyncio_run(provider.authenticate({"grant_type": "client_credentials", "access_token": "at"}))


def test_oidc_decode_non_dict_and_alg_and_key_provider():
    def enc(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
    now = time.time()
    provider = OIDCProvider(client_id="c", client_secret="s", issuer="https://idp")
    h = enc({"alg": "HS256"})
    b = enc([1, 2])
    with pytest.raises(InvalidTokenError):
        asyncio_run(provider.authenticate({"id_token": f"{h}.{b}.sig"}))
    b2 = enc({"iss": "https://idp", "aud": "c", "sub": "s1", "exp": now + 300})
    h2 = enc({"alg": "none"})
    with pytest.raises(InvalidTokenError):
        asyncio_run(provider.authenticate({"id_token": f"{h2}.{b2}.sig"}))
    provider2 = OIDCProvider(client_id="c", client_secret="s", issuer="https://idp", key_provider=lambda kid: None)
    h3 = enc({"alg": "RS256", "kid": "k1"})
    with pytest.raises(InvalidTokenError):
        asyncio_run(provider2.authenticate({"id_token": f"{h3}.{b2}.sig"}))


def test_oidc_discovery_provider_error_passthrough():
    provider = OIDCProvider(client_id="c", discovery_url="https://idp/d", transport=lambda u, p: (_ for _ in ()).throw(ProviderError("nope")))
    with pytest.raises(ProviderError):
        provider._discover()


def test_auth_logger_fallback(monkeypatch):
    import app.auth.logging as auth_logging

    def boom(*args, **kwargs):
        raise RuntimeError("json failed")
    monkeypatch.setattr(auth_logging.json, "dumps", boom)
    logger = AuthLogger()
    logger.log_event("login", tenant_id="t1")
    logger.log_event("login")
