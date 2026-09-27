# Pangolin (Unofficial) for Home Assistant

Custom integration that connects Home Assistant to the [Pangolin](https://github.com/fosrl/pangolin) Integration API.

> **AI-written ("vibe coded").** [Claude](https://claude.ai) (Anthropic's AI) wrote this integration, with the maintainer directing its features and testing it on their own Pangolin setup. It has automated tests, but **it hasn't had a line-by-line human code review**. Some features change your Pangolin server (enabling/disabling resources, blocking/archiving/deleting clients, changing API key permissions), so try them carefully. It's an unofficial project, not affiliated with or endorsed by Fossorial/Pangolin. Use at your own risk, and please open an issue if something breaks.

## Entities

Your organization gets a hub device with
- Sites online (sensor): number of online sites, with every site's name, online state, status (pending or approved), type and address in the `sites` attribute
- API reachable (diagnostic binary sensor): whether Pangolin answers at all. This stays available when everything else is unavailable, so you can tell "Pangolin is down" apart from "the key stopped working".
- Reset bandwidth (button): zeroes every site's data in/out counters

Each Pangolin site becomes a device with
- Online (binary sensor, connectivity)
- Restart (button, off by default, Newt sites only): tells the site's Newt connector to restart its WireGuard tunnel, a quick reconnect for a stuck site. Nothing visible happens when it works. Most Pangolin versions don't allow this for API keys, so it usually shows an error instead.
- Data in / Data out (diagnostic sensors, MB)

Each public resource becomes a device with
- Enabled (switch) that enables or disables the resource in Pangolin
- Health (sensor) with the values healthy, degraded, offline, unknown

Each private resource becomes a device with
- Enabled (switch) that enables or disables the private resource, with its mode, destination, alias and sites as attributes

Each client (machine client or user device running the Pangolin client) becomes a device with
- Online (binary sensor, connectivity), with kind, user, version and device model as attributes. It's handy for presence, e.g. "my laptop is connected through Pangolin".
- Data in / Data out (diagnostic sensors, MB)
- Blocked and Archived (switches) that block/unblock or archive/unarchive the client
- Delete client (button, opt-in, **machine clients only**): permanently deletes the client in Pangolin and removes its device from Home Assistant. Pangolin doesn't allow deleting user devices (phones and laptops signed in as a user); archive those instead.

Resources show up in Home Assistant's device list as services, so they're easy to tell apart from sites and clients.

New sites, resources and clients are picked up automatically. Data refreshes every 30 seconds.

## Pangolin requirements

> **Source:** steps 1 to 3 summarize Pangolin's official [Enable Integration API](https://docs.pangolin.net/self-host/advanced/integration-api) guide as of **September 26, 2026**. Pangolin changes over time, so check that page for the current instructions and exact config. If this summary and the guide disagree, follow the guide.

### 1. Enable the Integration API (self-hosted)

In Pangolin's `config.yml`, set `enable_integration_api: true` under `flags`. The API listens on port `3003` by default. To use a different port, set `integration_port` under `server`.

### 2. Route it through Traefik

The guide adds the following to `config/traefik/dynamic_config.yml`, for a hostname such as `api.example.com`:
- A router on the `web` entry point that redirects to HTTPS. It also uses the `badger` middleware if you run Badger 1.3.0 or later with it enabled.
- A router on the `websecure` entry point with TLS from your certificate resolver.
- A service that forwards to `http://pangolin:3003`.

Copy the exact YAML from the [guide](https://docs.pangolin.net/self-host/advanced/integration-api#configure-traefik-routing), and make sure the hostname resolves to your Pangolin server.

### 3. Check that it's reachable

Open `https://api.example.com/v1/docs`. You should see Pangolin's Swagger UI. The API itself is at `https://api.example.com/v1`. In Home Assistant, enter `https://api.example.com`, and the integration adds `/v1` for you.

### 4. Create an API key

In the Pangolin dashboard, create an **organization** API key with the permissions for the features you want:

- Get Organization and List Sites (always)
- List Resources, plus Update Resource for the switches (public resources)
- List Site Resources, plus Update Site Resource for the switches (private resources)
- List Clients, plus Block Client, Unblock Client, Archive Client and Unarchive Client for the switches, and Delete Client for the delete buttons (clients)
- Reset Organization Bandwidth (reset bandwidth button)
- Restart Site (restart buttons; see the note below)

The full per-feature table is under [Permission check](#permission-check-advanced). Once the integration is set up, that tool can work the list out, or adjust the key for you.

A root key also works and lets setup list your organizations, but it can do anything on the server. An org key limited to the permissions above is safer.

Private resources and clients are optional. If the key can't list them, or your Pangolin version doesn't have the private resources endpoint, the integration skips them and logs a warning. Grant the permission and reload the integration to add them later.

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
| Sites: restart buttons | Restart button per Newt site. Starts unticked, because most Pangolin versions don't allow it for API keys. |
| Sites: data in/out sensors | Data in / Data out diagnostic sensors |
| Clients: status | Online sensor and Data in / Data out sensors per client |
| Clients: block and archive switches | Blocked and Archived switches |
| Clients: delete buttons | Delete client button on machine clients. **Permanent**, so it starts unticked. |
| Organization: reset bandwidth button | Reset bandwidth button |

Site online sensors, the Sites online summary and API reachable are always on. Updating from an earlier version keeps your current choices, and new features stay off. When an update adds features, Home Assistant shows a **"New Pangolin features are available"** notice under Settings > System > Repairs. Press **Fix** to see the new features and the permissions they need, and tick the ones you want. You can also ignore the notice, or turn features on later under Configure.

Pangolin org API keys can't read their own permission list, so the integration requests one item from each resource list to see what the key can read. That check changes nothing on the server. Features the key can't use are hidden, and everything else starts ticked except client delete buttons and site restart buttons. Write permissions (Update Resource, Update Site Resource, the client actions, Reset Organization Bandwidth, Restart Site) can't be checked without making a change, so if one is missing you get an error when you use that control.

To change features later, go to the integration's page and choose Configure. Entities and devices for features you turn off are removed.

### Reconfigure

To change the Integration API address, the SSL check or the API key, open the integration's menu and choose **Reconfigure**. Leave the key empty to keep the current one. The organization, devices and entities stay as they are.

### Removing old devices

If a site, resource or client is deleted in Pangolin, its device stays in Home Assistant as unavailable. Delete it from the device page. Home Assistant only allows that once Pangolin no longer has it.

### Permission check (advanced)

Configure > **Permission check (advanced)** works out the smallest set of Pangolin permissions your features need.

- **Without a root key**, it lists the permissions to set on your key yourself, with what each one is for.
- **With a root key**, it compares that list with what the integration's key actually has, then offers to add what's missing and remove what isn't needed. Tick features that are off today to add the permissions they'll need. The key is found automatically from its ID (the part before the `.`), so you don't need to enter its name.
- **If the integration runs on a root key**, it can create a new organization key with only the needed permissions, check that it works, and switch to it. Your root key isn't changed or deleted.

> **Requirements:** Pangolin has two kinds of API keys. **Organization keys** are made in an organization's Settings > API Keys. Even with every box ticked, they can't read or change key permissions, because those permissions aren't offered for them. **Root keys** are made by a server admin in **Server Admin > API Keys**, and only they can do this. To compare, the root key needs **List API Key Actions**. To apply changes, it also needs **Set API Key Allowed Actions**, plus **Create API Key** when replacing a root key. The root key you enter is used for that one check and is never saved.

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
| Clients: status | List Clients |
| Clients: switches | List Clients, Block Client, Unblock Client, Archive Client, Unarchive Client |
| Clients: delete buttons | List Clients, Delete Client |
| Organization: reset bandwidth | Reset Organization Bandwidth |

## Troubleshooting

**"Could not reach the Pangolin Integration API"**
- In a browser on the same network as Home Assistant, open `https://<your-api-host>/v1/docs`. If Swagger doesn't load, the problem is in Pangolin or Traefik, not Home Assistant. Recheck the [Integration API guide](https://docs.pangolin.net/self-host/advanced/integration-api): the config flag, the Traefik routers and service, and DNS for the hostname.
- Enter just the scheme and host, like `https://api.example.com`. The `/v1` is added for you.
- If you use a self-signed certificate, untick **Verify SSL certificate**.

**"The API key was rejected"**
- The key is wrong or was deleted in Pangolin. Home Assistant raises a re-authentication notification, where you can paste a new key.

**Setup asks me to type the organization ID**
- That's expected with an organization API key, because only root keys can list organizations. The ID is in the Pangolin dashboard URL. "Can't access that organization" means the key belongs to a different organization.

**Some features are missing from the checklist**
- The key can't read that resource list (see the note on the checklist screen). Add **List Resources** or **List Site Resources** to the key, then open Configure > Choose features again. Configure > Permission check lists exactly what's needed.

**The permission check says my key isn't a root key**
- Organization keys can't read or change key permissions, even with every permission ticked. Only root keys, made in Server Admin > API Keys, can. See [Permission check](#permission-check-advanced).

**Clients don't show up**
- The key lacks **List Clients**. The log shows "Clients unavailable, skipping them". Grant it, then reload the integration.

**Private resources don't show up**
- The key lacks **List Site Resources**, or your Pangolin version has no private resources endpoint. The log shows "Private resources unavailable, skipping them". Grant the permission, then reload the integration.

**A switch says "Could not enable/disable resource"**
- The key lacks **Update Resource** (public) or **Update Site Resource** (private).

**A restart button says Pangolin didn't accept the restart**
- Many Pangolin versions only allow site restart from the dashboard, not with an API key, and the dashboard's key editor doesn't offer that permission. Turn off Sites: restart buttons under Configure > Choose features to hide them.

**Health shows "Unknown"**
- Pangolin has no health results for that resource's targets. This usually means health checks are off for them in Pangolin.

**Entities are unavailable**
- Home Assistant can't reach Pangolin right now (see the first item), or the site or resource was deleted in Pangolin.

**Getting more detail**
- On the integration's page, open the menu and choose **Download diagnostics**. Keys, addresses, domains, names and user details are removed from the file.
- On the integration's page, open the menu and choose **Enable debug logging**, reproduce the problem, then disable it to download the log.
- When [opening an issue](https://github.com/Mcp20091/ha-pangolin/issues), include your Home Assistant and Pangolin versions and the relevant log lines. **Remove API keys and your domain names first.**

## Contributing

Contributions are welcome. [CONTRIBUTING.md](CONTRIBUTING.md) covers the tools you need, how to run the tests and how CI checks changes. [AGENTS.md](AGENTS.md) collects what's worth knowing about the Pangolin API and this codebase before you change it, for people and AI coding agents alike.

## Credits

- **[Pangolin](https://github.com/fosrl/pangolin)** by the Fossorial team and its contributors: the self-hosted tunneled reverse proxy this integration talks to, its [Integration API](https://docs.pangolin.net/self-host/advanced/integration-api), and its documentation. The Pangolin name and logo belong to Fossorial, Inc. and are used here only to identify the service this integration connects to. Please support the project upstream.
- **[Home Assistant](https://www.home-assistant.io)** and its developer documentation
- **[HACS](https://hacs.xyz)** for custom integration distribution and validation
- **[pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)** for the test harness
- **[Material Design Icons](https://pictogrammers.com/library/mdi/)** by Pictogrammers for entity icons
- Written with **[Claude](https://claude.ai)** by Anthropic, and maintained by [@Mcp20091](https://github.com/Mcp20091)
