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

1. Enable the Integration API (self-hosted) by setting `flags.enable_integration_api: true` in Pangolin's `config.yml`, then route it so Home Assistant can reach it (it listens on port 3003 by default). See the Pangolin docs for the Integration API.
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

Settings > Devices & services > Add integration > Pangolin, then enter
- Integration API URL, for example `https://api.example.com/v1`
- API key
- Organization ID
