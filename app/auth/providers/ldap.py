from __future__ import annotations

from typing import Any, Callable

from ..exceptions import InvalidCredentialsError, ProviderError
from ..models import ProviderUser
from .base import AuthProvider

BindTransport = Callable[[str, str, str], dict[str, Any] | None]


def default_ldap_bind(bind_dn_template: str, base_dn: str) -> BindTransport:
    def bind(username: str, password: str, tenant_id: str = "") -> dict[str, Any] | None:
        try:
            import ldap3
        except ImportError:
            raise ProviderError("LDAP requires the 'ldap3' package") from None
        dn = bind_dn_template.format(username=username, tenant_id=tenant_id, base_dn=base_dn)
        server = ldap3.Server(host="ldap://localhost", port=389, get_info=ldap3.NONE)
        connection = ldap3.Connection(server, user=dn, password=password, auto_bind=True)
        connection.unbind()
        return {
            "dn": dn,
            "username": username,
            "attributes": {"mail": username},
        }

    return bind


class LDAPProvider(AuthProvider):
    name = "ldap"

    def __init__(
        self,
        bind_dn_template: str = "cn={username},{base_dn}",
        base_dn: str = "dc=example,dc=com",
        bind: BindTransport | None = None,
        username_attr: str = "cn",
        role_attr: str = "memberOf",
        **options: Any,
    ):
        super().__init__(**options)
        self._bind_dn_template = bind_dn_template
        self._base_dn = base_dn
        self._bind = bind or default_ldap_bind(bind_dn_template, base_dn)
        self._username_attr = username_attr
        self._role_attr = role_attr

    async def authenticate(self, credentials: dict[str, Any]) -> ProviderUser:
        username = str(credentials.get("username", ""))
        password = str(credentials.get("password", ""))
        tenant_id = str(credentials.get("tenant_id", ""))
        if not username or not password:
            raise InvalidCredentialsError("Missing credentials")
        try:
            entry = self._bind(username, password, tenant_id)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"LDAP bind failed: {exc}") from exc
        if entry is None:
            raise InvalidCredentialsError("LDAP authentication failed")
        attributes = entry.get("attributes") or {}
        roles = [str(r) for r in attributes.get(self._role_attr, [])]
        display_name = str(attributes.get("displayName") or username)
        return ProviderUser(
            id=str(entry.get("dn") or f"ldap:{username}"),
            username=str(attributes.get(self._username_attr) or username),
            email=str(attributes.get("mail", "")),
            display_name=display_name,
            roles=roles,
            tenant_id=tenant_id,
            attributes=attributes,
        )
