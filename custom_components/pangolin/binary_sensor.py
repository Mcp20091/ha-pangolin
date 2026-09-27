"""Site connectivity sensors for Pangolin."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import LEVEL_OFF, LEVEL_STATUS, OPT_CLIENTS, OPT_PRIVATE, OPT_PUBLIC
from .coordinator import PangolinConfigEntry, PangolinCoordinator
from .entity import (
    PangolinClientEntity,
    PangolinOrgEntity,
    PangolinPrivateResourceEntity,
    PangolinResourceEntity,
    PangolinSiteEntity,
    add_entities_dynamically,
    private_resource_attributes,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PangolinConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    options = entry.runtime_data.options
    async_add_entities([PangolinApiReachable(entry.runtime_data)])
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
        client_factory=(
            (lambda c, cid: [PangolinClientOnline(c, cid)])
            if options[OPT_CLIENTS] != LEVEL_OFF
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
            "newt_version": site.get("newtVersion"),
            "agent_version": site.get("agentVersion"),
            "exit_node": site.get("exitNodeName"),
            "resource_count": site.get("resourceCount"),
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

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return private_resource_attributes(self.resource, self.site_resource_id)

    def __init__(self, coordinator: PangolinCoordinator, site_resource_id: int) -> None:
        super().__init__(coordinator, site_resource_id, "enabled")


class PangolinApiReachable(PangolinOrgEntity, BinarySensorEntity):
    """Whether Pangolin answers at all, separate from the key being accepted."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "api_reachable"

    def __init__(self, coordinator: PangolinCoordinator) -> None:
        super().__init__(coordinator, "api_reachable")

    @property
    def available(self) -> bool:
        # Stays available when updates fail, since reporting that is its job.
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.api_reachable


class PangolinClientOnline(PangolinClientEntity, BinarySensorEntity):
    """Whether a client (machine client or user device) is connected."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "client_online"

    def __init__(self, coordinator: PangolinCoordinator, client_id: int) -> None:
        super().__init__(coordinator, client_id, "online")

    @property
    def is_on(self) -> bool | None:
        value = self.client.get("online")
        return None if value is None else bool(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        client = self.client
        return {
            "client_id": self.client_id,
            "kind": client.get("kind"),
            "user": client.get("username"),
            "version": client.get("olmVersion"),
            "device_model": client.get("deviceModel"),
            "platform": client.get("fingerprintPlatform"),
            "os_version": client.get("fingerprintOsVersion"),
            "arch": client.get("fingerprintArch"),
            "agent": client.get("agent"),
            "user_type": client.get("userType"),
            "blocked": client.get("blocked"),
            "archived": client.get("archived"),
            "approval_state": client.get("approvalState"),
        }
