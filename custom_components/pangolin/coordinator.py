"""Data coordinator for Pangolin."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    PangolinAuthError,
    PangolinClient,
    PangolinError,
    PangolinNotFoundError,
)
from .const import (
    DEFAULT_FEATURES,
    CONF_FEATURES,
    DEFAULT_SCAN_INTERVAL,
    DETAIL_REFRESH_INTERVAL,
    DOMAIN,
    LEVEL_OFF,
    OPT_CLIENTS,
    OPT_PRIVATE,
    OPT_PUBLIC,
    OPT_PUBLIC_BLOCK,
    OPT_PUBLIC_MAINTENANCE,
    resolve_features,
)

_LOGGER = logging.getLogger(__name__)

type PangolinConfigEntry = ConfigEntry[PangolinCoordinator]


def get_options(entry: ConfigEntry) -> dict[str, Any]:
    """Resolved features; entries from before feature selection get the defaults."""
    return resolve_features(entry.options.get(CONF_FEATURES, DEFAULT_FEATURES))


@dataclass
class PangolinData:
    """Snapshot of sites and resources keyed by ID."""

    sites: dict[int, dict[str, Any]] = field(default_factory=dict)
    resources: dict[int, dict[str, Any]] = field(default_factory=dict)
    private_resources: dict[int, dict[str, Any]] = field(default_factory=dict)
    clients: dict[int, dict[str, Any]] = field(default_factory=dict)
    # Full settings of public resources (GET /resource/{id}), only fetched
    # when a switch needs them.
    resource_details: dict[int, dict[str, Any]] = field(default_factory=dict)


class PangolinCoordinator(DataUpdateCoordinator[PangolinData]):
    """Polls Pangolin for site and resource state."""

    config_entry: PangolinConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: PangolinConfigEntry, client: PangolinClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.client = client
        self.options = get_options(entry)
        self._private_supported = self.options[OPT_PRIVATE] != LEVEL_OFF
        self._clients_supported = self.options[OPT_CLIENTS] != LEVEL_OFF
        self._details_supported = (
            self.options[OPT_PUBLIC_BLOCK] or self.options[OPT_PUBLIC_MAINTENANCE]
        )
        self._resource_details: dict[int, dict[str, Any]] = {}
        self._details_fetched_at: datetime | None = None
        # False only when Pangolin itself doesn't answer, as opposed to the
        # key being rejected.
        self.api_reachable = True

    async def _async_update_data(self) -> PangolinData:
        try:
            sites = await self.client.list_sites()
            resources = (
                await self.client.list_resources()
                if self.options[OPT_PUBLIC] != LEVEL_OFF
                else []
            )
            private_resources = await self._fetch_private_resources()
            clients = await self._fetch_clients()
            await self._fetch_resource_details([r["resourceId"] for r in resources])
        except PangolinAuthError as err:
            self.api_reachable = True
            raise ConfigEntryAuthFailed(str(err)) from err
        except PangolinError as err:
            self.api_reachable = await self.client.ping()
            raise UpdateFailed(str(err)) from err
        self.api_reachable = True
        return PangolinData(
            sites={s["siteId"]: s for s in sites},
            resources={r["resourceId"]: r for r in resources},
            private_resources=private_resources,
            clients=clients,
            resource_details=self._resource_details,
        )

    async def _fetch_private_resources(self) -> dict[int, dict[str, Any]]:
        """Private resources are optional: older servers or keys without the
        List Site Resources permission just get none."""
        if not self._private_supported:
            return {}
        try:
            items = await self.client.list_private_resources()
        except (PangolinAuthError, PangolinNotFoundError) as err:
            _LOGGER.warning("Private resources unavailable, skipping them: %s", err)
            self._private_supported = False
            return {}
        return {r["siteResourceId"]: r for r in items}

    async def _fetch_clients(self) -> dict[int, dict[str, Any]]:
        """Clients are optional too: keys without List Clients get none."""
        if not self._clients_supported:
            return {}
        try:
            items = await self.client.list_clients()
        except (PangolinAuthError, PangolinNotFoundError) as err:
            _LOGGER.warning("Clients unavailable, skipping them: %s", err)
            self._clients_supported = False
            return {}
        return {c["clientId"]: c for c in items}

    async def _fetch_resource_details(self, resource_ids: list[int]) -> None:
        """Refresh full resource settings every few minutes, or for new ones."""
        if not self._details_supported:
            return
        now = dt_util.utcnow()
        due = (
            self._details_fetched_at is None
            or now - self._details_fetched_at >= DETAIL_REFRESH_INTERVAL
        )
        wanted = resource_ids if due else [
            rid for rid in resource_ids if rid not in self._resource_details
        ]
        for resource_id in wanted:
            try:
                self._resource_details[resource_id] = await self.client.get_resource(
                    resource_id
                )
            except (PangolinAuthError, PangolinNotFoundError) as err:
                _LOGGER.warning(
                    "Resource details unavailable (needs Get Resource), so block "
                    "access and maintenance switches are skipped: %s",
                    err,
                )
                self._details_supported = False
                self._resource_details.clear()
                return
        for gone in set(self._resource_details) - set(resource_ids):
            del self._resource_details[gone]
        if due:
            self._details_fetched_at = now

    async def async_refresh_resource_detail(self, resource_id: int) -> dict[str, Any]:
        """Re-read one resource's settings right after changing them."""
        detail = await self.client.get_resource(resource_id)
        self._resource_details[resource_id] = detail
        self.async_update_listeners()
        return detail
