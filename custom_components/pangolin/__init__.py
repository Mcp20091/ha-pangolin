"""The Pangolin integration."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PangolinClient
from .const import (
    DOMAIN,
    CONF_ORG_ID,
    LEVEL_CONTROL,
    LEVEL_OFF,
    LEVEL_STATUS,
    OPT_CLIENT_DELETE,
    OPT_CLIENTS,
    OPT_PRIVATE,
    OPT_PUBLIC,
    OPT_RESET_BANDWIDTH,
    OPT_RESTART,
    OPT_TRAFFIC,
)
from .coordinator import PangolinConfigEntry, PangolinCoordinator, get_options

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: PangolinConfigEntry) -> bool:
    """Set up Pangolin from a config entry."""
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, True)
    client = PangolinClient(
        async_get_clientsession(hass, verify_ssl=verify_ssl),
        entry.data[CONF_URL],
        entry.data[CONF_API_KEY],
        entry.data[CONF_ORG_ID],
        verify_ssl,
    )
    _remove_disabled_features(hass, entry)
    coordinator = PangolinCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PangolinConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(hass: HomeAssistant, entry: PangolinConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _resource_entity_wanted(level: str, domain: str) -> bool:
    if level == LEVEL_OFF:
        return False
    if domain == Platform.SWITCH:
        return level == LEVEL_CONTROL
    if domain == Platform.BINARY_SENSOR:
        return level == LEVEL_STATUS
    return True


def _remove_disabled_features(hass: HomeAssistant, entry: PangolinConfigEntry) -> None:
    """Drop entities and devices left behind by features that were turned off."""
    options: dict[str, Any] = get_options(entry)
    ent_reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        uid = ent.unique_id
        # Client entities first: their data/button suffixes overlap sites'.
        if "_client_" in uid:
            if ent.domain == Platform.BUTTON:
                wanted = options[OPT_CLIENT_DELETE]
            elif ent.domain == Platform.SWITCH:
                wanted = options[OPT_CLIENTS] == LEVEL_CONTROL
            else:
                wanted = options[OPT_CLIENTS] != LEVEL_OFF
        elif "_resource_" in uid:
            wanted = _resource_entity_wanted(options[OPT_PUBLIC], ent.domain)
        elif "_private_" in uid:
            wanted = _resource_entity_wanted(options[OPT_PRIVATE], ent.domain)
        elif uid.endswith("_org_reset_bandwidth"):
            wanted = options[OPT_RESET_BANDWIDTH]
        elif ent.domain == Platform.BUTTON:
            wanted = options[OPT_RESTART]
        elif uid.endswith(("_data_in", "_data_out")):
            wanted = options[OPT_TRAFFIC]
        else:
            wanted = True
        if not wanted:
            ent_reg.async_remove(ent.entity_id)

    dev_reg = dr.async_get(hass)
    for dev in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        ids = {i for d, i in dev.identifiers}
        if (
            options[OPT_PUBLIC] == LEVEL_OFF and any("_resource_" in i for i in ids)
        ) or (
            options[OPT_PRIVATE] == LEVEL_OFF and any("_private_" in i for i in ids)
        ) or (
            options[OPT_CLIENTS] == LEVEL_OFF and any("_client_" in i for i in ids)
        ):
            dev_reg.async_remove_device(dev.id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: PangolinConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow deleting a device once its site, resource or client is gone."""
    data = entry.runtime_data.data
    prefix = f"{entry.entry_id}_"
    for domain, identifier in device.identifiers:
        if domain != DOMAIN or not identifier.startswith(prefix):
            continue
        kind, _, raw_id = identifier[len(prefix):].partition("_")
        current = {
            "site": data.sites,
            "resource": data.resources,
            "private": data.private_resources,
            "client": data.clients,
        }.get(kind)
        if current is None:  # the org device always stays
            return False
        try:
            return int(raw_id) not in current
        except ValueError:
            return False
    return True
