# Security

## Reporting a vulnerability

Please **don't open a public issue** for security problems. Report them privately with GitHub's [private vulnerability reporting](https://github.com/Mcp20091/ha-pangolin/security/advisories/new) (Security tab > Report a vulnerability). You'll get a reply there.

This is an unofficial, AI-written community project maintained in spare time, with no guaranteed response times. Problems in Pangolin itself belong with the [Pangolin project](https://github.com/fosrl/pangolin/security).

## Keep your secrets out of reports

When opening any issue, **remove API keys, domain names and hostnames** from logs and screenshots. The integration's **Download diagnostics** file already has keys, URLs, domains, names, addresses and user details removed.

## What the repo does to stay safe

- **Secret scanning:** GitHub secret scanning with push protection is on, and a TruffleHog scan runs on every push and pull request, plus weekly across the full history.
- **Code scanning:** GitHub CodeQL, and Ruff's security rules (the Bandit checks) on every change.
- **Dependencies:** the integration has no third-party Python requirements. Dependabot watches the test dependencies and the GitHub Actions, which are pinned to exact commits.
- **Credentials in Home Assistant:** the API key is stored the way Home Assistant stores every integration's settings (`.storage/core.config_entries`). It's sent only to the Integration API URL you enter. A root key entered in the permission check is used for that one check and never saved.
