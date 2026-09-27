"""Site connectivity sensors for Pangolin."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import LEVEL_STATUS, OPT_PRIVATE, OPT_PUBLIC
from .coordinator import PangolinConfigEntry, PangolinCoordinator
from .entity import (
    PangolinPrivateResourceEntity,
    PangolinResourceEntity,
    PangolinSiteEntity,
    add_entities_dynamically,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PangolinConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    options = entry.runtime_data.options
    add_entities_dynamically(
        entry,
        async_add_entities,
        site_factory=lambda c, sid: [PangolinSiteOnline(c, sid)],
        # Status-only mode shows Enabled read-only instead of as a switch.
        resource_factory=(
            (lambda c, rid: [PangolinResourceEnabled(c, rid)])
            if options[OPT_PUBLIC] == LEVEL_STATUS
            else None
        ),
        private_factory=(
            (lambda c, rid: [PangolinPrivateResourceEnabled(c, rid)])
            if options[OPT_PRIVATE] == LEVEL_STATUS
            else None
        ),
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


class _ReadOnlyEnabled(BinarySensorEntity):
    """Whether a resource is enabled, without the ability to change it."""

    _attr_translation_key = "resource_enabled"
    resource: dict[str, Any]

    @property
    def is_on(self) -> bool | None:
        value = self.resource.get("enabled")
        return None if value is None else bool(value)


class PangolinResourceEnabled(PangolinResourceEntity, _ReadOnlyEnabled):
    """Read-only enabled state of a public resource."""

    def __init__(self, coordinator: PangolinCoordinator, resource_id: int) -> None:
        super().__init__(coordinator, resource_id, "enabled")


class PangolinPrivateResourceEnabled(PangolinPrivateResourceEntity, _ReadOnlyEnabled):
    """Read-only enabled state of a private resource."""

    _attr_translation_key = "private_resource_enabled"

    def __init__(self, coordinator: PangolinCoordinator, site_resource_id: int) -> None:
        super().__init__(coordinator, site_resource_id, "enabled")
