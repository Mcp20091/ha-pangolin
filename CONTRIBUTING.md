# Contributing

Thanks for helping out. Bug reports, fixes and new features are all welcome. Please open an issue first for anything large so we can agree on the approach.

## What you need

| Tool | Why |
| --- | --- |
| Python 3.14 | Same version current Home Assistant runs on. The test harness installs a matching Home Assistant. |
| git | Version control |
| Linux, macOS or WSL | Home Assistant's pytest plugin doesn't run on native Windows (it blocks sockets that the Windows event loop needs). On Windows, use WSL. |

Optional, for trying changes for real:
- A Home Assistant instance (HACS makes installing a branch easy)
- A Pangolin instance with the Integration API enabled, plus an API key

No build step is needed. The integration is plain Python that Home Assistant loads directly.

## Set up and run the tests

```bash
git clone https://github.com/Mcp20091/ha-pangolin.git
cd ha-pangolin
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt
pytest -q
```

## How it's tested

- **Unit and integration tests** live in `tests/test_pangolin.py`. They use [pytest-homeassistant-custom-component](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component), which runs a real Home Assistant core in memory. The Pangolin API is faked with its `aioclient_mock` fixture, so no Pangolin server is needed.
- The tests cover setup (org picker, org ID entry, bad keys, the `/v1` suffix), feature selection, every entity type, switches and buttons calling the right endpoints, pagination, optional private resources, and every Permission check path.
- **CI** (`.github/workflows/validate.yml`) runs on every push and pull request:
  - `hacs/action`: HACS repository rules
  - `hassfest`: Home Assistant's manifest, translation and icon validation
  - `pytest`: the test suite above
- **Manual testing:** copy `custom_components/pangolin` into your Home Assistant `config/custom_components/` folder and restart, or add your fork to HACS as a custom repository and install your branch.

Please add or update tests with any behavior change and make sure CI passes.

## Security checks

The **Security** workflow runs a TruffleHog secret scan and Ruff's security lint on every push and pull request. To run the lint yourself:

```bash
pip install ruff
ruff check
```

**Never commit real API keys, domains or hostnames**, including in tests, fixtures or screenshots. Tests use `example.com` and fake keys like `k1.secret`. See [SECURITY.md](SECURITY.md) for how to report a vulnerability privately.

## Working on the code

- `custom_components/pangolin/api.py`: the API client
- `coordinator.py`: polling
- `config_flow.py`: setup and Configure screens
- `binary_sensor.py`, `sensor.py`, `switch.py`, `button.py`: entities
- `strings.json`: UI text. Keep `translations/en.json` identical to it.
- `icons.json`: entity icons
- `brand/`: logo images

[AGENTS.md](AGENTS.md) has the details worth knowing before changing anything: API quirks, naming rules, and what hassfest rejects.

To enable and reach the API, follow Pangolin's [Integration API guide](https://docs.pangolin.net/self-host/advanced/integration-api). Pangolin's OpenAPI spec doesn't describe response fields. To see exactly what your server returns, run `python scripts/api_fields.py > api-fields.json`, or `.\scriptspi_fields.ps1 > api-fields.json` in PowerShell (5.1 or 7, no Python needed). It prints field names and types only, never values, so the output is safe to share. Your Pangolin server documents its own API at `https://<your-api-host>/v1/docs`, with the raw spec at `/v1/openapi.json`. Pangolin's source ([fosrl/pangolin](https://github.com/fosrl/pangolin)) is the final word on which permission each endpoint needs.

## Releases

1. Bump `version` in `custom_components/pangolin/manifest.json`.
2. Merge to `main` with CI passing.
3. Create a GitHub release tagged `vX.Y.Z`. HACS offers releases as updates.
