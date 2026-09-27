"""Resource enable/disable switches for Pangolin."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import PangolinError
from .const import LEVEL_CONTROL, OPT_CLIENTS, OPT_PRIVATE, OPT_PUBLIC
from .coordinator import PangolinConfigEntry, PangolinCoordinator
from .entity import (
    PangolinClientEntity,
    PangolinPrivateResourceEntity,
    PangolinResourceEntity,
    add_entities_dynamically,
    run_action,
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
        resource_factory=(
            (lambda c, rid: [PangolinResourceSwitch(c, rid)])
            if options[OPT_PUBLIC] == LEVEL_CONTROL
            else None
        ),
        private_factory=(
            (lambda c, rid: [PangolinPrivateResourceSwitch(c, rid)])
            if options[OPT_PRIVATE] == LEVEL_CONTROL
            else None
        ),
        client_factory=(
            (
                lambda c, cid: [
                    PangolinClientFlagSwitch(c, cid, "blocked"),
                    PangolinClientFlagSwitch(c, cid, "archived"),
                ]
            )
            if options[OPT_CLIENTS] == LEVEL_CONTROL
            else None
        ),
    )


class _EnabledSwitch(SwitchEntity):
    """Shared on/off handling for public and private resources."""

    _attr_translation_key = "resource_enabled"
    coordinator: PangolinCoordinator
    resource: dict[str, Any]

    def _setter(self) -> Callable[[bool], Awaitable[None]]:
        raise NotImplementedError

    @property
    def is_on(self) -> bool | None:
        value = self.resource.get("enabled")
        return None if value is None else bool(value)

    async def _set(self, enabled: bool) -> None:
        try:
            await self._setter()(enabled)
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


class PangolinResourceSwitch(PangolinResourceEntity, _EnabledSwitch):
    """Turns a public Pangolin resource on or off."""

    def __init__(self, coordinator: PangolinCoordinator, resource_id: int) -> None:
        super().__init__(coordinator, resource_id, "enabled")

    def _setter(self) -> Callable[[bool], Awaitable[None]]:
        return lambda on: self.coordinator.client.set_resource_enabled(
            self.resource_id, on
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        res = self.resource
        return {
            "resource_id": self.resource_id,
            "nice_id": res.get("niceId"),
            "full_domain": res.get("fullDomain"),
            "sso": res.get("sso"),
        }


class PangolinPrivateResourceSwitch(PangolinPrivateResourceEntity, _EnabledSwitch):
    """Turns a private Pangolin resource on or off."""

    _attr_translation_key = "private_resource_enabled"

    def __init__(self, coordinator: PangolinCoordinator, site_resource_id: int) -> None:
        super().__init__(coordinator, site_resource_id, "enabled")

    def _setter(self) -> Callable[[bool], Awaitable[None]]:
        return lambda on: self.coordinator.client.set_private_resource_enabled(
            self.site_resource_id, on
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        res = self.resource
        return {
            "site_resource_id": self.site_resource_id,
            "nice_id": res.get("niceId"),
            "mode": res.get("mode"),
            "destination": res.get("destination"),
            "alias": res.get("alias"),
            "sites": res.get("siteNames"),
        }


class PangolinClientFlagSwitch(PangolinClientEntity, SwitchEntity):
    """Blocks/unblocks or archives/unarchives a client."""

    def __init__(
        self, coordinator: PangolinCoordinator, client_id: int, flag: str
    ) -> None:
        super().__init__(coordinator, client_id, flag)
        self._flag = flag
        self._attr_translation_key = f"client_{flag}"

    @property
    def is_on(self) -> bool | None:
        value = self.client.get(self._flag)
        return None if value is None else bool(value)

    async def _set(self, on: bool) -> None:
        client = self.coordinator.client
        if self._flag == "blocked":
            action = client.set_client_blocked(self.client_id, on)
            permission = "Block Client" if on else "Unblock Client"
        else:
            action = client.set_client_archived(self.client_id, on)
            permission = "Archive Client" if on else "Unarchive Client"
        await run_action(action, f"Could not update client {self._flag}", permission)
        self.client[self._flag] = on
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
