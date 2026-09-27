"""Site restart buttons for Pangolin."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import PangolinError, PangolinNotFoundError
from .const import OPT_CLIENT_DELETE, OPT_RESET_BANDWIDTH, OPT_RESTART
from .coordinator import PangolinConfigEntry, PangolinCoordinator
from .entity import (
    PangolinClientEntity,
    PangolinOrgEntity,
    PangolinSiteEntity,
    add_entities_dynamically,
    run_action,
)

# Only Newt sites have a connector that can be told to restart.
NON_RESTARTABLE_TYPES = {"wireguard", "local"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PangolinConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    options = entry.runtime_data.options
    if options[OPT_RESET_BANDWIDTH]:
        async_add_entities([PangolinResetBandwidth(entry.runtime_data)])
    add_entities_dynamically(
        entry,
        async_add_entities,
        site_factory=(
            (
                lambda c, sid: (
                    []
                    if c.data.sites[sid].get("type") in NON_RESTARTABLE_TYPES
                    else [PangolinSiteRestart(c, sid)]
                )
            )
            if options[OPT_RESTART]
            else None
        ),
        client_factory=(
            (lambda c, cid: [PangolinClientDelete(c, cid)])
            if options[OPT_CLIENT_DELETE]
            else None
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


class PangolinResetBandwidth(PangolinOrgEntity, ButtonEntity):
    """Zeroes every site's data in/out counters."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "reset_bandwidth"

    def __init__(self, coordinator: PangolinCoordinator) -> None:
        super().__init__(coordinator, "reset_bandwidth")

    async def async_press(self) -> None:
        await run_action(
            self.coordinator.client.reset_bandwidth(),
            "Could not reset bandwidth",
            "Reset Organization Bandwidth",
        )
        await self.coordinator.async_request_refresh()


class PangolinClientDelete(PangolinClientEntity, ButtonEntity):
    """Permanently deletes the client from Pangolin, then from Home Assistant."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "client_delete"

    def __init__(self, coordinator: PangolinCoordinator, client_id: int) -> None:
        super().__init__(coordinator, client_id, "delete")

    async def async_press(self) -> None:
        await run_action(
            self.coordinator.client.delete_client(self.client_id),
            "Could not delete client",
            "Delete Client",
        )
        # The client is gone for good, so drop its device instead of leaving
        # it behind as unavailable.
        if self.device_entry is not None:
            dr.async_get(self.hass).async_remove_device(self.device_entry.id)
        await self.coordinator.async_request_refresh()
