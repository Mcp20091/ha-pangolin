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
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
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
    PangolinNotFoundError,
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

# Features that only work when the key can read the matching resource list.
FEATURE_NEEDS = {
    FEATURE_PUBLIC_STATUS: OPT_PUBLIC,
    FEATURE_PUBLIC_CONTROL: OPT_PUBLIC,
    FEATURE_PRIVATE_STATUS: OPT_PRIVATE,
    FEATURE_PRIVATE_CONTROL: OPT_PRIVATE,
}

URL_SUFFIX = "/v1"
PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL, suffix=URL_SUFFIX)
        ),
        vol.Required(CONF_API_KEY): PASSWORD_SELECTOR,
        vol.Optional(CONF_VERIFY_SSL, default=True): bool,
    }
)


def _client(hass: HomeAssistant, data: Mapping[str, Any]) -> PangolinClient:
    verify_ssl = data.get(CONF_VERIFY_SSL, True)
    return PangolinClient(
        async_get_clientsession(hass, verify_ssl=verify_ssl),
        data[CONF_URL],
        data[CONF_API_KEY],
        data.get(CONF_ORG_ID, ""),
        verify_ssl,
    )


def _error_key(err: PangolinError) -> str:
    if isinstance(err, PangolinAuthError):
        return "invalid_auth"
    if isinstance(err, PangolinConnectionError):
        return "cannot_connect"
    return "unknown"


def _url_for_display(url: str) -> str:
    """The form shows /v1 beside the box, so leave it out of the value."""
    return url.removesuffix(URL_SUFFIX)


class _FeatureStep:
    """Feature checklist shared by the config and options flows."""

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

    def _show_features(self, selected: list[str]) -> ConfigFlowResult:
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
            }
        )
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="features",
            data_schema=self.add_suggested_values_to_schema(  # type: ignore[attr-defined]
                schema, {CONF_FEATURES: [f for f in selected if f in capable]}
            ),
            description_placeholders={"unavailable": self._unavailable_text()},
        )


class PangolinConfigFlow(_FeatureStep, ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Pangolin."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._access = {}
        # orgId -> name when the key may list organizations (root keys only).
        self._orgs: dict[str, str] | None = None
        self._title = ""

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PangolinOptionsFlow:
        return PangolinOptionsFlow()

    async def _validate_org(self, data: dict[str, Any]) -> str | None:
        """Check the key against one org and record what it can read."""
        client = _client(self.hass, data)
        try:
            org = await client.get_org()
            await client.list_sites()
            self._access = await client.probe_access()
        except PangolinError as err:
            return _error_key(err)
        name = ((org or {}).get("org") or {}).get("name")
        self._title = f"Pangolin ({name or data[CONF_ORG_ID]})"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**user_input, CONF_URL: normalize_url(user_input[CONF_URL])}
            try:
                orgs = await _client(self.hass, data).list_orgs()
            except PangolinAuthError as err:
                if err.status == 403:
                    # Org-scoped key: it works, it just can't list orgs.
                    self._data, self._orgs = data, None
                    return await self.async_step_org()
                errors["base"] = "invalid_auth"
            except PangolinNotFoundError:
                self._data, self._orgs = data, None
                return await self.async_step_org()
            except PangolinError as err:
                errors["base"] = _error_key(err)
            else:
                self._data = data
                self._orgs = {
                    str(o["orgId"]): str(o.get("name") or o["orgId"]) for o in orgs
                }
                if not self._orgs:
                    errors["base"] = "no_orgs"
                elif len(self._orgs) == 1:
                    return await self.async_step_org(
                        {CONF_ORG_ID: next(iter(self._orgs))}
                    )
                else:
                    return await self.async_step_org()
        suggested = (
            {**user_input, CONF_URL: _url_for_display(user_input[CONF_URL])}
            if user_input
            else None
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, suggested),
            errors=errors,
        )

    async def async_step_org(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            org_id = str(user_input[CONF_ORG_ID]).strip()
            data = {**self._data, CONF_ORG_ID: org_id}
            await self.async_set_unique_id(f"{data[CONF_URL]}|{org_id}")
            self._abort_if_unique_id_configured()
            if (error := await self._validate_org(data)) is None:
                self._data = data
                return self._show_features(self._capable())
            errors["base"] = "org_denied" if error == "invalid_auth" else error

        if self._orgs:
            field: Any = SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=oid, label=f"{name} ({oid})")
                        for oid, name in sorted(
                            self._orgs.items(), key=lambda o: o[1].lower()
                        )
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
            step_id = "org"
        else:
            field = str
            step_id = "org_manual"
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_ORG_ID): field}), user_input
            ),
            errors=errors,
        )

    async def async_step_org_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_org(user_input)

    async def async_step_features(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            return self._show_features(self._capable())
        capable = self._capable()
        return self.async_create_entry(
            title=self._title,
            data=self._data,
            options={
                CONF_FEATURES: [
                    f for f in user_input.get(CONF_FEATURES, []) if f in capable
                ]
            },
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
            if (error := await self._validate_org(data)) is None:
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
        capable = self._capable()
        return self.async_create_entry(
            data={
                CONF_FEATURES: [
                    f for f in user_input.get(CONF_FEATURES, []) if f in capable
                ]
            }
        )
