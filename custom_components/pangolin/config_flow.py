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
    key_id_of,
    normalize_url,
)
from .const import (
    ACTION_INFO,
    ALL_FEATURES,
    CONF_FEATURES,
    CONF_KNOWN_FEATURES,
    DEFAULT_FEATURES,
    DEFAULT_OFF_FEATURES,
    CONF_ORG_ID,
    DOMAIN,
    FEATURE_NEEDS,
    OPT_CLIENTS,
    OPT_PRIVATE,
    OPT_PUBLIC,
    required_actions,
)

URL_SUFFIX = "/v1"
CONF_ROOT_API_KEY = "root_api_key"
CONF_APPLY = "apply"
NEW_KEY_NAME = "Home Assistant (least privilege)"
PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
URL_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.URL, suffix=URL_SUFFIX)
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): URL_SELECTOR,
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
            for opt, label in (
                (OPT_PUBLIC, "Public resource"),
                (OPT_PRIVATE, "Private resource"),
                (OPT_CLIENTS, "Client"),
            )
            if not self._access[opt]
        ]
        if not missing:
            return "None. This key can read everything the integration uses."
        return (
            f"{', '.join(missing)} features are hidden because this key can't "
            "list them (missing permission, or your Pangolin version doesn't "
            "support them)."
        )

    def _default_selection(self) -> list[str]:
        """Everything the key can use, except permanent actions."""
        return [f for f in self._capable() if f not in DEFAULT_OFF_FEATURES]

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
                return self._show_features(self._default_selection())
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
            return self._show_features(self._default_selection())
        capable = self._capable()
        return self.async_create_entry(
            title=self._title,
            data=self._data,
            options={
                CONF_FEATURES: [
                    f for f in user_input.get(CONF_FEATURES, []) if f in capable
                ],
                CONF_KNOWN_FEATURES: ALL_FEATURES,
            },
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address, SSL check or API key without re-adding."""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            data = {
                **entry.data,
                CONF_URL: normalize_url(user_input[CONF_URL]),
                CONF_VERIFY_SSL: user_input.get(CONF_VERIFY_SSL, True),
            }
            if new_key := (user_input.get(CONF_API_KEY) or "").strip():
                data[CONF_API_KEY] = new_key
            unique_id = f"{data[CONF_URL]}|{data[CONF_ORG_ID]}"
            other = self.hass.config_entries.async_entry_for_domain_unique_id(
                DOMAIN, unique_id
            )
            if other is not None and other.entry_id != entry.entry_id:
                return self.async_abort(reason="already_configured")
            if (error := await self._validate_org(data)) is None:
                return self.async_update_reload_and_abort(
                    entry, unique_id=unique_id, data=data
                )
            errors["base"] = error

        current = user_input or {
            CONF_URL: _url_for_display(entry.data[CONF_URL]),
            CONF_VERIFY_SSL: entry.data.get(CONF_VERIFY_SSL, True),
        }
        schema = vol.Schema(
            {
                vol.Required(CONF_URL): URL_SELECTOR,
                vol.Optional(CONF_API_KEY): PASSWORD_SELECTOR,
                vol.Optional(CONF_VERIFY_SSL, default=True): bool,
            }
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                schema, {k: v for k, v in current.items() if k != CONF_API_KEY}
            ),
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
            if (error := await self._validate_org(data)) is None:
                return self.async_update_reload_and_abort(entry, data=data)
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): PASSWORD_SELECTOR}),
            errors=errors,
        )


def _action_lines(actions: list[str]) -> str:
    return "\n".join(
        f"- {ACTION_INFO[a][0]} (`{a}`): {ACTION_INFO[a][1]}" for a in actions
    ) or "- (none)"


def _plain_list(actions: list[str]) -> str:
    return "\n".join(f"- {ACTION_INFO.get(a, (a,))[0]} (`{a}`)" for a in actions)


class PangolinOptionsFlow(_FeatureStep, OptionsFlow):
    """Change features, or check and tighten the API key's permissions."""

    def __init__(self) -> None:
        self._access = {}
        self._target: list[str] = []
        self._required: list[str] = []
        self._mode = ""
        self._summary = ""
        # Held only for the length of this flow; never written to the entry.
        self._admin: PangolinClient | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["features", "permissions"]
        )

    async def async_step_features(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is None:
            try:
                self._access = await _client(
                    self.hass, self.config_entry.data
                ).probe_access()
            except PangolinError as err:
                return self.async_abort(reason=_error_key(err))
            current = self.config_entry.options.get(CONF_FEATURES, DEFAULT_FEATURES)
            return self._show_features(list(current))
        capable = self._capable()
        return self.async_create_entry(
            data={
                CONF_FEATURES: [
                    f for f in user_input.get(CONF_FEATURES, []) if f in capable
                ],
                CONF_KNOWN_FEATURES: ALL_FEATURES,
            }
        )

    async def async_step_permissions(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the features to size the key for, and optionally a root key."""
        errors: dict[str, str] = {}
        key_id = key_id_of(self.config_entry.data[CONF_API_KEY])
        if user_input is not None:
            self._target = list(user_input.get(CONF_FEATURES, []))
            self._required = required_actions(self._target)
            root_key = (user_input.get(CONF_ROOT_API_KEY) or "").strip()
            try:
                errors = await self._check_permissions(key_id, root_key)
            except PangolinError as err:
                errors = {"base": _error_key(err)}
            if not errors:
                return await self.async_step_permissions_result()

        schema = vol.Schema(
            {
                vol.Optional(CONF_FEATURES): SelectSelector(
                    SelectSelectorConfig(
                        options=ALL_FEATURES,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                        translation_key="feature",
                    )
                ),
                vol.Optional(CONF_ROOT_API_KEY): PASSWORD_SELECTOR,
            }
        )
        current = self.config_entry.options.get(CONF_FEATURES, DEFAULT_FEATURES)
        return self.async_show_form(
            step_id="permissions",
            data_schema=self.add_suggested_values_to_schema(
                schema, {CONF_FEATURES: list(current)}
            ),
            description_placeholders={"key_id": key_id or "unknown"},
            errors=errors,
        )

    async def _check_permissions(
        self, key_id: str | None, root_key: str
    ) -> dict[str, str]:
        """Work out what can be reported or changed; returns form errors."""
        data = self.config_entry.data
        required = _action_lines(self._required)

        if await _client(self.hass, data).is_root_key():
            # The integration itself runs on a root key: the least-privilege
            # fix is a new org key, which this key is allowed to create.
            self._mode = "root_in_use"
            self._admin = _client(self.hass, data)
            self._summary = (
                "The integration is using a **root** API key, which can do "
                "anything in every organization.\n\nAn organization key needs "
                f"only:\n{required}"
            )
            return {}

        if not root_key:
            self._mode = "list_only"
            self._summary = (
                f"Grant this key these permissions in Pangolin:\n{required}\n\n"
                "Pangolin only lets root keys read a key's permissions, so they "
                "were not compared. Go back and add a root key to compare them "
                "and have them adjusted for you."
            )
            return {}

        if key_id is None:
            return {"base": "key_format"}
        admin = _client(self.hass, {**data, CONF_API_KEY: root_key})
        try:
            current = await admin.list_key_actions(key_id)
        except PangolinAuthError as err:
            return {
                CONF_ROOT_API_KEY: "root_invalid" if err.status == 401 else "not_root"
            }
        except PangolinNotFoundError:
            return {"base": "key_not_found"}

        missing = [a for a in self._required if a not in current]
        extra = sorted(a for a in current if a not in self._required)
        granted = [a for a in self._required if a in current]
        self._admin = admin
        self._mode = "compare" if (missing or extra) else "exact"
        parts = [f"Needed and already granted:\n{_plain_list(granted) or '- (none)'}"]
        if missing:
            parts.append(f"**Missing** (will be added):\n{_action_lines(missing)}")
        if extra:
            parts.append(
                f"**Not needed** (will be removed):\n{_plain_list(extra)}\n\n"
                "If you also use this key for something else, removing these "
                "will break that."
            )
        if not (missing or extra):
            parts.append("This key already has exactly what it needs.")
        self._summary = "\n\n".join(parts)
        return {}

    async def async_step_permissions_result(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the findings and, where possible, offer to apply them."""
        can_apply = self._mode in ("compare", "root_in_use")
        errors: dict[str, str] = {}
        if user_input is not None:
            if not (can_apply and user_input.get(CONF_APPLY)):
                return self.async_abort(reason="no_changes")
            try:
                await self._apply()
            except PangolinAuthError as err:
                errors["base"] = "apply_denied" if err.status == 403 else "invalid_auth"
            except PangolinError as err:
                errors["base"] = _error_key(err)
            else:
                return self.async_create_entry(
                    data={
                        CONF_FEATURES: self._target,
                        CONF_KNOWN_FEATURES: ALL_FEATURES,
                    }
                )

        schema = (
            vol.Schema({vol.Optional(CONF_APPLY, default=False): bool})
            if can_apply
            else vol.Schema({})
        )
        return self.async_show_form(
            step_id=f"permissions_{self._mode}",
            data_schema=schema,
            description_placeholders={"summary": self._summary},
            errors=errors,
            last_step=True,
        )

    # One step id per outcome so each gets its own title and apply label.
    async def async_step_permissions_compare(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_permissions_result(user_input)

    async def async_step_permissions_exact(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_permissions_result(user_input)

    async def async_step_permissions_list_only(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_permissions_result(user_input)

    async def async_step_permissions_root_in_use(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_permissions_result(user_input)

    async def _apply(self) -> None:
        if self._admin is None:
            raise PangolinError("No key available to make the change")
        data = self.config_entry.data
        if self._mode == "compare":
            key_id = key_id_of(data[CONF_API_KEY])
            if key_id is None:
                raise PangolinError("The integration's key has no ID part")
            await self._admin.set_key_actions(key_id, self._required)
            return
        # root_in_use: make a least-privilege org key and switch to it.
        new_key = await self._admin.create_org_key(NEW_KEY_NAME)
        new_id = key_id_of(new_key)
        if new_id is None:
            raise PangolinError("Pangolin returned a key without an ID")
        await self._admin.set_key_actions(new_id, self._required)
        await _client(self.hass, {**data, CONF_API_KEY: new_key}).get_org()
        self.hass.config_entries.async_update_entry(
            self.config_entry, data={**data, CONF_API_KEY: new_key}
        )
