from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pangolin.const import (
    ALL_FEATURES,
    CONF_ORG_ID,
    DEFAULT_FEATURES,
    DOMAIN,
)

BASE = "https://api.example.com/v1"


def ok(data):
    return {"data": data, "success": True, "error": False, "message": "", "status": 200}


HOME = {"orgId": "home", "name": "Home"}


MACHINE = {"clientId": 11, "name": "Backup box", "niceId": "backup", "type": "olm",
           "online": True, "blocked": False, "archived": False, "olmVersion": "1.2.0",
           "megabytesIn": 5.0, "megabytesOut": 1.5, "subnet": "100.90.128.4/32"}
LAPTOP = {"clientId": 12, "name": "Laptop", "niceId": "laptop", "online": False,
          "firstSeen": 1790000000, "lastSeen": 1790467200,
          "blocked": True, "archived": False, "olmVersion": "1.3.0",
          "username": "alex", "userEmail": "alex@example.com", "deviceModel": "ThinkPad",
          "megabytesIn": 0, "megabytesOut": 0, "fingerprintPlatform": "windows",
          "fingerprintOsVersion": "11", "fingerprintArch": "x64", "agent": "Pangolin Windows",
          "userType": "internal", "fingerprintHostname": "LAPTOP-SECRET",
          "fingerprintSerialNumber": "SN-SECRET"}


def mock_api(aioclient_mock, enabled=True, health="healthy", private_status=200,
             orgs=(HOME,), orgs_status=200, clients_status=200, BASE=BASE, clear=True,
             block=False, maintenance=False, detail_status=200):
    if clear:
        aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/", json={"message": "Healthy"})
    aioclient_mock.get(
        f"{BASE}/org/home/clients", status=clients_status,
        json=ok({"clients": [MACHINE], "pagination": {"total": 1, "page": 1, "pageSize": 100}}),
    )
    aioclient_mock.get(
        f"{BASE}/org/home/user-devices",
        json=ok({"devices": [LAPTOP], "pagination": {"total": 1, "page": 1, "pageSize": 100}}),
    )
    for action in ("block", "unblock", "archive", "unarchive"):
        aioclient_mock.post(f"{BASE}/client/11/{action}", json=ok(None))
    aioclient_mock.delete(f"{BASE}/client/11", json=ok(None))
    aioclient_mock.post(f"{BASE}/org/home/reset-bandwidth", json=ok(None))
    aioclient_mock.get(
        f"{BASE}/orgs", status=orgs_status,
        json=ok({"orgs": list(orgs), "pagination": {"total": len(orgs), "limit": 1000, "offset": 0}}),
    )
    aioclient_mock.get(f"{BASE}/org/home", json=ok({"org": HOME}))
    aioclient_mock.get(f"{BASE}/org/other", status=403, json={"error": True})
    aioclient_mock.get(
        f"{BASE}/org/home/sites",
        json=ok({"sites": [{"siteId": 1, "name": "Proxmox", "niceId": "px", "type": "newt",
                            "online": True, "megabytesIn": 12.5, "megabytesOut": 3.0,
                            "newtVersion": "1.17.0", "agentVersion": "1.17.0",
                            "exitNodeName": "exit-1", "resourceCount": 1}],
                 "pagination": {"total": 1, "page": 1, "pageSize": 100}}),
    )
    aioclient_mock.get(
        f"{BASE}/org/home/resources",
        json=ok({"resources": [{"resourceId": 7, "name": "Home Assistant", "niceId": "ha",
                                "enabled": enabled, "health": health,
                                "fullDomain": "ha.example.com", "mode": "http", "ssl": True,
                                "sso": 1, "passwordId": None, "pincodeId": 4, "whitelist": 0,
                                "headerAuthId": None,
                                "sites": [{"siteId": 1, "siteName": "Proxmox", "online": True}],
                                "targets": [{"targetId": 9, "siteName": "Proxmox",
                                             "ip": "10.0.0.7", "port": 8123, "enabled": True,
                                             "hcEnabled": True, "healthStatus": "healthy"}]}],
                 "pagination": {"total": 1, "page": 1, "pageSize": 100}}),
    )
    aioclient_mock.get(
        f"{BASE}/org/home/private-resources",
        status=private_status,
        json=ok({"siteResources": [{"siteResourceId": 3, "name": "NAS", "niceId": "nas",
                                    "mode": "host", "destination": "10.0.0.5",
                                    "enabled": True, "siteNames": ["Proxmox"],
                                    "siteOnlines": [True], "aliasAddress": "100.96.1.1",
                                    "tcpPortRangeString": "*", "udpPortRangeString": "*",
                                    "disableIcmp": False}],
                 "pagination": {"total": 1, "page": 1, "pageSize": 100}}),
    )
    aioclient_mock.get(
        f"{BASE}/resource/7", status=detail_status,
        json=ok({"resourceId": 7, "blockAccess": block, "maintenanceModeEnabled": maintenance,
                 "maintenanceModeType": "forced"}),
    )
    aioclient_mock.post(f"{BASE}/resource/7", json=ok({"resourceId": 7}))
    aioclient_mock.post(f"{BASE}/private-resource/3", json=ok({"siteResourceId": 3}))
    aioclient_mock.post(f"{BASE}/site/1/restart", json=ok(None))


async def test_flow_and_entities(hass, aioclient_mock):
    mock_api(aioclient_mock)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: "https://api.example.com/", CONF_API_KEY: "id.secret", CONF_VERIFY_SSL: True},
    )
    # A root key that sees a single org skips straight to features.
    assert result["step_id"] == "features"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"features": ALL_FEATURES}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_URL] == BASE
    assert result["data"][CONF_ORG_ID] == "home"
    assert result["title"] == "Pangolin (Home)"
    assert result["options"]["features"] == ALL_FEATURES
    await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.pangolin_site_proxmox_online").state == "on"
    assert hass.states.get("sensor.pangolin_site_proxmox_data_in").state == "12.5"
    assert hass.states.get("sensor.pangolin_home_assistant_health").state == "healthy"
    sw = hass.states.get("switch.pangolin_home_assistant_enabled")
    assert sw.state == "on"
    assert sw.attributes["full_domain"] == "ha.example.com"

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.pangolin_home_assistant_enabled"}, blocking=True
    )
    posts = [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert str(posts[-1][1]).endswith("/resource/7")
    assert posts[-1][2] == {"enabled": False}
    auth = [c for c in aioclient_mock.mock_calls if c[0] == "POST"][-1][3]
    assert auth["Authorization"] == "Bearer id.secret"



async def test_legacy_unhealthy_maps_to_offline(hass, aioclient_mock):
    mock_api(aioclient_mock, health="unhealthy")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_URL: BASE, CONF_API_KEY: "k", CONF_ORG_ID: "home", CONF_VERIFY_SSL: True},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.pangolin_home_assistant_health").state == "offline"


async def start_flow(hass, url=BASE, key="k"):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: url, CONF_API_KEY: key, CONF_VERIFY_SSL: True}
    )


def field(result, name):
    for key in result["data_schema"].schema:
        if key == name:
            return key
    raise AssertionError(f"no {name} field")


async def test_bad_key(hass, aioclient_mock):
    mock_api(aioclient_mock, orgs_status=401)
    result = await start_flow(hass, key="bad")
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}
    # /v1 is shown beside the box, so the redisplayed value leaves it off.
    assert field(result, CONF_URL).description["suggested_value"] == "https://api.example.com"


async def test_url_box_shows_v1_suffix(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    url_selector = result["data_schema"].schema[field(result, CONF_URL)]
    assert url_selector.config["suffix"] == "/v1"


async def test_root_key_picks_org_from_list(hass, aioclient_mock):
    mock_api(aioclient_mock, orgs=({"orgId": "work", "name": "Work"}, HOME))
    result = await start_flow(hass)
    assert result["step_id"] == "org"
    options = result["data_schema"].schema[field(result, CONF_ORG_ID)].config["options"]
    assert options == [
        {"value": "home", "label": "Home (home)"},
        {"value": "work", "label": "Work (work)"},
    ]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ORG_ID: "home"})
    assert result["step_id"] == "features"


async def test_org_key_enters_org_id(hass, aioclient_mock):
    mock_api(aioclient_mock, orgs_status=403)
    result = await start_flow(hass)
    assert result["step_id"] == "org_manual"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ORG_ID: "other"})
    assert result["errors"] == {"base": "org_denied"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ORG_ID: " home "})
    assert result["step_id"] == "features"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"features": ALL_FEATURES})
    assert result["data"][CONF_ORG_ID] == "home"


async def test_pagination(hass, aioclient_mock):
    from custom_components.pangolin.api import PangolinClient
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    page1 = ok({"resources": [{"resourceId": i} for i in range(100)],
                "pagination": {"total": 150, "page": 1, "pageSize": 100}})
    page2 = ok({"resources": [{"resourceId": i} for i in range(100, 150)],
                "pagination": {"total": 150, "page": 2, "pageSize": 100}})
    aioclient_mock.get(f"{BASE}/org/home/resources", params={"page": 1, "pageSize": 100}, json=page1)
    aioclient_mock.get(f"{BASE}/org/home/resources", params={"page": 2, "pageSize": 100}, json=page2)
    client = PangolinClient(async_get_clientsession(hass), BASE, "k", "home")
    assert len(await client.list_resources()) == 150


async def setup_entry(hass, features=None, api_key="k"):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_URL: BASE, CONF_API_KEY: api_key, CONF_ORG_ID: "home", CONF_VERIFY_SSL: True},
        options={} if features is None else {"features": features},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_private_resource_switch(hass, aioclient_mock):
    mock_api(aioclient_mock)
    await setup_entry(hass)
    sw = hass.states.get("switch.pangolin_nas_enabled")
    assert sw.state == "on"
    assert sw.attributes["destination"] == "10.0.0.5"
    assert sw.attributes["sites"] == [{"name": "Proxmox", "online": True}]

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.pangolin_nas_enabled"}, blocking=True
    )
    posts = [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert str(posts[-1][1]).endswith("/private-resource/3")
    assert posts[-1][2] == {"enabled": False}


async def test_private_resources_optional(hass, aioclient_mock):
    mock_api(aioclient_mock, private_status=403)
    entry = await setup_entry(hass)
    assert entry.state.name == "LOADED"
    assert hass.states.get("switch.pangolin_home_assistant_enabled").state == "on"
    assert hass.states.get("switch.pangolin_nas_enabled") is None


async def test_restart_button_and_sites_list(hass, aioclient_mock):
    mock_api(aioclient_mock)
    await setup_entry(hass, features=["site_restart"])

    online = hass.states.get("sensor.pangolin_home_sites_online")
    assert online.state == "1"
    assert online.attributes["total"] == 1
    assert online.attributes["sites"][0]["name"] == "Proxmox"
    assert online.attributes["sites"][0]["online"] is True

    await hass.services.async_call(
        "button", "press", {"entity_id": "button.pangolin_site_proxmox_restart"}, blocking=True
    )
    posts = [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert str(posts[-1][1]).endswith("/site/1/restart")


async def test_restart_not_supported(hass, aioclient_mock):
    import pytest
    from homeassistant.exceptions import HomeAssistantError

    mock_api(aioclient_mock)
    await setup_entry(hass, features=["site_restart"])
    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{BASE}/site/1/restart", status=404, json={"error": True})
    with pytest.raises(HomeAssistantError, match="does not expose site restart"):
        await hass.services.async_call(
            "button", "press", {"entity_id": "button.pangolin_site_proxmox_restart"},
            blocking=True,
        )


def suggested_features(result):
    return field(result, "features").description["suggested_value"]


async def test_feature_step_detects_access(hass, aioclient_mock):
    import pytest
    from homeassistant.data_entry_flow import InvalidData

    mock_api(aioclient_mock, private_status=403)
    result = await start_flow(hass)
    assert result["step_id"] == "features"
    # Private features are hidden; client delete and site restart start unticked.
    assert suggested_features(result) == [
        "public_status", "public_control", "site_traffic",
        "client_status", "client_control", "reset_bandwidth", "public_block_access"]
    assert "Private" in result["description_placeholders"]["unavailable"]

    # Features the key can't use aren't accepted by the form.
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {"features": ["public_status", "private_control"]})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"features": ["public_status"]})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["features"] == ["public_status"]
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.pangolin_home_assistant_enabled").state == "on"
    assert hass.states.get("switch.pangolin_home_assistant_enabled") is None
    assert hass.states.get("button.pangolin_site_proxmox_restart") is None
    assert hass.states.get("sensor.pangolin_site_proxmox_data_in") is None


async def test_options_flow_removes_disabled_entities(hass, aioclient_mock):
    from homeassistant.helpers import entity_registry as er

    mock_api(aioclient_mock)
    entry = await setup_entry(hass)
    reg = er.async_get(hass)
    assert reg.async_get("switch.pangolin_nas_enabled")

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "features"})
    assert result["step_id"] == "features"
    assert suggested_features(result) == DEFAULT_FEATURES
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"features": ["public_status", "public_control", "private_status"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert reg.async_get("switch.pangolin_nas_enabled") is None
    assert hass.states.get("binary_sensor.pangolin_nas_enabled").state == "on"
    assert reg.async_get("button.pangolin_site_proxmox_restart") is None
    assert hass.states.get("switch.pangolin_home_assistant_enabled").state == "on"


async def open_permissions(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "permissions"})


async def test_permissions_list_only_without_root_key(hass, aioclient_mock):
    mock_api(aioclient_mock, orgs_status=403)
    entry = await setup_entry(hass, api_key="k1.secret")
    result = await open_permissions(hass, entry)
    assert result["step_id"] == "permissions"
    assert result["description_placeholders"] == {"key_id": "k1"}

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"features": ["public_control"]})
    assert result["step_id"] == "permissions_list_only"
    summary = result["description_placeholders"]["summary"]
    assert "Get Organization (`getOrg`)" in summary
    assert "Update Resource (`updateResource`)" in summary
    assert "listSiteResources" not in summary

    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_changes"


async def test_permissions_trim_and_add_with_root_key(hass, aioclient_mock):
    mock_api(aioclient_mock, orgs_status=403)
    aioclient_mock.get(
        f"{BASE}/org/home/api-key/k1/actions",
        json=ok({"actions": [{"actionId": a} for a in
                             ("getOrg", "listSites", "listResources", "deleteSite")],
                 "pagination": {"total": 4, "limit": 1000, "offset": 0}}),
    )
    aioclient_mock.post(f"{BASE}/org/home/api-key/k1/actions", json=ok({}))
    entry = await setup_entry(hass, api_key="k1.secret")
    result = await open_permissions(hass, entry)

    # Size for public switches: updateResource is missing, deleteSite is extra.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"features": ["public_status", "public_control"], "root_api_key": "root.key"})
    assert result["step_id"] == "permissions_compare"
    summary = result["description_placeholders"]["summary"]
    assert "**Missing** (will be added):\n- Update Resource" in summary
    assert "**Not needed** (will be removed):\n- deleteSite" in summary

    # Nothing happens unless the risk box is ticked.
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"apply": False})
    assert result2["reason"] == "no_changes"

    result = await open_permissions(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"features": ["public_status", "public_control"], "root_api_key": "root.key"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"apply": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    posts = [c for c in aioclient_mock.mock_calls
             if c[0] == "POST" and str(c[1]).endswith("/api-key/k1/actions")]
    assert posts[-1][2] == {"actionIds": ["getOrg", "listSites", "listResources", "updateResource"]}
    assert posts[-1][3]["Authorization"] == "Bearer root.key"
    await hass.async_block_till_done()
    assert entry.options["features"] == ["public_status", "public_control"]
    # The root key is never stored.
    assert "root.key" not in str(entry.data) and "root.key" not in str(entry.options)


async def test_permissions_rejects_non_root_key(hass, aioclient_mock):
    mock_api(aioclient_mock, orgs_status=403)
    aioclient_mock.get(f"{BASE}/org/home/api-key/k1/actions", status=403, json={"error": True})
    entry = await setup_entry(hass, api_key="k1.secret")
    result = await open_permissions(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"features": ALL_FEATURES, "root_api_key": "org.key"})
    assert result["step_id"] == "permissions"
    assert result["errors"] == {"root_api_key": "not_root"}


async def test_permissions_replaces_root_key_in_use(hass, aioclient_mock):
    mock_api(aioclient_mock)  # /orgs answers, so the configured key is root
    aioclient_mock.put(
        f"{BASE}/org/home/api-key",
        json=ok({"apiKeyId": "new1", "apiKey": "fresh", "name": "x", "lastChars": "resh"}),
    )
    aioclient_mock.post(f"{BASE}/org/home/api-key/new1/actions", json=ok({}))
    entry = await setup_entry(hass, api_key="root1.secret")
    result = await open_permissions(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"features": ["public_status"]})
    assert result["step_id"] == "permissions_root_in_use"
    assert "**root** API key" in result["description_placeholders"]["summary"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"apply": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    posts = [c for c in aioclient_mock.mock_calls
             if c[0] == "POST" and str(c[1]).endswith("/api-key/new1/actions")]
    assert posts[-1][2] == {"actionIds": ["getOrg", "listSites", "listResources"]}
    await hass.async_block_till_done()
    assert entry.data[CONF_API_KEY] == "new1.fresh"


async def test_resources_are_service_devices(hass, aioclient_mock):
    from homeassistant.helpers import device_registry as dr, entity_registry as er

    mock_api(aioclient_mock)
    await setup_entry(hass)
    ent_reg, dev_reg = er.async_get(hass), dr.async_get(hass)

    def device_of(entity_id):
        return dev_reg.async_get(ent_reg.async_get(entity_id).device_id)

    service = dr.DeviceEntryType.SERVICE
    assert device_of("switch.pangolin_home_assistant_enabled").entry_type is service
    assert device_of("switch.pangolin_nas_enabled").entry_type is service
    assert device_of("binary_sensor.pangolin_site_proxmox_online").entry_type is None



def entity_ids(hass, domain):
    return sorted(e for e in hass.states.async_entity_ids(domain) if "pangolin" in e)


async def test_clients(hass, aioclient_mock):
    mock_api(aioclient_mock)
    await setup_entry(hass)

    online = hass.states.get("binary_sensor.pangolin_backup_box_online")
    assert online.state == "on"
    assert online.attributes["kind"] == "machine"
    laptop = hass.states.get("binary_sensor.pangolin_laptop_online")
    assert laptop.state == "off"
    assert laptop.attributes["kind"] == "user"
    assert laptop.attributes["user"] == "alex"
    assert "alex@example.com" not in str(laptop.attributes)
    assert hass.states.get("sensor.pangolin_backup_box_data_in").state == "5.0"
    assert hass.states.get("switch.pangolin_laptop_blocked").state == "on"
    assert hass.states.get("switch.pangolin_backup_box_archived").state == "off"

    # Blocked and archived clients are asked for explicitly.
    gets = [c for c in aioclient_mock.mock_calls
            if c[0] == "GET" and c[1].path.endswith("/org/home/clients")]
    assert gets[-1][1].query["status"] == "active,blocked,archived"

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.pangolin_backup_box_blocked"}, blocking=True)
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.pangolin_backup_box_archived"}, blocking=True)
    posts = [str(c[1]) for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert posts[-2].endswith("/client/11/block")
    assert posts[-1].endswith("/client/11/archive")

    # Delete is opt-in, so it isn't there by default.
    assert hass.states.get("button.pangolin_backup_box_delete_client") is None


async def test_client_action_without_permission(hass, aioclient_mock):
    import pytest
    from homeassistant.exceptions import HomeAssistantError

    mock_api(aioclient_mock)
    await setup_entry(hass)
    aioclient_mock.clear_requests()
    aioclient_mock.post(f"{BASE}/client/11/block", status=403, json={"error": True})
    with pytest.raises(HomeAssistantError, match="needs the Block Client permission"):
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": "switch.pangolin_backup_box_blocked"},
            blocking=True)


async def test_client_delete_removes_device(hass, aioclient_mock):
    from homeassistant.helpers import device_registry as dr, entity_registry as er

    mock_api(aioclient_mock)
    await setup_entry(hass, features=["client_status", "client_delete"])
    ent_reg, dev_reg = er.async_get(hass), dr.async_get(hass)
    device_id = ent_reg.async_get("button.pangolin_backup_box_delete_client").device_id

    await hass.services.async_call(
        "button", "press", {"entity_id": "button.pangolin_backup_box_delete_client"},
        blocking=True)
    deletes = [c for c in aioclient_mock.mock_calls if c[0] == "DELETE"]
    assert str(deletes[-1][1]).endswith("/client/11")
    assert dev_reg.async_get(device_id) is None


async def test_clients_optional(hass, aioclient_mock):
    mock_api(aioclient_mock, clients_status=403)
    entry = await setup_entry(hass)
    assert entry.state.name == "LOADED"
    assert entity_ids(hass, "switch")  # resources still there
    assert hass.states.get("binary_sensor.pangolin_backup_box_online") is None


async def test_reset_bandwidth(hass, aioclient_mock):
    mock_api(aioclient_mock)
    await setup_entry(hass)
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.pangolin_home_reset_bandwidth"}, blocking=True)
    posts = [str(c[1]) for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert posts[-1].endswith("/org/home/reset-bandwidth")


async def test_api_reachable_when_pangolin_is_down(hass, aioclient_mock):
    import aiohttp

    mock_api(aioclient_mock)
    entry = await setup_entry(hass)
    assert hass.states.get("binary_sensor.pangolin_home_api_reachable").state == "on"

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{BASE}/", exc=aiohttp.ClientError())
    aioclient_mock.get(f"{BASE}/org/home/sites", exc=aiohttp.ClientError())
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    reachable = hass.states.get("binary_sensor.pangolin_home_api_reachable")
    assert reachable.state == "off"  # still available, and says why
    assert hass.states.get("binary_sensor.pangolin_site_proxmox_online").state == "unavailable"


async def test_diagnostics_are_redacted(hass, aioclient_mock):
    from custom_components.pangolin.diagnostics import async_get_config_entry_diagnostics

    mock_api(aioclient_mock)
    entry = await setup_entry(hass, api_key="k1.secret")
    diag = await async_get_config_entry_diagnostics(hass, entry)
    text = str(diag)
    for secret in ("k1.secret", "api.example.com", "ha.example.com", "alex@example.com",
                   "alex", "10.0.0.5", "10.0.0.7", "Proxmox", "Home Assistant", "home",
                   "LAPTOP-SECRET", "SN-SECRET", "100.96.1.1"):
        assert secret not in text, secret
    assert diag["counts"] == {"sites": 1, "public_resources": 1,
                              "private_resources": 1, "clients": 2}


async def test_reconfigure_changes_url_and_key(hass, aioclient_mock):
    new = "https://pangolin-api.example.net/v1"
    mock_api(aioclient_mock)
    mock_api(aioclient_mock, BASE=new, clear=False)
    entry = await setup_entry(hass, api_key="k1.secret")

    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_URL: "https://pangolin-api.example.net", CONF_API_KEY: "k2.secret",
         CONF_VERIFY_SSL: False},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.data[CONF_URL] == new
    assert entry.data[CONF_API_KEY] == "k2.secret"
    assert entry.data[CONF_VERIFY_SSL] is False
    assert entry.data[CONF_ORG_ID] == "home"
    assert entry.unique_id == f"{new}|home"


async def test_reconfigure_keeps_key_when_blank(hass, aioclient_mock):
    mock_api(aioclient_mock)
    entry = await setup_entry(hass, api_key="k1.secret")
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: "https://api.example.com", CONF_VERIFY_SSL: True})
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_API_KEY] == "k1.secret"


async def test_stale_devices_can_be_removed(hass, aioclient_mock):
    from homeassistant.helpers import device_registry as dr, entity_registry as er
    from custom_components.pangolin import async_remove_config_entry_device

    mock_api(aioclient_mock)
    entry = await setup_entry(hass)
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)

    def device_of(entity_id):
        return dev_reg.async_get(ent_reg.async_get(entity_id).device_id)

    live = device_of("binary_sensor.pangolin_backup_box_online")
    org = device_of("binary_sensor.pangolin_home_api_reachable")
    gone = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, f"{entry.entry_id}_client_99")})
    assert await async_remove_config_entry_device(hass, entry, gone) is True
    assert await async_remove_config_entry_device(hass, entry, live) is False
    assert await async_remove_config_entry_device(hass, entry, org) is False


def test_client_permissions():
    from custom_components.pangolin.const import required_actions

    assert required_actions(["client_control"]) == [
        "getOrg", "listSites", "listClients", "blockClient", "unblockClient",
        "archiveClient", "unarchiveClient"]
    assert "deleteClient" in required_actions(["client_delete"])
    assert "resetSiteBandwidth" in required_actions(["reset_bandwidth"])


LEGACY = ["public_status", "public_control", "private_status", "private_control",
          "site_restart", "site_traffic"]


def pangolin_issues(hass):
    from homeassistant.helpers import issue_registry as ir

    return {i for d, i in ir.async_get(hass).issues if d == DOMAIN}


async def test_update_announces_new_features(hass, aioclient_mock, hass_client):
    from homeassistant.setup import async_setup_component
    from custom_components.pangolin.const import CONF_KNOWN_FEATURES

    assert await async_setup_component(hass, "repairs", {})
    mock_api(aioclient_mock)
    # Saved by an earlier version: chose features but has no known-features list.
    entry = await setup_entry(hass, features=LEGACY)
    issue_id = (f"new_features_{entry.entry_id}_"
                "client_status-client_control-client_delete-reset_bandwidth-client_last_seen-"
                "public_sso-public_block_access-public_maintenance")
    assert pangolin_issues(hass) == {issue_id}

    client = await hass_client()
    resp = await client.post(
        "/api/repairs/issues/fix", json={"handler": DOMAIN, "issue_id": issue_id})
    flow = await resp.json()
    assert flow["step_id"] == "confirm"
    # Offered unticked-if-permanent, with the permissions they need.
    assert flow["data_schema"][0]["description"]["suggested_value"] == [
        "client_status", "client_control", "reset_bandwidth", "public_block_access"]
    assert "List Clients" in flow["description_placeholders"]["permissions"]
    assert "Reset Organization Bandwidth" in flow["description_placeholders"]["permissions"]

    resp = await client.post(
        f"/api/repairs/issues/fix/{flow['flow_id']}", json={"features": ["client_status"]})
    assert (await resp.json())["type"] == "create_entry"
    await hass.async_block_till_done()

    assert entry.options["features"] == LEGACY + ["client_status"]
    assert entry.options[CONF_KNOWN_FEATURES] == ALL_FEATURES
    assert pangolin_issues(hass) == set()
    assert hass.states.get("binary_sensor.pangolin_backup_box_online").state == "on"


async def test_no_notice_after_setup_or_saving_features(hass, aioclient_mock):
    from custom_components.pangolin.const import CONF_KNOWN_FEATURES

    mock_api(aioclient_mock)
    result = await start_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"features": ["public_status"]})
    await hass.async_block_till_done()
    assert result["options"][CONF_KNOWN_FEATURES] == ALL_FEATURES
    assert pangolin_issues(hass) == set()

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "features"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"features": ["public_status", "site_traffic"]})
    await hass.async_block_till_done()
    assert entry.options[CONF_KNOWN_FEATURES] == ALL_FEATURES
    assert pangolin_issues(hass) == set()


async def test_no_delete_button_for_user_devices(hass, aioclient_mock):
    from homeassistant.helpers import entity_registry as er

    mock_api(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_URL: BASE, CONF_API_KEY: "k", CONF_ORG_ID: "home", CONF_VERIFY_SSL: True},
        options={"features": ["client_status", "client_delete"]},
    )
    entry.add_to_hass(hass)
    # An earlier version made a Delete button for the user device (client 12).
    ent_reg = er.async_get(hass)
    stale = ent_reg.async_get_or_create(
        "button", DOMAIN, f"{entry.entry_id}_client_12_delete", config_entry=entry)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get("button.pangolin_backup_box_delete_client") is not None
    assert hass.states.get("button.pangolin_laptop_delete_client") is None
    assert ent_reg.async_get(stale.entity_id) is None


async def test_site_restart_off_by_default(hass, aioclient_mock):
    mock_api(aioclient_mock)
    await setup_entry(hass)
    assert hass.states.get("button.pangolin_site_proxmox_restart") is None


async def test_last_seen_for_user_devices_only(hass, aioclient_mock):
    mock_api(aioclient_mock)
    await setup_entry(hass, features=["client_status", "client_last_seen"])
    assert hass.states.get("sensor.pangolin_laptop_last_seen").state == "2026-09-27T00:00:00+00:00"
    assert hass.states.get("sensor.pangolin_backup_box_last_seen") is None


async def test_last_seen_steps_while_online(hass, aioclient_mock):
    from custom_components.pangolin.coordinator import PangolinData

    mock_api(aioclient_mock)
    entry = await setup_entry(hass, features=["client_last_seen"])
    coordinator = entry.runtime_data
    base = 1790467200

    def push(last_seen, online):
        clients = dict(coordinator.data.clients)
        clients[12] = {**clients[12], "lastSeen": last_seen, "online": online}
        coordinator.async_set_updated_data(PangolinData(
            sites=coordinator.data.sites, resources=coordinator.data.resources,
            private_resources=coordinator.data.private_resources, clients=clients))

    push(base + 60, True)  # a ping a minute later: not worth a new state
    await hass.async_block_till_done()
    assert hass.states.get("sensor.pangolin_laptop_last_seen").state == "2026-09-27T00:00:00+00:00"
    push(base + 300, True)  # five minutes on: published
    await hass.async_block_till_done()
    assert hass.states.get("sensor.pangolin_laptop_last_seen").state == "2026-09-27T00:05:00+00:00"
    push(base + 420, False)  # went offline: the exact last ping is published
    await hass.async_block_till_done()
    assert hass.states.get("sensor.pangolin_laptop_last_seen").state == "2026-09-27T00:07:00+00:00"


async def test_last_seen_off_by_default(hass, aioclient_mock):
    mock_api(aioclient_mock)
    await setup_entry(hass)
    assert hass.states.get("binary_sensor.pangolin_laptop_online") is not None
    assert hass.states.get("sensor.pangolin_laptop_last_seen") is None


def resource_gets(aioclient_mock):
    return sum(1 for c in aioclient_mock.mock_calls
               if c[0] == "GET" and c[1].path == "/v1/resource/7")


async def test_extra_details_as_attributes(hass, aioclient_mock):
    mock_api(aioclient_mock)
    await setup_entry(hass, features=["public_status", "private_status", "client_status"])

    health = hass.states.get("sensor.pangolin_home_assistant_health").attributes
    assert health["targets"] == [{"site": "Proxmox", "target": "10.0.0.7:8123", "enabled": True,
                                  "health_check": True, "health": "healthy"}]
    assert health["sites"] == [{"name": "Proxmox", "online": True}]
    assert health["protection"] == {"sso": True, "password": False, "pin": True,
                                    "email_whitelist": False, "header_auth": False}

    site = hass.states.get("binary_sensor.pangolin_site_proxmox_online").attributes
    assert site["exit_node"] == "exit-1" and site["resource_count"] == 1

    nas = hass.states.get("binary_sensor.pangolin_nas_enabled").attributes
    assert nas["sites"] == [{"name": "Proxmox", "online": True}]
    assert nas["tcp_ports"] == "*" and nas["icmp"] is True

    laptop = hass.states.get("binary_sensor.pangolin_laptop_online").attributes
    assert laptop["platform"] == "windows" and laptop["os_version"] == "11"
    # Identifying device details stay out of Home Assistant.
    assert "LAPTOP-SECRET" not in str(laptop) and "SN-SECRET" not in str(laptop)


async def test_sso_switch(hass, aioclient_mock):
    mock_api(aioclient_mock)
    await setup_entry(hass, features=["public_sso"])
    assert hass.states.get("switch.pangolin_home_assistant_sso").state == "on"
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.pangolin_home_assistant_sso"}, blocking=True)
    posts = [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert str(posts[-1][1]).endswith("/resource/7")
    assert posts[-1][2] == {"sso": False}


async def test_block_access_switch_reads_back(hass, aioclient_mock):
    mock_api(aioclient_mock)
    await setup_entry(hass, features=["public_block_access"])
    assert hass.states.get("switch.pangolin_home_assistant_block_access").state == "off"

    mock_api(aioclient_mock, block=True)  # Pangolin now reports it blocked
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.pangolin_home_assistant_block_access"},
        blocking=True)
    posts = [c for c in aioclient_mock.mock_calls if c[0] == "POST"]
    assert posts[-1][2] == {"blockAccess": True}
    assert hass.states.get("switch.pangolin_home_assistant_block_access").state == "on"


async def test_maintenance_ignored_by_unlicensed_server(hass, aioclient_mock):
    import pytest
    from homeassistant.exceptions import HomeAssistantError

    mock_api(aioclient_mock)  # detail keeps saying maintenance is off
    await setup_entry(hass, features=["public_maintenance"])
    switch = hass.states.get("switch.pangolin_home_assistant_maintenance_mode")
    assert switch.state == "off"
    assert switch.attributes["maintenance_type"] == "forced"
    with pytest.raises(HomeAssistantError, match="licensed"):
        await hass.services.async_call(
            "switch", "turn_on",
            {"entity_id": "switch.pangolin_home_assistant_maintenance_mode"}, blocking=True)
    assert hass.states.get("switch.pangolin_home_assistant_maintenance_mode").state == "off"


async def test_resource_details_refresh_every_5_minutes(hass, aioclient_mock):
    from datetime import timedelta

    mock_api(aioclient_mock)
    entry = await setup_entry(hass, features=["public_block_access"])
    coordinator = entry.runtime_data
    assert resource_gets(aioclient_mock) == 1

    await coordinator.async_refresh()  # 30 seconds later: no detail calls
    assert resource_gets(aioclient_mock) == 1

    coordinator._details_fetched_at -= timedelta(minutes=6)
    await coordinator.async_refresh()
    assert resource_gets(aioclient_mock) == 2


async def test_resource_details_forbidden(hass, aioclient_mock):
    mock_api(aioclient_mock, detail_status=403)
    entry = await setup_entry(hass, features=["public_status", "public_block_access"])
    assert entry.state.name == "LOADED"
    assert hass.states.get("sensor.pangolin_home_assistant_health").state == "healthy"
    assert hass.states.get("switch.pangolin_home_assistant_block_access").state == "unavailable"


def test_new_switch_permissions():
    from custom_components.pangolin.const import required_actions

    assert required_actions(["public_sso"]) == [
        "getOrg", "listSites", "listResources", "updateResource"]
    assert required_actions(["public_maintenance"]) == [
        "getOrg", "listSites", "listResources", "getResource", "updateResource"]
