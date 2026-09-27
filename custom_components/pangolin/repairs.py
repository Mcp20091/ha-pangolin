"""Repairs: let users turn on features added by an update."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.repairs import RepairsFlow
from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import PangolinClient, PangolinError
from .const import (
    ACTION_INFO,
    ALL_FEATURES,
    BASE_ACTIONS,
    CONF_FEATURES,
    CONF_KNOWN_FEATURES,
    CONF_ORG_ID,
    DEFAULT_OFF_FEATURES,
    FEATURE_NEEDS,
    known_features,
    required_actions,
)


class NewFeaturesFlow(RepairsFlow):
    """Offer the features an update added, then save the user's choice."""

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id
        self._offered: list[str] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return self.async_abort(reason="entry_removed")

        if user_input is not None:
            chosen = [f for f in user_input.get(CONF_FEATURES, []) if f in self._offered]
            current = list(entry.options.get(CONF_FEATURES, []))
            self.hass.config_entries.async_update_entry(
                entry,
                options={
                    **entry.options,
                    CONF_FEATURES: current + [f for f in chosen if f not in current],
                    CONF_KNOWN_FEATURES: ALL_FEATURES,
                },
            )
            # Saving reloads the entry, which clears this notice.
            return self.async_create_entry(data={})

        known = known_features(entry.options)
        new = [f for f in ALL_FEATURES if f not in known]
        data = entry.data
        client = PangolinClient(
            async_get_clientsession(
                self.hass, verify_ssl=data.get(CONF_VERIFY_SSL, True)
            ),
            data[CONF_URL],
            data[CONF_API_KEY],
            data[CONF_ORG_ID],
            data.get(CONF_VERIFY_SSL, True),
        )
        try:
            access = await client.probe_access()
        except PangolinError:
            return self.async_abort(reason="cannot_connect")
        self._offered = [
            f for f in new if f not in FEATURE_NEEDS or access[FEATURE_NEEDS[f]]
        ]
        hidden = len(new) - len(self._offered)
        extra = [a for a in required_actions(new) if a not in BASE_ACTIONS]
        schema = vol.Schema(
            {
                vol.Optional(CONF_FEATURES): SelectSelector(
                    SelectSelectorConfig(
                        options=self._offered,
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                        translation_key="feature",
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="confirm",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {
                    CONF_FEATURES: [
                        f for f in self._offered if f not in DEFAULT_OFF_FEATURES
                    ]
                },
            ),
            description_placeholders={
                "title": entry.title,
                "permissions": "\n".join(
                    f"- {ACTION_INFO[a][0]}: {ACTION_INFO[a][1]}" for a in extra
                ),
                "hidden": (
                    f"{hidden} more can't be offered because this key can't read "
                    "what they need. Grant the permissions below, then use "
                    "Configure > Choose features."
                    if hidden
                    else "All of them work with this key's read access."
                ),
            },
        )


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Create the flow behind the notice's Fix button."""
    # A missing entry ID just makes the flow abort as "entry removed".
    return NewFeaturesFlow(str((data or {}).get("entry_id", "")))
