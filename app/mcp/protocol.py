from __future__ import annotations

import json
from typing import Any

from app.mcp.exceptions import MCPProtocolError, MCPRPCError


class JSONRPCRequest:
    def __init__(self, method: str, params: dict[str, Any] | None = None, request_id: int | None = None):
        self.jsonrpc = "2.0"
        self.method = method
        self.params = params or {}
        self.id = request_id if request_id is not None else 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "jsonrpc": self.jsonrpc,
            "id": self.id,
            "method": self.method,
            "params": self.params,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class JSONRPCResponse:
    def __init__(self, request_id: int | None = None, result: Any = None,
                 error: dict[str, Any] | None = None):
        self.jsonrpc = "2.0"
        self.id = request_id
        self.result = result
        self.error = error

    @property
    def ok(self) -> bool:
        return self.error is None

    def raise_for_error(self) -> Any:
        if self.error is not None:
            raise MCPRPCError(
                code=int(self.error.get("code", -32000)),
                message=str(self.error.get("message", "RPC error")),
                data=self.error.get("data"),
            )
        return self.result

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            payload["error"] = self.error
        else:
            payload["result"] = self.result
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JSONRPCResponse:
        return cls(
            request_id=data.get("id"),
            result=data.get("result"),
            error=data.get("error"),
        )

    @classmethod
    def from_json(cls, raw: str) -> JSONRPCResponse:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as e:
            raise MCPProtocolError(f"Invalid JSON-RPC payload: {e}") from e
        if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
            raise MCPProtocolError("Response is not a JSON-RPC 2.0 message")
        return cls.from_dict(data)


class JSONRPCNotification:
    def __init__(self, method: str, params: dict[str, Any] | None = None):
        self.jsonrpc = "2.0"
        self.method = method
        self.params = params or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "jsonrpc": self.jsonrpc,
            "method": self.method,
            "params": self.params,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


def build_request(method: str, params: dict[str, Any] | None = None, request_id: int = 1) -> JSONRPCRequest:
    return JSONRPCRequest(method, params, request_id)


def parse_message(raw: str | bytes | dict[str, Any]) -> JSONRPCResponse:
    if isinstance(raw, (str, bytes)):
        return JSONRPCResponse.from_json(raw.decode() if isinstance(raw, bytes) else raw)
    if isinstance(raw, dict):
        return JSONRPCResponse.from_dict(raw)
    raise MCPProtocolError(f"Unsupported message type: {type(raw).__name__}")


class IDGenerator:
    def __init__(self, start: int = 1):
        self._next = start

    def next(self) -> int:
        current = self._next
        self._next += 1
        return current
