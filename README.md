# Pangolin for Home Assistant

Custom integration that connects Home Assistant to the [Pangolin](https://github.com/fosrl/pangolin) Integration API.

> **Built with Claude.** This integration was written by [Claude](https://claude.ai) (Anthropic's AI assistant) from the Pangolin Integration API OpenAPI spec. It has automated tests but limited real-world testing so far. It is an unofficial community project and is not affiliated with or endorsed by Fossorial/Pangolin. Use at your own risk and please open an issue if something breaks.

## Entities

Each Pangolin site becomes a device with
- Online (binary sensor, connectivity)
- Data in / Data out (diagnostic sensors, MB)

Each Pangolin resource becomes a device with
- Enabled (switch) that enables or disables the resource in Pangolin
- Health (sensor) with the values healthy, degraded, offline, unknown

New sites and resources are picked up automatically. Data refreshes every 30 seconds.

## Pangolin requirements

1. Enable the Integration API (self-hosted) by setting `flags.enable_integration_api: true` in Pangolin's `config.yml`, then route it so Home Assistant can reach it (it listens on port 3003 by default). See the Pangolin docs for the Integration API.
2. In the Pangolin dashboard, create an organization API key with these permissions
   - Get Organization
   - List Sites
   - List Resources
   - Update Resource

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
