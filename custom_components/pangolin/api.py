"""Minimal async client for the Pangolin Integration API."""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import OPT_PRIVATE, OPT_PUBLIC, PAGE_SIZE


class PangolinError(Exception):
    """Generic Pangolin API error."""


class PangolinAuthError(PangolinError):
    """Raised when the API key is rejected."""


class PangolinConnectionError(PangolinError):
    """Raised when the API cannot be reached."""


class PangolinNotFoundError(PangolinError):
    """Raised when an endpoint or object does not exist (404)."""


def normalize_url(url: str) -> str:
    """Return the Integration API base URL ending in /v1."""
    url = url.strip().rstrip("/")
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


class PangolinClient:
    """Talks to the Pangolin Integration API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        api_key: str,
        org_id: str,
        verify_ssl: bool = True,
    ) -> None:
        self._session = session
        self._base_url = normalize_url(base_url)
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._org_id = org_id
        self._ssl = None if verify_ssl else False

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        try:
            async with self._session.request(
                method,
                f"{self._base_url}{path}",
                headers=self._headers,
                params=params,
                json=json,
                ssl=self._ssl,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status in (401, 403):
                    raise PangolinAuthError(
                        f"API key rejected ({resp.status}) for {path}"
                    )
                if resp.status == 404:
                    raise PangolinNotFoundError(f"{path} not found (404)")
                try:
                    body = await resp.json(content_type=None)
                except ValueError as err:
                    raise PangolinError(
                        f"Non-JSON response ({resp.status}) from {path}"
                    ) from err
                if (
                    resp.status >= 400
                    or not isinstance(body, dict)
                    or body.get("error")
                ):
                    msg = body.get("message") if isinstance(body, dict) else None
                    raise PangolinError(f"{path} failed ({resp.status}): {msg}")
                return body.get("data")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise PangolinConnectionError(str(err)) from err

    async def _get_all(self, path: str, key: str) -> list[dict[str, Any]]:
        """Walk every page of a paginated list endpoint."""
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            data = await self._request(
                "GET", path, params={"page": page, "pageSize": PAGE_SIZE}
            )
            batch = (data or {}).get(key) or []
            items.extend(batch)
            total = ((data or {}).get("pagination") or {}).get("total", 0)
            if not batch or len(items) >= total:
                return items
            page += 1

    async def get_org(self) -> dict[str, Any]:
        """Return the configured organization (used to validate setup)."""
        return await self._request("GET", f"/org/{self._org_id}")

    async def probe_access(self) -> dict[str, bool]:
        """Report which optional resource lists this key can read.

        Org API keys cannot read their own permission list, so this asks for
        one item from each endpoint instead. Nothing is changed on the server.
        """
        paths = {
            OPT_PUBLIC: f"/org/{self._org_id}/resources",
            OPT_PRIVATE: f"/org/{self._org_id}/private-resources",
        }
        access: dict[str, bool] = {}
        for option, path in paths.items():
            try:
                await self._request("GET", path, params={"page": 1, "pageSize": 1})
            except (PangolinAuthError, PangolinNotFoundError):
                access[option] = False
            else:
                access[option] = True
        return access

    async def list_sites(self) -> list[dict[str, Any]]:
        """Return all sites in the organization."""
        return await self._get_all(f"/org/{self._org_id}/sites", "sites")

    async def list_resources(self) -> list[dict[str, Any]]:
        """Return all public resources in the organization."""
        return await self._get_all(f"/org/{self._org_id}/resources", "resources")

    async def list_private_resources(self) -> list[dict[str, Any]]:
        """Return all private (site) resources in the organization."""
        return await self._get_all(
            f"/org/{self._org_id}/private-resources", "siteResources"
        )

    async def set_private_resource_enabled(
        self, site_resource_id: int, enabled: bool
    ) -> None:
        """Enable or disable a private resource."""
        await self._request(
            "POST", f"/private-resource/{site_resource_id}", json={"enabled": enabled}
        )

    async def restart_site(self, site_id: int) -> None:
        """Ask a site's Newt connector to restart its tunnel."""
        await self._request("POST", f"/site/{site_id}/restart")

    async def set_resource_enabled(self, resource_id: int, enabled: bool) -> None:
        """Enable or disable a resource."""
        await self._request(
            "POST", f"/resource/{resource_id}", json={"enabled": enabled}
        )
