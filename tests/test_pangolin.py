from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pangolin.const import ALL_FEATURES, CONF_ORG_ID, DOMAIN

BASE = "https://api.example.com/v1"


def ok(data):
    return {"data": data, "success": True, "error": False, "message": "", "status": 200}


HOME = {"orgId": "home", "name": "Home"}


def mock_api(aioclient_mock, enabled=True, health="healthy", private_status=200,
             orgs=(HOME,), orgs_status=200):
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{BASE}/orgs", status=orgs_status,
        json=ok({"orgs": list(orgs), "pagination": {"total": len(orgs), "limit": 1000, "offset": 0}}),
    )
    aioclient_mock.get(f"{BASE}/org/home", json=ok({"org": HOME}))
    aioclient_mock.get(f"{BASE}/org/other", status=403, json={"error": True})
    aioclient_mock.get(
        f"{BASE}/org/home/sites",
        json=ok({"sites": [{"siteId": 1, "name": "Proxmox", "niceId": "px", "type": "newt",
                            "online": True, "megabytesIn": 12.5, "megabytesOut": 3.0}],
                 "pagination": {"total": 1, "page": 1, "pageSize": 100}}),
    )
    aioclient_mock.get(
        f"{BASE}/org/home/resources",
        json=ok({"resources": [{"resourceId": 7, "name": "Home Assistant", "niceId": "ha",
                                "enabled": enabled, "health": health,
                                "fullDomain": "ha.example.com", "mode": "http"}],
                 "pagination": {"total": 1, "page": 1, "pageSize": 100}}),
    )
    aioclient_mock.get(
        f"{BASE}/org/home/private-resources",
        status=private_status,
        json=ok({"siteResources": [{"siteResourceId": 3, "name": "NAS", "niceId": "nas",
                                    "mode": "host", "destination": "10.0.0.5",
                                    "enabled": True, "siteNames": ["Proxmox"]}],
                 "pagination": {"total": 1, "page": 1, "pageSize": 100}}),
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
    assert result["options"] == {"features": ALL_FEATURES}
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


async def setup_entry(hass, features=None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_URL: BASE, CONF_API_KEY: "k", CONF_ORG_ID: "home", CONF_VERIFY_SSL: True},
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
    assert sw.attributes["sites"] == ["Proxmox"]

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
    await setup_entry(hass)

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
    await setup_entry(hass)
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
    assert suggested_features(result) == [
        "public_status", "public_control", "site_restart", "site_traffic"]
    assert "Private" in result["description_placeholders"]["unavailable"]

    # Features the key can't use aren't accepted by the form.
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {"features": ["public_status", "private_control"]})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"features": ["public_status"]})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {"features": ["public_status"]}
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
    assert result["step_id"] == "features"
    assert suggested_features(result) == ALL_FEATURES
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"features": ["public_status", "public_control", "private_status"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert reg.async_get("switch.pangolin_nas_enabled") is None
    assert hass.states.get("binary_sensor.pangolin_nas_enabled").state == "on"
    assert reg.async_get("button.pangolin_site_proxmox_restart") is None
    assert hass.states.get("switch.pangolin_home_assistant_enabled").state == "on"
