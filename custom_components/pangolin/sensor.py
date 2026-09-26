"""Resource health and site traffic sensors for Pangolin."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PangolinConfigEntry, PangolinCoordinator
from .entity import PangolinResourceEntity, PangolinSiteEntity, add_entities_dynamically

HEALTH_OPTIONS = ["healthy", "degraded", "offline", "unknown"]
# Older Pangolin builds reported fully-down resources as "unhealthy".
HEALTH_ALIASES = {"unhealthy": "offline"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PangolinConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    add_entities_dynamically(
        entry,
        async_add_entities,
        site_factory=lambda c, sid: [
            PangolinSiteTraffic(c, sid, "megabytesIn", "data_in"),
            PangolinSiteTraffic(c, sid, "megabytesOut", "data_out"),
        ],
        resource_factory=lambda c, rid: [PangolinResourceHealth(c, rid)],
    )


class PangolinResourceHealth(PangolinResourceEntity, SensorEntity):
    """Aggregate target health for a resource."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = HEALTH_OPTIONS
    _attr_translation_key = "resource_health"

    def __init__(self, coordinator: PangolinCoordinator, resource_id: int) -> None:
        super().__init__(coordinator, resource_id, "health")

    @property
    def native_value(self) -> str | None:
        health = self.resource.get("health")
        health = HEALTH_ALIASES.get(health, health)
        return health if health in HEALTH_OPTIONS else "unknown"


class PangolinSiteTraffic(PangolinSiteEntity, SensorEntity):
    """Data transferred through a site tunnel."""

    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_native_unit_of_measurement = UnitOfInformation.MEGABYTES
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_suggested_display_precision = 1

    def __init__(
        self, coordinator: PangolinCoordinator, site_id: int, field: str, key: str
    ) -> None:
        super().__init__(coordinator, site_id, key)
        self._field = field
        self._attr_translation_key = key

    @property
    def native_value(self) -> float | None:
        value = self.site.get(self._field)
        return None if value is None else float(value)
