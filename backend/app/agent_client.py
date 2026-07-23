from __future__ import annotations

import httpx


class AgentClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"x-ksylian-token": self.token}

    def get(self, path: str, params: dict[str, str] | None = None) -> httpx.Response:
        self.require_configured()
        return httpx.get(f"{self.base_url}{path}", headers=self.headers(), params=params, timeout=10)

    def post(self, path: str, json: dict | None = None) -> httpx.Response:
        self.require_configured()
        return httpx.post(f"{self.base_url}{path}", headers=self.headers(), json=json, timeout=240)

    def put(self, path: str, json: dict | None = None) -> httpx.Response:
        self.require_configured()
        return httpx.put(f"{self.base_url}{path}", headers=self.headers(), json=json, timeout=30)

    def delete(self, path: str) -> httpx.Response:
        self.require_configured()
        return httpx.delete(f"{self.base_url}{path}", headers=self.headers(), timeout=90)

    def require_configured(self) -> None:
        if not self.configured:
            raise RuntimeError("Agent is not configured")
