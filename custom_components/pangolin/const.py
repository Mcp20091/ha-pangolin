"""Constants for the Pangolin integration."""

from collections.abc import Iterable, Mapping
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
FEATURE_CLIENT_STATUS = "client_status"
FEATURE_CLIENT_CONTROL = "client_control"
FEATURE_CLIENT_DELETE = "client_delete"
FEATURE_RESET_BANDWIDTH = "reset_bandwidth"
FEATURE_CLIENT_LAST_SEEN = "client_last_seen"
ALL_FEATURES = [
    FEATURE_PUBLIC_STATUS,
    FEATURE_PUBLIC_CONTROL,
    FEATURE_PRIVATE_STATUS,
    FEATURE_PRIVATE_CONTROL,
    FEATURE_SITE_RESTART,
    FEATURE_SITE_TRAFFIC,
    FEATURE_CLIENT_STATUS,
    FEATURE_CLIENT_CONTROL,
    FEATURE_CLIENT_DELETE,
    FEATURE_RESET_BANDWIDTH,
    FEATURE_CLIENT_LAST_SEEN,
]
# Features that existed before v0.6.0. Entries saved without a known-features
# list have seen exactly these, so anything newer gets announced.
LEGACY_FEATURES = [
    FEATURE_PUBLIC_STATUS,
    FEATURE_PUBLIC_CONTROL,
    FEATURE_PRIVATE_STATUS,
    FEATURE_PRIVATE_CONTROL,
    FEATURE_SITE_RESTART,
    FEATURE_SITE_TRAFFIC,
]
# Stored beside the chosen features: every feature the user has been offered.
CONF_KNOWN_FEATURES = "known_features"
# Unticked until the user opts in: permanent actions, site restart (most
# Pangolin versions don't allow it for API keys) and experimental features.
DEFAULT_OFF_FEATURES = {
    FEATURE_CLIENT_DELETE,
    FEATURE_SITE_RESTART,
    FEATURE_CLIENT_LAST_SEEN,
}
DEFAULT_FEATURES = [f for f in ALL_FEATURES if f not in DEFAULT_OFF_FEATURES]

# Pangolin API key permissions (action IDs) each feature needs.
BASE_ACTIONS = ["getOrg", "listSites"]
FEATURE_ACTIONS = {
    FEATURE_PUBLIC_STATUS: ["listResources"],
    FEATURE_PUBLIC_CONTROL: ["listResources", "updateResource"],
    FEATURE_PRIVATE_STATUS: ["listSiteResources"],
    FEATURE_PRIVATE_CONTROL: ["listSiteResources", "updateSiteResource"],
    FEATURE_SITE_RESTART: ["restartSite"],
    FEATURE_SITE_TRAFFIC: [],
    FEATURE_CLIENT_STATUS: ["listClients"],
    FEATURE_CLIENT_CONTROL: [
        "listClients",
        "blockClient",
        "unblockClient",
        "archiveClient",
        "unarchiveClient",
    ],
    FEATURE_CLIENT_DELETE: ["listClients", "deleteClient"],
    FEATURE_RESET_BANDWIDTH: ["resetSiteBandwidth"],
    FEATURE_CLIENT_LAST_SEEN: ["listClients"],
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
    "listClients": ("List Clients", "clients and their status"),
    "blockClient": ("Block Client", "client Blocked switches"),
    "unblockClient": ("Unblock Client", "client Blocked switches"),
    "archiveClient": ("Archive Client", "client Archived switches"),
    "unarchiveClient": ("Unarchive Client", "client Archived switches"),
    "deleteClient": ("Delete Client", "Delete buttons on machine clients"),
    "resetSiteBandwidth": (
        "Reset Organization Bandwidth",
        "the Reset bandwidth button",
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
OPT_CLIENTS = "clients"
OPT_CLIENT_DELETE = "client_delete"
OPT_RESET_BANDWIDTH = "reset_bandwidth"
OPT_CLIENT_LAST_SEEN = "client_last_seen"

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
        # Delete buttons and last seen live on client devices, so they bring
        # status along.
        OPT_CLIENTS: _level(
            f
            | (
                {FEATURE_CLIENT_STATUS}
                if f & {FEATURE_CLIENT_DELETE, FEATURE_CLIENT_LAST_SEEN}
                else set()
            ),
            FEATURE_CLIENT_STATUS,
            FEATURE_CLIENT_CONTROL,
        ),
        OPT_CLIENT_DELETE: FEATURE_CLIENT_DELETE in f,
        OPT_RESET_BANDWIDTH: FEATURE_RESET_BANDWIDTH in f,
        OPT_CLIENT_LAST_SEEN: FEATURE_CLIENT_LAST_SEEN in f,
    }

# Features that only work when the key can read the matching list.
FEATURE_NEEDS = {
    FEATURE_PUBLIC_STATUS: OPT_PUBLIC,
    FEATURE_PUBLIC_CONTROL: OPT_PUBLIC,
    FEATURE_PRIVATE_STATUS: OPT_PRIVATE,
    FEATURE_PRIVATE_CONTROL: OPT_PRIVATE,
    FEATURE_CLIENT_STATUS: OPT_CLIENTS,
    FEATURE_CLIENT_CONTROL: OPT_CLIENTS,
    FEATURE_CLIENT_DELETE: OPT_CLIENTS,
    FEATURE_CLIENT_LAST_SEEN: OPT_CLIENTS,
}


def known_features(options: Mapping[str, Any]) -> list[str]:
    """Features this entry has already been offered."""
    if CONF_KNOWN_FEATURES in options:
        return list(options[CONF_KNOWN_FEATURES])
    # Chose features before this list existed: they saw the pre-0.6.0 set.
    # No options at all predates feature selection, so there's nothing to add.
    return list(LEGACY_FEATURES) if CONF_FEATURES in options else list(ALL_FEATURES)
