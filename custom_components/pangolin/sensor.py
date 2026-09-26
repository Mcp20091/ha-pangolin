"""Resource health and site traffic sensors for Pangolin."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import LEVEL_OFF, OPT_PUBLIC, OPT_TRAFFIC
from .coordinator import PangolinConfigEntry, PangolinCoordinator
from .entity import (
    PangolinOrgEntity,
    PangolinResourceEntity,
    PangolinSiteEntity,
    add_entities_dynamically,
)

HEALTH_OPTIONS = ["healthy", "degraded", "offline", "unknown"]
# Older Pangolin builds reported fully-down resources as "unhealthy".
HEALTH_ALIASES = {"unhealthy": "offline"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PangolinConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    options = entry.runtime_data.options
    async_add_entities([PangolinSitesOnline(entry.runtime_data)])
    add_entities_dynamically(
        entry,
        async_add_entities,
        site_factory=(
            (
                lambda c, sid: [
                    PangolinSiteTraffic(c, sid, "megabytesIn", "data_in"),
                    PangolinSiteTraffic(c, sid, "megabytesOut", "data_out"),
                ]
            )
            if options[OPT_TRAFFIC]
            else None
        ),
        resource_factory=(
            (lambda c, rid: [PangolinResourceHealth(c, rid)])
            if options[OPT_PUBLIC] != LEVEL_OFF
            else None
        ),
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


class PangolinSitesOnline(PangolinOrgEntity, SensorEntity):
    """How many sites are online, with every site listed in the attributes."""

    _attr_translation_key = "sites_online"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: PangolinCoordinator) -> None:
        super().__init__(coordinator, "sites_online")

    @property
    def native_value(self) -> int:
        return sum(1 for s in self.coordinator.data.sites.values() if s.get("online"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        sites = sorted(
            self.coordinator.data.sites.values(),
            key=lambda s: str(s.get("name", "")).lower(),
        )
        return {
            "total": len(sites),
            "sites": [
                {
                    "name": s.get("name"),
                    "online": bool(s.get("online")),
                    "status": s.get("status"),
                    "type": s.get("type"),
                    "address": s.get("address"),
                }
                for s in sites
            ],
        }
