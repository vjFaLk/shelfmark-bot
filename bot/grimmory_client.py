"""Async HTTP client for the Grimmory API (login, newest books, Quick Send)."""

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class GrimmoryAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class GrimmoryClient:
    """Minimal wrapper: username/password login (Grimmory has no API keys) + 3 calls."""

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._token = ""
        self._token_exp = 0.0  # epoch seconds
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _headers(self) -> dict[str, str]:
        # ponytail: re-login when the 2h access token nears expiry; skipped refresh-token flow
        if not self._token or time.time() > self._token_exp - 60:
            resp = await self._client.post(
                "/api/v1/auth/login",
                json={"username": self._username, "password": self._password},
            )
            if resp.status_code >= 400:
                raise GrimmoryAPIError(
                    f"Grimmory login failed (HTTP {resp.status_code})", resp.status_code
                )
            body = resp.json()
            self._token = body["accessToken"]
            self._token_exp = (body.get("expires") or 0) / 1000 or time.time() + 3600
        return {"Authorization": f"Bearer {self._token}"}

    async def _request(
        self, method: str, path: str, *, params: dict[str, Any] | None = None
    ) -> Any:
        resp = await self._client.request(
            method, path, params=params, headers=await self._headers()
        )
        if resp.status_code >= 400:
            try:
                msg = resp.json().get("message") or resp.text
            except Exception:
                msg = resp.text
            raise GrimmoryAPIError(msg or f"HTTP {resp.status_code}", resp.status_code)
        return None if resp.status_code == 204 else resp.json()

    async def newest_books(self, limit: int = 10) -> list[dict[str, Any]]:
        """Newest books first. Filtering still uses id, so no clock-skew issues."""
        result = await self._request(
            "GET", "/api/v1/books/page", params={"sort": "-addedOn", "size": limit}
        )
        return result.get("content") or []

    async def latest_book_id(self) -> int:
        books = await self.newest_books(limit=1)
        return int(books[0]["id"]) if books else 0

    async def books_after(self, watermark: int, limit: int = 10) -> list[dict[str, Any]]:
        return [b for b in await self.newest_books(limit) if int(b.get("id", 0)) > watermark]

    async def quick_send(self, book_id: int) -> None:
        """Trigger Email Book → Quick Send (default provider + default recipient)."""
        await self._request("POST", f"/api/v1/email/book/{book_id}")
