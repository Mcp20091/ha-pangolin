"""Data coordinator for Pangolin."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PangolinAuthError, PangolinClient, PangolinError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type PangolinConfigEntry = ConfigEntry[PangolinCoordinator]


@dataclass
class PangolinData:
    """Snapshot of sites and resources keyed by ID."""

    sites: dict[int, dict[str, Any]] = field(default_factory=dict)
    resources: dict[int, dict[str, Any]] = field(default_factory=dict)


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

    async def _async_update_data(self) -> PangolinData:
        try:
            sites = await self.client.list_sites()
            resources = await self.client.list_resources()
        except PangolinAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PangolinError as err:
            raise UpdateFailed(str(err)) from err
        return PangolinData(
            sites={s["siteId"]: s for s in sites},
            resources={r["resourceId"]: r for r in resources},
        )
