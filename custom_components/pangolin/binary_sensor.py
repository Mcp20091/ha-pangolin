"""Site connectivity sensors for Pangolin."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PangolinConfigEntry, PangolinCoordinator
from .entity import PangolinSiteEntity, add_entities_dynamically


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PangolinConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    add_entities_dynamically(
        entry,
        async_add_entities,
        site_factory=lambda c, sid: [PangolinSiteOnline(c, sid)],
    )


class PangolinSiteOnline(PangolinSiteEntity, BinarySensorEntity):
    """Whether the site tunnel is connected."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "site_online"

    def __init__(self, coordinator: PangolinCoordinator, site_id: int) -> None:
        super().__init__(coordinator, site_id, "online")

    @property
    def is_on(self) -> bool | None:
        value = self.site.get("online")
        return None if value is None else bool(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        site = self.site
        return {
            "site_id": self.site_id,
            "nice_id": site.get("niceId"),
            "type": site.get("type"),
            "address": site.get("address"),
            "status": site.get("status"),
        }
