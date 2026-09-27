"""Resource enable/disable switches for Pangolin."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import PangolinError
from .const import (
    LEVEL_CONTROL,
    OPT_CLIENTS,
    OPT_PRIVATE,
    OPT_PUBLIC,
    OPT_PUBLIC_BLOCK,
    OPT_PUBLIC_MAINTENANCE,
    OPT_PUBLIC_SSO,
)
from .coordinator import PangolinConfigEntry, PangolinCoordinator
from .entity import (
    PangolinClientEntity,
    PangolinPrivateResourceEntity,
    PangolinResourceEntity,
    add_entities_dynamically,
    private_resource_attributes,
    run_action,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PangolinConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    options = entry.runtime_data.options

    def resource_switches(c: PangolinCoordinator, rid: int) -> list[SwitchEntity]:
        switches: list[SwitchEntity] = []
        if options[OPT_PUBLIC] == LEVEL_CONTROL:
            switches.append(PangolinResourceSwitch(c, rid))
        if options[OPT_PUBLIC_SSO]:
            switches.append(PangolinResourceSsoSwitch(c, rid))
        if options[OPT_PUBLIC_BLOCK]:
            switches.append(PangolinResourceDetailSwitch(c, rid, BLOCK_ACCESS))
        if options[OPT_PUBLIC_MAINTENANCE]:
            switches.append(PangolinResourceDetailSwitch(c, rid, MAINTENANCE))
        return switches

    add_entities_dynamically(
        entry,
        async_add_entities,
        resource_factory=resource_switches,
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
        return private_resource_attributes(self.resource, self.site_resource_id)


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


class PangolinResourceSsoSwitch(PangolinResourceEntity, SwitchEntity):
    """Requires (or stops requiring) Pangolin sign-in for a public resource."""

    _attr_translation_key = "resource_sso"

    def __init__(self, coordinator: PangolinCoordinator, resource_id: int) -> None:
        super().__init__(coordinator, resource_id, "sso")

    @property
    def is_on(self) -> bool | None:
        value = self.resource.get("sso")
        return None if value is None else bool(value)

    async def _set(self, on: bool) -> None:
        await run_action(
            self.coordinator.client.update_resource(self.resource_id, sso=on),
            f"Could not turn SSO {'on' if on else 'off'}",
            "Update Resource",
        )
        self.resource["sso"] = on
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)


# (API field, unique ID key / translation key, message when Pangolin ignores it)
BLOCK_ACCESS = (
    "blockAccess",
    "block_access",
    "Pangolin didn't apply the block access change.",
)
MAINTENANCE = (
    "maintenanceModeEnabled",
    "maintenance",
    "Pangolin didn't apply maintenance mode. It only works on a licensed "
    "(Enterprise) Pangolin server.",
)


class PangolinResourceDetailSwitch(PangolinResourceEntity, SwitchEntity):
    """A resource setting only in the full resource details (block, maintenance)."""

    def __init__(
        self,
        coordinator: PangolinCoordinator,
        resource_id: int,
        setting: tuple[str, str, str],
    ) -> None:
        self._field, key, self._not_applied = setting
        super().__init__(coordinator, resource_id, key)
        self._attr_translation_key = f"resource_{key}"

    @property
    def detail(self) -> dict[str, Any]:
        return self.coordinator.data.resource_details.get(self.resource_id, {})

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.resource_id in self.coordinator.data.resource_details
        )

    @property
    def is_on(self) -> bool | None:
        value = self.detail.get(self._field)
        return None if value is None else bool(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self._field != "maintenanceModeEnabled":
            return None
        # forced: page always shown; automatic: only while every target is down.
        return {"maintenance_type": self.detail.get("maintenanceModeType")}

    async def _set(self, on: bool) -> None:
        await run_action(
            self.coordinator.client.update_resource(
                self.resource_id, **{self._field: on}
            ),
            "Could not change the setting",
            "Update Resource",
        )
        # Pangolin can accept the request yet ignore it (maintenance mode on an
        # unlicensed server), so read it back instead of assuming.
        try:
            detail = await self.coordinator.async_refresh_resource_detail(
                self.resource_id
            )
        except PangolinError as err:
            raise HomeAssistantError(
                f"The change was sent, but reading it back failed: {err}"
            ) from err
        if bool(detail.get(self._field)) != on:
            raise HomeAssistantError(self._not_applied)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
