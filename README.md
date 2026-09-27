# Pangolin for Home Assistant

Custom integration that connects Home Assistant to the [Pangolin](https://github.com/fosrl/pangolin) Integration API.

> **Built with Claude.** This integration was written by [Claude](https://claude.ai) (Anthropic's AI assistant) from the Pangolin Integration API OpenAPI spec. It has automated tests but limited real-world testing so far. It is an unofficial community project and is not affiliated with or endorsed by Fossorial/Pangolin. Use at your own risk and please open an issue if something breaks.

## Entities

Your organization gets a hub device with
- Sites online (sensor): number of online sites, with every site's name, online state, status (pending or approved), type and address in the `sites` attribute

Each Pangolin site becomes a device with
- Online (binary sensor, connectivity)
- Restart (button) that restarts the site's Newt tunnel (Newt sites only)
- Data in / Data out (diagnostic sensors, MB)

Each public resource becomes a device with
- Enabled (switch) that enables or disables the resource in Pangolin
- Health (sensor) with the values healthy, degraded, offline, unknown

Each private resource becomes a device with
- Enabled (switch) that enables or disables the private resource, with its mode, destination, alias and sites as attributes

New sites and resources are picked up automatically. Data refreshes every 30 seconds.

## Pangolin requirements

1. Enable the Integration API (self-hosted) by setting `flags.enable_integration_api: true` in Pangolin's `config.yml`, then route it so Home Assistant can reach it (it listens on port 3003 by default). See the Pangolin docs: [Integration API](https://docs.pangolin.net/self-host/advanced/integration-api).
2. In the Pangolin dashboard, create an organization API key with these permissions
   - Get Organization
   - List Sites
   - Restart Site (for the restart buttons)
   - List Resources
   - Update Resource
   - List Site Resources and Update Site Resource (for private resources; optional)

Private resources are optional. If the key can't list them, or your Pangolin version doesn't have the private resources endpoint, the integration skips them and logs a warning. Grant the permission and reload the integration to add them later.

Site restart is part of the Integration API spec, but some Pangolin versions only allow it from the dashboard. If so, pressing Restart shows an error saying it isn't supported.

## Install

Manual
1. Copy `custom_components/pangolin` into your Home Assistant `/config/custom_components/` folder.
2. Restart Home Assistant.

HACS
1. HACS > three dots > Custom repositories > add `https://github.com/Mcp20091/ha-pangolin` with type Integration.
2. Install Pangolin and restart Home Assistant.

## Setup

Settings > Devices & services > Add integration > Pangolin, then
1. Enter the Integration API address, for example `https://api.example.com`. `/v1` is shown beside the box and added for you.
2. Enter the API key.
3. Choose the organization.
   - With a **root** API key, pick it from a dropdown. If the key only sees one organization, it's picked for you.
   - With an **organization** API key, type the organization ID (it's in the Pangolin dashboard URL). Pangolin only lets root keys list organizations.

### Choosing features

After the key is checked, you get a list of features to tick:

| Feature | Adds |
| --- | --- |
| Public resources: status | Health sensor, plus a read-only Enabled sensor when switches are off |
| Public resources: enable/disable switches | Enabled switch |
| Private resources: status | Read-only Enabled sensor |
| Private resources: enable/disable switches | Enabled switch |
| Sites: restart buttons | Restart button per Newt site |
| Sites: data in/out sensors | Data in / Data out diagnostic sensors |

Site online sensors and the Sites online summary are always on.

Pangolin org API keys can't read their own permission list, so the integration requests one item from each resource list to see what the key can read. That check changes nothing on the server. Features the key can't use are hidden, and everything else starts ticked. Write permissions (Update Resource, Update Site Resource, Restart Site) can't be checked without making a change, so if one is missing you get an error when you use that control.

To change features later, go to the integration's page and choose Configure. Entities and devices for features you turn off are removed.

### Permission check (advanced)

Configure > **Permission check (advanced)** works out the smallest set of Pangolin permissions your features need.

- **Without a root key**, it lists the permissions to set on your key yourself, with what each one is for.
- **With a root key**, it compares that list with what the integration's key actually has, then offers to add what's missing and remove what isn't needed. Tick features that are off today to add the permissions they'll need. The key is found automatically from its ID (the part before the `.`), so you don't need to enter its name.
- **If the integration runs on a root key**, it can create a new organization key with only the needed permissions, check that it works, and switch to it. Your root key isn't changed or deleted.

> **Requirements:** Pangolin only lets **root** API keys read or change key permissions. To compare, the root key needs **List API Key Actions**. To apply changes, it also needs **Set API Key Allowed Actions**, plus **Create API Key** when replacing a root key. The root key you enter is used for that one check and is never saved.

> **Warning: use at your own risk.** Changing permissions can cut off features you use now, features added in later versions, and anything else that uses the same key. Nothing changes until you tick the confirmation box. This is an unofficial project and its authors aren't responsible for lost access, connection problems or other issues caused by permission changes.

| Feature | Pangolin permissions |
| --- | --- |
| Always | Get Organization, List Sites |
| Public resources: status | List Resources |
| Public resources: switches | List Resources, Update Resource |
| Private resources: status | List Site Resources |
| Private resources: switches | List Site Resources, Update Site Resource |
| Sites: restart buttons | Restart Site (not offered in the dashboard's key editor; some versions don't allow it for API keys) |
| Sites: data in/out | nothing extra |

## Contributing

Contributions are welcome. [CONTRIBUTING.md](CONTRIBUTING.md) covers the tools you need, how to run the tests and how CI checks changes. [AGENTS.md](AGENTS.md) collects what's worth knowing about the Pangolin API and this codebase before you change it, for people and AI coding agents alike.

## Credits

- **[Pangolin](https://github.com/fosrl/pangolin)** by the Fossorial team and its contributors: the self-hosted tunneled reverse proxy this integration talks to, its [Integration API](https://docs.pangolin.net/self-host/advanced/integration-api), and its documentation. The Pangolin name and logo belong to Fossorial, Inc. and are used here only to identify the service this integration connects to. Please support the project upstream.
- **[Home Assistant](https://www.home-assistant.io)** and its developer documentation
- **[HACS](https://hacs.xyz)** for custom integration distribution and validation
- **[pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)** for the test harness
- **[Material Design Icons](https://pictogrammers.com/library/mdi/)** by Pictogrammers for entity icons
- Written with **[Claude](https://claude.ai)** by Anthropic, and maintained by [@Mcp20091](https://github.com/Mcp20091)
