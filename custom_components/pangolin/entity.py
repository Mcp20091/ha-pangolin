"""Base entities for Pangolin."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import PangolinAuthError, PangolinError
from .const import CONF_ORG_ID, DOMAIN
from .coordinator import PangolinConfigEntry, PangolinCoordinator


class PangolinOrgEntity(CoordinatorEntity[PangolinCoordinator]):
    """Entity tied to the Pangolin organization as a whole."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PangolinCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_org_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_org")},
            name=f"Pangolin {entry.data[CONF_ORG_ID]}",
            manufacturer="Pangolin",
            model="Organization",
        )


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
            entry_type=DeviceEntryType.SERVICE,
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


class PangolinPrivateResourceEntity(CoordinatorEntity[PangolinCoordinator]):
    """Entity tied to a Pangolin private (site) resource."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: PangolinCoordinator, site_resource_id: int, key: str
    ) -> None:
        super().__init__(coordinator)
        self.site_resource_id = site_resource_id
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_private_{site_resource_id}_{key}"
        res = self.resource
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_private_{site_resource_id}")},
            name=f"Pangolin {res.get('name', site_resource_id)}",
            manufacturer="Pangolin",
            model=f"Private resource ({res.get('mode') or 'unknown'})",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def resource(self) -> dict[str, Any]:
        return self.coordinator.data.private_resources.get(self.site_resource_id, {})

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.site_resource_id in self.coordinator.data.private_resources
        )


class PangolinClientEntity(CoordinatorEntity[PangolinCoordinator]):
    """Entity tied to a Pangolin client (machine client or user device)."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: PangolinCoordinator, client_id: int, key: str
    ) -> None:
        super().__init__(coordinator)
        self.client_id = client_id
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_client_{client_id}_{key}"
        client = self.client
        if client.get("kind") == "user":
            model = "User device"
            if client.get("deviceModel"):
                model = f"User device ({client['deviceModel']})"
        else:
            model = "Machine client"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_client_{client_id}")},
            name=f"Pangolin {client.get('name', client_id)}",
            manufacturer="Pangolin",
            model=model,
            sw_version=client.get("olmVersion"),
        )

    @property
    def client(self) -> dict[str, Any]:
        return self.coordinator.data.clients.get(self.client_id, {})

    @property
    def available(self) -> bool:
        return super().available and self.client_id in self.coordinator.data.clients


def add_entities_dynamically(
    entry: PangolinConfigEntry,
    async_add_entities: Callable[[Iterable[Entity]], None],
    site_factory: Callable[[PangolinCoordinator, int], list[Entity]] | None = None,
    resource_factory: Callable[[PangolinCoordinator, int], list[Entity]] | None = None,
    private_factory: Callable[[PangolinCoordinator, int], list[Entity]] | None = None,
    client_factory: Callable[[PangolinCoordinator, int], list[Entity]] | None = None,
) -> None:
    """Add entities now and whenever new sites or resources appear."""
    coordinator = entry.runtime_data
    known_sites: set[int] = set()
    known_resources: set[int] = set()
    known_private: set[int] = set()
    known_clients: set[int] = set()

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
        if private_factory:
            for res_id in coordinator.data.private_resources.keys() - known_private:
                known_private.add(res_id)
                new.extend(private_factory(coordinator, res_id))
        if client_factory:
            for client_id in coordinator.data.clients.keys() - known_clients:
                known_clients.add(client_id)
                new.extend(client_factory(coordinator, client_id))
        if new:
            async_add_entities(new)

    _check()
    entry.async_on_unload(coordinator.async_add_listener(_check))


async def run_action(action: Awaitable[None], failure: str, permission: str) -> None:
    """Run a Pangolin call, turning failures into readable errors."""
    try:
        await action
    except PangolinAuthError as err:
        if err.status == 403:
            raise HomeAssistantError(
                f"{failure}: the API key needs the {permission} permission in Pangolin."
            ) from err
        raise HomeAssistantError(f"{failure}: {err}") from err
    except PangolinError as err:
        raise HomeAssistantError(f"{failure}: {err}") from err


def _sites(names: Any, onlines: Any) -> list[dict[str, Any]]:
    names = names or []
    onlines = onlines or []
    return [
        {"name": name, "online": onlines[i] if i < len(onlines) else None}
        for i, name in enumerate(names)
    ]


def public_resource_details(res: dict[str, Any]) -> dict[str, Any]:
    """Targets, sites and protection of a public resource, from the list data."""
    return {
        "mode": res.get("mode"),
        "ssl": res.get("ssl"),
        "sites": [
            {"name": s.get("siteName"), "online": s.get("online")}
            for s in res.get("sites") or []
        ],
        "targets": [
            {
                "site": t.get("siteName"),
                "target": f"{t.get('ip')}:{t.get('port')}",
                "enabled": t.get("enabled"),
                "health_check": t.get("hcEnabled"),
                "health": t.get("healthStatus"),
            }
            for t in res.get("targets") or []
        ],
        "protection": {
            "sso": bool(res.get("sso")),
            "password": res.get("passwordId") is not None,
            "pin": res.get("pincodeId") is not None,
            "email_whitelist": bool(res.get("whitelist")),
            "header_auth": res.get("headerAuthId") is not None,
        },
    }


def private_resource_attributes(res: dict[str, Any], site_resource_id: int) -> dict[str, Any]:
    """What a private resource points at and which sites carry it."""
    return {
        "site_resource_id": site_resource_id,
        "nice_id": res.get("niceId"),
        "mode": res.get("mode"),
        "destination": res.get("destination"),
        "alias": res.get("alias"),
        "alias_address": res.get("aliasAddress"),
        "tcp_ports": res.get("tcpPortRangeString"),
        "udp_ports": res.get("udpPortRangeString"),
        "icmp": None if res.get("disableIcmp") is None else not res.get("disableIcmp"),
        "sites": _sites(res.get("siteNames"), res.get("siteOnlines")),
    }
