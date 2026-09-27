"""Minimal async client for the Pangolin Integration API."""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import OPT_PRIVATE, OPT_PUBLIC, PAGE_SIZE


class PangolinError(Exception):
    """Generic Pangolin API error."""


class PangolinAuthError(PangolinError):
    """Raised when the API key is rejected (401) or not allowed (403)."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


class PangolinConnectionError(PangolinError):
    """Raised when the API cannot be reached."""


class PangolinNotFoundError(PangolinError):
    """Raised when an endpoint or object does not exist (404)."""


def key_id_of(api_key: str) -> str | None:
    """Pangolin keys look like "<apiKeyId>.<secret>"; return the ID part."""
    key_id, sep, secret = api_key.strip().partition(".")
    return key_id if sep and key_id and secret else None


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
        org_id: str = "",
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
                        f"API key rejected ({resp.status}) for {path}", resp.status
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

    async def list_orgs(self) -> list[dict[str, Any]]:
        """Return every organization. Only root API keys may call this."""
        data = await self._request("GET", "/orgs")
        return (data or {}).get("orgs") or []

    async def is_root_key(self) -> bool:
        """Whether this is a root key (org-scoped keys may not list orgs)."""
        try:
            await self._request("GET", "/orgs")
        except PangolinAuthError as err:
            if err.status == 403:
                return False
            raise
        except PangolinNotFoundError:
            return False
        return True

    # Key management below needs a root API key.

    async def list_key_actions(self, key_id: str) -> list[str]:
        """Return the permission (action) IDs granted to an org API key."""
        data = await self._request(
            "GET", f"/org/{self._org_id}/api-key/{key_id}/actions"
        )
        return [a["actionId"] for a in (data or {}).get("actions") or []]

    async def set_key_actions(self, key_id: str, actions: list[str]) -> None:
        """Replace an org API key's permissions with exactly these actions."""
        await self._request(
            "POST",
            f"/org/{self._org_id}/api-key/{key_id}/actions",
            json={"actionIds": actions},
        )

    async def create_org_key(self, name: str) -> str:
        """Create an org API key with no permissions; return the full key."""
        data = await self._request(
            "PUT", f"/org/{self._org_id}/api-key", json={"name": name}
        )
        return f"{data['apiKeyId']}.{data['apiKey']}"

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
