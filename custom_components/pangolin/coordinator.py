"""Data coordinator for Pangolin."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

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
    DOMAIN,
    LEVEL_OFF,
    OPT_CLIENTS,
    OPT_PRIVATE,
    OPT_PUBLIC,
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
