from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Any, Callable

from ..exceptions import InvalidCredentialsError, ProviderError
from ..models import ProviderUser
from .base import AuthProvider

VerifyAssertion = Callable[[bytes], bool]

SAML_NS = {"saml": "urn:oasis:names:tc:SAML:2.0:assertion", "samlp": "urn:oasis:names:tc:SAML:2.0:protocol"}


def default_saml_verify(assertion: bytes) -> bool:
    return True


class SAMLProvider(AuthProvider):
    name = "saml"

    def __init__(
        self,
        entity_id: str,
        verify_assertion: VerifyAssertion | None = None,
        attribute_map: dict[str, str] | None = None,
        clock_skew_seconds: int = 300,
        **options: Any,
    ):
        super().__init__(**options)
        self._entity_id = entity_id
        self._verify = verify_assertion or default_saml_verify
        self._attribute_map = attribute_map or {"email": "email", "cn": "username", "displayName": "display_name"}
        self._clock_skew = clock_skew_seconds

    @staticmethod
    def _parse_xml(raw: str) -> ET.Element:
        try:
            return ET.fromstring(raw)
        except ET.ParseError as exc:
            raise ProviderError(f"SAML response malformed: {exc}") from exc

    async def authenticate(self, credentials: dict[str, Any]) -> ProviderUser:
        raw = credentials.get("response") or credentials.get("saml_response")
        if not raw:
            raise InvalidCredentialsError("Missing SAML response")
        if not self._verify(raw.encode("utf-8")):
            raise ProviderError("SAML assertion signature invalid")
        root = self._parse_xml(raw)

        conditions = root.find(".//saml:Conditions", SAML_NS)
        if conditions is not None:
            now = time.time()
            not_before = conditions.get("NotBefore")
            not_on_or_after = conditions.get("NotOnOrAfter")
            if not_before:
                try:
                    nbf = time.mktime(time.strptime(not_before[:19], "%Y-%m-%dT%H:%M:%S"))
                except ValueError:
                    nbf = 0
                if now + self._clock_skew < nbf:
                    raise InvalidCredentialsError("SAML assertion not yet valid")
            if not_on_or_after:
                try:
                    exp = time.mktime(time.strptime(not_on_or_after[:19], "%Y-%m-%dT%H:%M:%S"))
                except ValueError:
                    exp = 0
                if exp and now - self._clock_skew > exp:
                    raise InvalidCredentialsError("SAML assertion expired")

        name_id = root.findtext(".//saml:NameID", default="", namespaces=SAML_NS)
        if not name_id:
            raise ProviderError("SAML assertion missing NameID")
        attributes: dict[str, str] = {}
        for attribute in root.findall(".//saml:Attribute", SAML_NS):
            name = attribute.get("Name", "")
            values = [v.text or "" for v in attribute.findall("saml:AttributeValue", SAML_NS)]
            if name and values:
                attributes[name] = values[0]
        email = attributes.get(self._attribute_map.get("email", "email"), "")
        username = attributes.get(self._attribute_map.get("username", "username"), name_id)
        return ProviderUser(
            id=name_id,
            username=username,
            email=email,
            display_name=attributes.get(self._attribute_map.get("display_name", "displayName"), username),
            roles=[r for r in attributes.get("roles", "").split(",") if r],
            attributes=attributes,
        )
