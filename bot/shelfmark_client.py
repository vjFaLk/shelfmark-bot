"""Async HTTP client for the Shelfmark API."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ShelfmarkAPIError(Exception):
    """Raised on non-auth API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ShelfmarkClient:
    """Async wrapper around the Shelfmark REST API."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        """Make an API request to Shelfmark."""
        resp = await self._client.request(
            method, path, params=params, json=json_body
        )

        if resp.status_code >= 400:
            try:
                error_body = resp.json()
                msg = error_body.get("error", resp.text)
            except Exception:
                msg = resp.text
            raise ShelfmarkAPIError(msg, status_code=resp.status_code)

        # Some endpoints return 204 No Content
        if resp.status_code == 204:
            return None

        return resp.json()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    async def get_config(self) -> dict[str, Any]:
        return await self._request("GET", "/api/config")

    # ------------------------------------------------------------------
    # Metadata search (Universal mode)
    # ------------------------------------------------------------------

    async def search_books(
        self,
        query: str,
        *,
        content_type: str = "ebook",
        limit: int = 10,
        page: int = 1,
        sort: str | None = None,
    ) -> dict[str, Any]:
        """Search for books via metadata providers.

        Returns dict with keys: books, provider, query, page, total_found, has_more.
        """
        params: dict[str, Any] = {
            "query": query,
            "content_type": content_type,
            "limit": limit,
            "page": page,
        }
        if sort:
            params["sort"] = sort
        return await self._request("GET", "/api/metadata/search", params=params)

    async def get_book(self, provider: str, book_id: str) -> dict[str, Any]:
        """Get full metadata for a single book."""
        return await self._request(
            "GET", f"/api/metadata/book/{provider}/{book_id}"
        )

    async def get_metadata_providers(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/api/metadata/providers")

    # ------------------------------------------------------------------
    # Releases
    # ------------------------------------------------------------------

    async def get_release_sources(self) -> list[dict[str, Any]]:
        return await self._request("GET", "/api/release-sources")

    async def get_releases(
        self,
        provider: str,
        book_id: str,
        *,
        title: str | None = None,
        author: str | None = None,
        content_type: str = "ebook",
        source: str | None = None,
    ) -> dict[str, Any]:
        """Fetch available releases for a book.

        Returns dict with keys: releases, book, sources_searched, errors,
        column_config, search_info.
        """
        params: dict[str, Any] = {
            "provider": provider,
            "book_id": book_id,
            "content_type": content_type,
        }
        if title:
            params["title"] = title
        if author:
            params["author"] = author
        if source:
            params["source"] = source
        return await self._request("GET", "/api/releases", params=params)

    # ------------------------------------------------------------------
    # Downloads
    # ------------------------------------------------------------------

    async def download_release(
        self,
        *,
        source: str,
        source_id: str,
        title: str,
        fmt: str | None = None,
        size: str | None = None,
        extra: dict[str, Any] | None = None,
        download_url: str | None = None,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        """Queue a release for download.

        Returns dict with ``status`` and ``priority``.
        """
        body: dict[str, Any] = {
            "source": source,
            "source_id": source_id,
            "title": title,
        }
        if fmt:
            body["format"] = fmt
        if size:
            body["size"] = size
        if extra:
            body["extra"] = extra
        if download_url:
            body["download_url"] = download_url
        if content_type:
            body["content_type"] = content_type
        return await self._request(
            "POST", "/api/releases/download", json_body=body
        )

    # ------------------------------------------------------------------
    # Status / Queue
    # ------------------------------------------------------------------

    async def get_status(self) -> dict[str, Any]:
        """Get current download queue / status."""
        return await self._request("GET", "/api/status")

    async def download_file(self, book_id: str) -> tuple[bytes, str]:
        """Download a completed book file from Shelfmark.

        Returns (file_bytes, filename).
        Raises ShelfmarkAPIError on failure.
        """
        resp = await self._client.get(
            "/api/localdownload",
            params={"id": book_id},
            timeout=httpx.Timeout(120.0, connect=10.0),
        )
        if resp.status_code >= 400:
            raise ShelfmarkAPIError(
                f"File download failed (HTTP {resp.status_code})",
                status_code=resp.status_code,
            )

        # Extract filename from Content-Disposition header
        cd = resp.headers.get("content-disposition", "")
        filename = f"{book_id}.epub"  # fallback
        if "filename=" in cd:
            import re
            match = re.search(r'filename[*]?=["\']?([^"\';]+)', cd)
            if match:
                filename = match.group(1).strip()

        return resp.content, filename
