"""Base entities for Pangolin."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PangolinConfigEntry, PangolinCoordinator


class PangolinSiteEntity(CoordinatorEntity[PangolinCoordinator]):
    """Entity tied to a Pangolin site."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PangolinCoordinator, site_id: int, key: str) -> None:
        super().__init__(coordinator)
        self.site_id = site_id
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_site_{site_id}_{key}"
        site = self.site
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_site_{site_id}")},
            name=f"Pangolin Site {site.get('name', site_id)}",
            manufacturer="Pangolin",
            model=f"Site ({site.get('type') or 'unknown'})",
            sw_version=site.get("newtVersion"),
        )

    @property
    def site(self) -> dict[str, Any]:
        return self.coordinator.data.sites.get(self.site_id, {})

    @property
    def available(self) -> bool:
        return super().available and self.site_id in self.coordinator.data.sites


class PangolinResourceEntity(CoordinatorEntity[PangolinCoordinator]):
    """Entity tied to a Pangolin resource."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: PangolinCoordinator, resource_id: int, key: str
    ) -> None:
        super().__init__(coordinator)
        self.resource_id = resource_id
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_resource_{resource_id}_{key}"
        res = self.resource
        domain = res.get("fullDomain")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_resource_{resource_id}")},
            name=f"Pangolin {res.get('name', resource_id)}",
            manufacturer="Pangolin",
            model=f"Resource ({res.get('mode') or 'http'})",
            configuration_url=f"https://{domain}" if domain else None,
        )

    @property
    def resource(self) -> dict[str, Any]:
        return self.coordinator.data.resources.get(self.resource_id, {})

    @property
    def available(self) -> bool:
        return (
            super().available and self.resource_id in self.coordinator.data.resources
        )


def add_entities_dynamically(
    entry: PangolinConfigEntry,
    async_add_entities: Callable[[Iterable[Entity]], None],
    site_factory: Callable[[PangolinCoordinator, int], list[Entity]] | None = None,
    resource_factory: Callable[[PangolinCoordinator, int], list[Entity]] | None = None,
) -> None:
    """Add entities now and whenever new sites or resources appear."""
    coordinator = entry.runtime_data
    known_sites: set[int] = set()
    known_resources: set[int] = set()

    def _check() -> None:
        new: list[Entity] = []
        if site_factory:
            for site_id in coordinator.data.sites.keys() - known_sites:
                known_sites.add(site_id)
                new.extend(site_factory(coordinator, site_id))
        if resource_factory:
            for res_id in coordinator.data.resources.keys() - known_resources:
                known_resources.add(res_id)
                new.extend(resource_factory(coordinator, res_id))
        if new:
            async_add_entities(new)

    _check()
    entry.async_on_unload(coordinator.async_add_listener(_check))
