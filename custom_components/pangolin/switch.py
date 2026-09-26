"""Resource enable/disable switches for Pangolin."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import PangolinError
from .coordinator import PangolinConfigEntry, PangolinCoordinator
from .entity import PangolinResourceEntity, add_entities_dynamically


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PangolinConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    add_entities_dynamically(
        entry,
        async_add_entities,
        resource_factory=lambda c, rid: [PangolinResourceSwitch(c, rid)],
    )


class PangolinResourceSwitch(PangolinResourceEntity, SwitchEntity):
    """Turns a Pangolin resource on or off."""

    _attr_translation_key = "resource_enabled"

    def __init__(self, coordinator: PangolinCoordinator, resource_id: int) -> None:
        super().__init__(coordinator, resource_id, "enabled")

    @property
    def is_on(self) -> bool | None:
        value = self.resource.get("enabled")
        return None if value is None else bool(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        res = self.resource
        return {
            "resource_id": self.resource_id,
            "nice_id": res.get("niceId"),
            "full_domain": res.get("fullDomain"),
            "sso": res.get("sso"),
        }

    async def _set(self, enabled: bool) -> None:
        try:
            await self.coordinator.client.set_resource_enabled(self.resource_id, enabled)
        except PangolinError as err:
            raise HomeAssistantError(
                f"Could not {'enable' if enabled else 'disable'} resource: {err}"
            ) from err
        self.resource["enabled"] = enabled
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
