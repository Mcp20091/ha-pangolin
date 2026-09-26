"""Site restart buttons for Pangolin."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import PangolinError, PangolinNotFoundError
from .coordinator import PangolinConfigEntry, PangolinCoordinator
from .entity import PangolinSiteEntity, add_entities_dynamically

# Only Newt sites have a connector that can be told to restart.
NON_RESTARTABLE_TYPES = {"wireguard", "local"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PangolinConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    add_entities_dynamically(
        entry,
        async_add_entities,
        site_factory=lambda c, sid: (
            []
            if c.data.sites[sid].get("type") in NON_RESTARTABLE_TYPES
            else [PangolinSiteRestart(c, sid)]
        ),
    )


class PangolinSiteRestart(PangolinSiteEntity, ButtonEntity):
    """Restarts the site's Newt tunnel."""

    _attr_device_class = ButtonDeviceClass.RESTART

    def __init__(self, coordinator: PangolinCoordinator, site_id: int) -> None:
        super().__init__(coordinator, site_id, "restart")

    async def async_press(self) -> None:
        try:
            await self.coordinator.client.restart_site(self.site_id)
        except PangolinNotFoundError as err:
            raise HomeAssistantError(
                "Pangolin did not accept the restart. Either the site has no Newt "
                "connector or this Pangolin version does not expose site restart "
                "through the Integration API."
            ) from err
        except PangolinError as err:
            raise HomeAssistantError(f"Could not restart site: {err}") from err
        await self.coordinator.async_request_refresh()
