"""Config flow for Pangolin."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    PangolinAuthError,
    PangolinClient,
    PangolinConnectionError,
    PangolinError,
    normalize_url,
)
from .const import CONF_ORG_ID, DOMAIN

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_ORG_ID): str,
        vol.Optional(CONF_VERIFY_SSL, default=True): bool,
    }
)


class PangolinConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Pangolin."""

    VERSION = 1

    async def _validate(self, data: dict[str, Any]) -> str | None:
        """Return an error key, or None when the credentials work."""
        verify_ssl = data.get(CONF_VERIFY_SSL, True)
        client = PangolinClient(
            async_get_clientsession(self.hass, verify_ssl=verify_ssl),
            data[CONF_URL],
            data[CONF_API_KEY],
            data[CONF_ORG_ID],
            verify_ssl,
        )
        try:
            await client.get_org()
            await client.list_sites()
            await client.list_resources()
        except PangolinAuthError:
            return "invalid_auth"
        except PangolinConnectionError:
            return "cannot_connect"
        except PangolinError:
            return "unknown"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_URL] = normalize_url(user_input[CONF_URL])
            user_input[CONF_ORG_ID] = user_input[CONF_ORG_ID].strip()
            await self.async_set_unique_id(
                f"{user_input[CONF_URL]}|{user_input[CONF_ORG_ID]}"
            )
            self._abort_if_unique_id_configured()
            if (error := await self._validate(user_input)) is None:
                return self.async_create_entry(
                    title=f"Pangolin ({user_input[CONF_ORG_ID]})", data=user_input
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = {**entry.data, CONF_API_KEY: user_input[CONF_API_KEY]}
            if (error := await self._validate(data)) is None:
                return self.async_update_reload_and_abort(entry, data=data)
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )
