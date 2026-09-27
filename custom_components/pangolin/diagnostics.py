"""Diagnostics for Pangolin, with anything identifying removed."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import HomeAssistant

from .const import CONF_ORG_ID
from .coordinator import PangolinConfigEntry

# Keys, addresses, domains and names can identify the user's setup, so none
# of them leave Home Assistant in a diagnostics file.
TO_REDACT = {
    CONF_API_KEY,
    CONF_URL,
    CONF_ORG_ID,
    "orgId",
    "orgName",
    "name",
    "niceId",
    "fullDomain",
    "domain",
    "subdomain",
    "domainId",
    "destination",
    "address",
    "alias",
    "aliasAddress",
    "siteNames",
    "siteNiceIds",
    "subnet",
    "pubKey",
    "endpoint",
    "username",
    "userEmail",
    "email",
    "userId",
    "labels",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PangolinConfigEntry
) -> dict[str, Any]:
    """Return redacted settings, feature choices and the latest data."""
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "resolved_features": coordinator.options,
        "api_reachable": coordinator.api_reachable,
        "last_update_success": coordinator.last_update_success,
        "counts": {
            "sites": len(data.sites),
            "public_resources": len(data.resources),
            "private_resources": len(data.private_resources),
            "clients": len(data.clients),
        },
        "data": async_redact_data(
            {
                kind: list(items.values())
                for kind, items in asdict(data).items()
            },
            TO_REDACT,
        ),
    }
