"""Constants for the Pangolin integration."""

from collections.abc import Iterable
from datetime import timedelta
from typing import Any

DOMAIN = "pangolin"

CONF_ORG_ID = "org_id"

DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)
PAGE_SIZE = 100

# Features the user ticks during setup or under Configure (stored in options).
CONF_FEATURES = "features"
FEATURE_PUBLIC_STATUS = "public_status"
FEATURE_PUBLIC_CONTROL = "public_control"
FEATURE_PRIVATE_STATUS = "private_status"
FEATURE_PRIVATE_CONTROL = "private_control"
FEATURE_SITE_RESTART = "site_restart"
FEATURE_SITE_TRAFFIC = "site_traffic"
ALL_FEATURES = [
    FEATURE_PUBLIC_STATUS,
    FEATURE_PUBLIC_CONTROL,
    FEATURE_PRIVATE_STATUS,
    FEATURE_PRIVATE_CONTROL,
    FEATURE_SITE_RESTART,
    FEATURE_SITE_TRAFFIC,
]

# Pangolin API key permissions (action IDs) each feature needs.
BASE_ACTIONS = ["getOrg", "listSites"]
FEATURE_ACTIONS = {
    FEATURE_PUBLIC_STATUS: ["listResources"],
    FEATURE_PUBLIC_CONTROL: ["listResources", "updateResource"],
    FEATURE_PRIVATE_STATUS: ["listSiteResources"],
    FEATURE_PRIVATE_CONTROL: ["listSiteResources", "updateSiteResource"],
    FEATURE_SITE_RESTART: ["restartSite"],
    FEATURE_SITE_TRAFFIC: [],
}
# Labels as the Pangolin dashboard shows them, plus what each is used for.
ACTION_INFO = {
    "getOrg": ("Get Organization", "checking the key during setup"),
    "listSites": ("List Sites", "sites and their status"),
    "listResources": ("List Resources", "public resource status"),
    "updateResource": ("Update Resource", "public resource switches"),
    "listSiteResources": ("List Site Resources", "private resource status"),
    "updateSiteResource": ("Update Site Resource", "private resource switches"),
    "restartSite": (
        "Restart Site",
        "restart buttons (not listed in the dashboard's key editor; some "
        "Pangolin versions don't allow it for API keys at all)",
    ),
}


def required_actions(features: Iterable[str]) -> list[str]:
    """Smallest permission set for these features, in a stable order."""
    needed = set(BASE_ACTIONS)
    for feature in features:
        needed.update(FEATURE_ACTIONS.get(feature, []))
    return [a for a in ACTION_INFO if a in needed]


# Resolved view of the ticked features used by the platforms.
OPT_PUBLIC = "public_resources"
OPT_PRIVATE = "private_resources"
OPT_RESTART = "site_restart"
OPT_TRAFFIC = "site_traffic"

LEVEL_OFF = "off"
LEVEL_STATUS = "status"
LEVEL_CONTROL = "control"


def _level(features: set[str], status: str, control: str) -> str:
    # A switch already shows the enabled state, so control implies status.
    if control in features:
        return LEVEL_CONTROL
    if status in features:
        return LEVEL_STATUS
    return LEVEL_OFF


def resolve_features(features: Iterable[str]) -> dict[str, Any]:
    """Turn a list of ticked features into per-area settings."""
    f = set(features)
    return {
        OPT_PUBLIC: _level(f, FEATURE_PUBLIC_STATUS, FEATURE_PUBLIC_CONTROL),
        OPT_PRIVATE: _level(f, FEATURE_PRIVATE_STATUS, FEATURE_PRIVATE_CONTROL),
        OPT_RESTART: FEATURE_SITE_RESTART in f,
        OPT_TRAFFIC: FEATURE_SITE_TRAFFIC in f,
    }
