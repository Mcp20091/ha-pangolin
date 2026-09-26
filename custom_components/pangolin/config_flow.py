"""Config flow for Pangolin."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    PangolinAuthError,
    PangolinClient,
    PangolinConnectionError,
    PangolinError,
    normalize_url,
)
from .const import (
    ALL_FEATURES,
    CONF_FEATURES,
    CONF_ORG_ID,
    DOMAIN,
    FEATURE_PRIVATE_CONTROL,
    FEATURE_PRIVATE_STATUS,
    FEATURE_PUBLIC_CONTROL,
    FEATURE_PUBLIC_STATUS,
    OPT_PRIVATE,
    OPT_PUBLIC,
)

CONF_BULK = "bulk"
BULK_ALL = "select_all"
BULK_NONE = "select_none"
BULK_INVERT = "invert"

# Features that only work when the key can read the matching resource list.
FEATURE_NEEDS = {
    FEATURE_PUBLIC_STATUS: OPT_PUBLIC,
    FEATURE_PUBLIC_CONTROL: OPT_PUBLIC,
    FEATURE_PRIVATE_STATUS: OPT_PRIVATE,
    FEATURE_PRIVATE_CONTROL: OPT_PRIVATE,
}

PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_API_KEY): PASSWORD_SELECTOR,
        vol.Required(CONF_ORG_ID): str,
        vol.Optional(CONF_VERIFY_SSL, default=True): bool,
    }
)


def _client(hass: HomeAssistant, data: Mapping[str, Any]) -> PangolinClient:
    verify_ssl = data.get(CONF_VERIFY_SSL, True)
    return PangolinClient(
        async_get_clientsession(hass, verify_ssl=verify_ssl),
        data[CONF_URL],
        data[CONF_API_KEY],
        data[CONF_ORG_ID],
        verify_ssl,
    )


def _error_key(err: PangolinError) -> str:
    if isinstance(err, PangolinAuthError):
        return "invalid_auth"
    if isinstance(err, PangolinConnectionError):
        return "cannot_connect"
    return "unknown"


class _FeatureStep:
    """Feature checklist shared by the config and options flows.

    Home Assistant forms can't run scripts, so select all / unselect all /
    invert are a dropdown that redraws the form with the new ticks.
    """

    _access: dict[str, bool]

    def _capable(self) -> list[str]:
        return [
            f
            for f in ALL_FEATURES
            if f not in FEATURE_NEEDS or self._access[FEATURE_NEEDS[f]]
        ]

    def _unavailable_text(self) -> str:
        missing = [
            label
            for opt, label in ((OPT_PUBLIC, "public"), (OPT_PRIVATE, "private"))
            if not self._access[opt]
        ]
        if not missing:
            return "None. This key can read everything the integration uses."
        return (
            f"{' and '.join(missing).capitalize()} resource features are hidden "
            "because this key can't list them (missing permission, or your "
            "Pangolin version doesn't support them)."
        )

    def _show_features(
        self, selected: list[str], errors: dict[str, str] | None = None
    ) -> FlowResult:
        capable = self._capable()
        schema = vol.Schema(
            {
                vol.Optional(CONF_FEATURES): SelectSelector(
                    SelectSelectorConfig(
                        options=capable,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                        translation_key="feature",
                    )
                ),
                vol.Optional(CONF_BULK): SelectSelector(
                    SelectSelectorConfig(
                        options=[BULK_ALL, BULK_NONE, BULK_INVERT],
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key="bulk",
                    )
                ),
            }
        )
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="features",
            data_schema=self.add_suggested_values_to_schema(  # type: ignore[attr-defined]
                schema, {CONF_FEATURES: [f for f in selected if f in capable]}
            ),
            description_placeholders={"unavailable": self._unavailable_text()},
            errors=errors or {},
        )

    def _handle_features(
        self, user_input: dict[str, Any]
    ) -> tuple[list[str], bool]:
        """Return the selection and whether it is final (no bulk action used)."""
        capable = self._capable()
        selected = [f for f in user_input.get(CONF_FEATURES, []) if f in capable]
        bulk = user_input.get(CONF_BULK)
        if bulk == BULK_ALL:
            return capable, False
        if bulk == BULK_NONE:
            return [], False
        if bulk == BULK_INVERT:
            return [f for f in capable if f not in selected], False
        return selected, True


class PangolinConfigFlow(_FeatureStep, ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Pangolin."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._access = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PangolinOptionsFlow:
        return PangolinOptionsFlow()

    async def _validate(self, data: dict[str, Any]) -> str | None:
        """Return an error key, or None when the credentials work."""
        client = _client(self.hass, data)
        try:
            await client.get_org()
            await client.list_sites()
            self._access = await client.probe_access()
        except PangolinError as err:
            return _error_key(err)
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
                self._data = user_input
                return self._show_features(self._capable())
            errors["base"] = error
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_features(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            return self._show_features(self._capable())
        selected, final = self._handle_features(user_input)
        if not final:
            return self._show_features(selected)
        return self.async_create_entry(
            title=f"Pangolin ({self._data[CONF_ORG_ID]})",
            data=self._data,
            options={CONF_FEATURES: selected},
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
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): PASSWORD_SELECTOR}),
            errors=errors,
        )


class PangolinOptionsFlow(_FeatureStep, OptionsFlow):
    """Change which Pangolin features are used."""

    def __init__(self) -> None:
        self._access = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        try:
            self._access = await _client(
                self.hass, self.config_entry.data
            ).probe_access()
        except PangolinError as err:
            return self.async_abort(reason=_error_key(err))
        current = self.config_entry.options.get(CONF_FEATURES, ALL_FEATURES)
        return self._show_features(list(current))

    async def async_step_features(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            return await self.async_step_init()
        selected, final = self._handle_features(user_input)
        if not final:
            return self._show_features(selected)
        return self.async_create_entry(data={CONF_FEATURES: selected})
