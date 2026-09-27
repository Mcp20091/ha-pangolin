# AGENTS.md

Notes for AI coding agents and human contributors working on this repo. Read this before changing anything. For setup and test commands, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Keep this file current

This file is only useful if it's accurate. If you notice anything here that's wrong, outdated or missing, update this file in the same change, or say so in your PR or issue if you can't. That includes Pangolin API behavior that changed upstream, a renamed file, a new gotcha, or a convention that no longer holds.

AI agents: when your work shows this file needs changing, suggest or make the edit to AGENTS.md rather than working around the stale note silently.

## What this is

A Home Assistant custom integration (domain `pangolin`, installed through HACS) for the [Pangolin](https://github.com/fosrl/pangolin) Integration API. It polls every 30 s and exposes:

- Sites: online sensor, restart button, data in/out sensors
- Public resources: health sensor, enable/disable switch
- Private resources: enable/disable switch
- Clients (machine clients and user devices): online sensor, data in/out, blocked/archived switches, opt-in delete button
- An org hub device with a "Sites online" sensor listing every site, an "API reachable" sensor and a "Reset bandwidth" button

It's unofficial and AI-written, and it hasn't had a line-by-line human review. Keep the README's "AI-written (vibe coded)" disclaimer accurate, and keep the credits.

## Layout

| File | Role |
| --- | --- |
| `custom_components/pangolin/api.py` | Async aiohttp client. Unwraps the `{data, success, error, message, status}` envelope and maps HTTP errors to `PangolinAuthError` (keeps `.status`, 401 or 403), `PangolinNotFoundError` (404) and `PangolinConnectionError`. |
| `coordinator.py` | `DataUpdateCoordinator`. Builds `PangolinData(sites, resources, private_resources, clients)` keyed by ID. Tracks `api_reachable` (it pings only after a failed update). `get_options()` resolves the stored feature list. |
| `config_flow.py` | Setup: connect, then org, then features. Reconfigure: URL, SSL check, optional new key. Options: a menu with features or the permission check. |
| `entity.py` | Base entities (org, site, public resource, private resource) and `add_entities_dynamically()`, which adds entities for new IDs on each refresh. |
| `binary_sensor.py`, `sensor.py`, `switch.py`, `button.py` | Platforms. Each checks `entry.runtime_data.options` to decide what to create. |
| `const.py` | Feature keys, `resolve_features()`, and the permission map (`FEATURE_ACTIONS`, `ACTION_INFO`, `required_actions()`). |
| `__init__.py` | Setup, reload on options change, `_remove_disabled_features()` registry cleanup, and `async_remove_config_entry_device()` (lets users delete devices whose object is gone from Pangolin). |
| `repairs.py` | Fix flow for the "new features available" Repairs notice raised in `__init__.py`. |
| `diagnostics.py` | Diagnostics download. `TO_REDACT` removes keys, URLs, domains, names, addresses and user details. Add any new identifying field to it. |
| `strings.json` / `translations/en.json` | UI text. Keep them **byte-identical**. |
| `icons.json` | State-aware MDI icons, keyed by translation key |
| `brand/` | `icon.png` 256 px, `icon@2x.png` 512 px, `logo.png`, `dark_logo.png`. HA 2026.x serves these directly from custom integrations. They're derived from Pangolin's own logo files. |

## Pangolin API facts (verified against source; recheck when upgrading)

- **Setup docs:** https://docs.pangolin.net/self-host/advanced/integration-api (enabling the API, config flag, routing).
- **Base URL** ends in `/v1`. The server hosts Swagger at `/v1/docs` and the spec at `/v1/openapi.json`. The spec's response schemas are generic (`data: object`), so field names come from the route handlers in `fosrl/pangolin/server/routers/**`. Route guards (which permission each endpoint needs) are in `server/routers/integration.ts`.
- **Key format:** `<apiKeyId>.<secret>`, sent as `Authorization: Bearer <key>`. `key_id_of()` pulls out the ID.
- **Status codes:** 401 means the key is bad. 403 means the key is valid but lacks the permission, or isn't root for root-only routes.
- **Root-only routes:** `GET /orgs` and all API key management (`/org/{orgId}/api-keys`, `/org/{orgId}/api-key/{id}/actions` GET/POST, `PUT /org/{orgId}/api-key`). Org keys can't list orgs or see their own permissions. That's why setup falls back to typing the org ID, and why the permission check asks for a root key.
- `GET /orgs` has a strict query schema that takes only `limit` and `offset`. Don't send `pageSize`.
- **Lists:** `/org/{orgId}/sites` returns `data.sites` and `/org/{orgId}/resources` returns `data.resources`. They page with `page`/`pageSize`, and `data.pagination.total` gives the total.
- **Private resources:** `GET /org/{orgId}/private-resources` returns `data.siteResources` with `siteResourceId`, `name`, `niceId`, `mode`, `destination`, `alias`, `enabled`, `siteNames`, `siteIds`. They're updated with `POST /private-resource/{id}` and `{"enabled": bool}`. `/site-resources` and `/site-resource/{id}` are the legacy aliases.
- **Public resources:** updated with `POST /resource/{id}` and `{"enabled": bool}`. `/public-resource/{id}` is the newer alias.
- **Health values:** `healthy`, `degraded`, `offline`, `unknown`. Older builds said `unhealthy`, which is mapped to `offline`.
- **Site restart:** `POST /site/{siteId}/restart` returns `data: null`. It's in the OpenAPI spec, but on current `main` it's only registered on the dashboard router, not the integration router. The permission (`restartSite`) also isn't offered in the dashboard's key editor. Expect 404 for API keys, and keep the friendly error in `button.py`.
- **Permission (action) IDs** and dashboard labels: `getOrg` Get Organization, `listSites` List Sites, `listResources` List Resources, `updateResource` Update Resource, `listSiteResources` List Site Resources, `updateSiteResource` Update Site Resource, `restartSite` (no dashboard label). Key management needs `listApiKeyActions`, `setApiKeyActions` and `createApiKey`. `POST .../actions` **replaces** the whole set, and `actionIds` must be non-empty.
- **Two kinds of API keys:** org keys (org Settings > API Keys) and root keys (Server Admin > API Keys). The dashboard never offers key-management permissions for org keys, so users with "everything ticked" on an org key still get 403 on key routes. Don't confuse either with **AI Gateway virtual API keys** (`/virtual-api-key...`), which are for the AI gateway and can't call the Integration API.
- **Clients:** machine clients come from `GET /org/{orgId}/clients` (`data.clients`, only clients without a `userId`). User devices come from `GET /org/{orgId}/user-devices` (`data.devices`). Both need `listClients`, share the `clientId` namespace, and **hide blocked and archived clients unless `status` asks for them**, as a comma-separated list: clients take `active,blocked,archived`, and user devices also accept `pending,denied`. Actions: `POST /client/{id}/block|unblock|archive|unarchive`, and `DELETE /client/{id}` (permanent). **Delete only works for machine clients.** A client with a `userId` (every user device) returns 400 "Cannot delete a user client. User clients must be archived instead.", whether or not it's archived. That's why `button.py` only creates Delete for `kind == "machine"`. Permission IDs: `blockClient`, `unblockClient`, `archiveClient`, `unarchiveClient`, `deleteClient`.
- **Last seen:** user devices (not machine clients) include `firstSeen`/`lastSeen` as **Unix seconds** from the device fingerprint. Pangolin refreshes them on every client ping and at registration (`handleOlmPingMessage`, `handleOlmRegisterMessage`), so `lastSeen` is live activity. `PangolinClientLastSeen` publishes it in 5-minute steps (`LAST_SEEN_STEP`) to avoid recorder churn. It's the experimental `client_last_seen` feature, off by default. Label experimental features "(experimental, off by default)" and put them in `DEFAULT_OFF_FEATURES`.
- **Uptime history:** Pangolin computes per-day uptime for sites and resources (`/site/{id}/status-history`, `/resource/{id}/status-history`), but those routes are dashboard-only (`server/routers/external.ts`), not on the integration router. Use Home Assistant's History stats helper on the Online sensors instead.
- **Reset bandwidth:** `POST /org/{orgId}/reset-bandwidth` zeroes every site's `megabytesIn`/`megabytesOut`. Permission `resetSiteBandwidth`, labelled "Reset Organization Bandwidth". Traffic sensors are `TOTAL_INCREASING`, so HA handles the reset.
- **Health check:** `GET /v1/` needs no auth and returns `{"message": "Healthy"}`, not the usual envelope. Use `PangolinClient.ping()`, not `_request()`.
- **Not available to API keys:** site approve/reject, and site restart (see above). Health checks, access logs and certificates are only on the Enterprise router (`server/private/routers/integration.ts`).
- `PUT /org/{orgId}/api-key` with `{name}` returns `apiKeyId` and `apiKey` (the secret). The full key is `f"{apiKeyId}.{apiKey}"`. New keys start with no permissions.

## Home Assistant conventions used here

- `ConfigEntry.runtime_data` holds the coordinator. Entities use `has_entity_name` and `translation_key`, with names in `strings.json` and icons in `icons.json`.
- **Unique IDs:** `{entry_id}_org_{key}`, `{entry_id}_site_{siteId}_{key}`, `{entry_id}_resource_{resourceId}_{key}`, `{entry_id}_private_{siteResourceId}_{key}`, `{entry_id}_client_{clientId}_{key}`. Device identifiers follow the same pattern without `_{key}`. **`_remove_disabled_features()` matches on `_client_` (checked first, because client data sensors and buttons share suffixes with sites), `_resource_`, `_private_`, `_org_reset_bandwidth` and the `_data_in`/`_data_out` suffixes**, and `async_remove_config_entry_device()` parses the same identifiers. Update both if you change these formats. Changing unique IDs orphans users' entities.
- **Options** are stored as `{"features": [...]}`. A missing key means `DEFAULT_FEATURES` (everything except `DEFAULT_OFF_FEATURES`: client delete, because it's permanent, and site restart, because API keys usually can't call it). New features are off for existing entries until the user ticks them. Permanent actions go in `DEFAULT_OFF_FEATURES`. Client delete implies client status, because the button lives on the client device. `resolve_features()` turns the list into per-area levels (`off`/`status`/`control`). Control implies status: a switch replaces the read-only "Enabled" binary sensor.
- Public and private resource devices use `entry_type=DeviceEntryType.SERVICE`, so the device list shows them with Home Assistant's service icon. Sites and the org stay normal devices. That icon is the only per-device visual an integration can influence.
- **Adding a feature:** add it to `ALL_FEATURES`, and to `FEATURE_ACTIONS`, `FEATURE_NEEDS` (if it depends on a readable list) and the `feature` selector strings. Existing entries store `known_features` (every feature they've been offered). On setup, `_update_new_features_issue()` raises a fixable Repairs issue listing anything newer, and `repairs.py` lets the user opt in. **Never edit `LEGACY_FEATURES`**: it defines what pre-0.6.0 entries had already seen. Every options/config flow that saves features must also save `known_features: ALL_FEATURES`.
- Actions use `entity.run_action()`, which turns a 403 into "the API key needs the X permission".
- Private resources and clients are optional at runtime. A 403 or 404 on the list turns them off for that session with a warning, instead of breaking setup or forcing re-authentication.
- **Never store the root key** entered in the permission check. It stays on the flow instance only. A test asserts this.

## Staying current with Home Assistant

Home Assistant deprecates and removes developer APIs regularly, and this integration has to keep up.

- **Before changing code**, skim recent posts on the [Home Assistant developer blog](https://developers.home-assistant.io/blog). Every deprecation and breaking change for integrations is announced there, with the version it takes effect in. It's far easier to follow than core's commit history. For a specific helper, check its current source in `home-assistant/core` rather than relying on memory.
- **Run the tests against the latest release.** `requirements_test.txt` is unpinned, so CI installs the newest `pytest-homeassistant-custom-component` and Home Assistant on every run. Deprecated calls often fail there as errors (for example, `device_registry.async_get_device` raises in 2026.x). Treat deprecation warnings in test output as work to do, not noise.
- Keep `hacs.json`'s minimum `homeassistant` version honest if you start relying on newer features.
- If you find a deprecation that affects this code, fix it and note it here.

## Validation gotchas (hassfest)

- UI strings may not contain URLs or anything that looks like HTML (`<id>` fails). Use placeholders or plain words.
- Every `translation_key` used in code needs an entry in `strings.json`. Every icon must be a real MDI name; check them at `https://cdn.jsdelivr.net/npm/@mdi/svg/svg/<name>.svg`.
- Menu steps need `menu_options` labels. Each form `step_id` needs its own `strings.json` entry.

## Testing

- `pytest -q` (see CONTRIBUTING.md). Doesn't work on native Windows; use WSL.
- Fake the API with `aioclient_mock`. Its matching ignores headers, so the same URL mock serves both the integration's key and a root key. Assert headers through `mock_calls[i][3]` when it matters.
- Match any new endpoint's mock to the real response shape documented above.

## Releasing and commits

- Bump `manifest.json` `version`, push to `main` with CI green, then run `gh release create vX.Y.Z`. HACS follows releases.
- Keep entity IDs and unique IDs stable across releases. Users update in place.
- Commits made with an AI agent should credit it with a `Co-Authored-By` trailer.
