"""List every field the Pangolin Integration API returns, without the values.

Calls the list and detail endpoints this integration cares about and prints
each response's structure: field names and value types only. No domains,
addresses, emails, keys or names are printed, so the output is safe to share
in an issue or with a contributor.

Usage (Python 3.10+, no extra packages):

    python scripts/api_fields.py > api-fields.json

It asks for the Integration API address, organization ID and API key (the key
isn't echoed or saved). Endpoints the key can't read are reported as errors
and skipped.
"""

from __future__ import annotations

import getpass
import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def shape(value: Any) -> Any:
    """Replace every value with its type, keeping the structure."""
    if isinstance(value, dict):
        return {key: shape(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        merged: Any = None
        for item in value:
            merged = merge(merged, shape(item))
        return [merged] if merged is not None else []
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def merge(a: Any, b: Any) -> Any:
    """Combine two shapes, so fields seen on any item are listed."""
    if a is None:
        return b
    if b is None:  # field missing from this item: keep what we know
        return a
    if isinstance(a, dict) and isinstance(b, dict):
        return {k: merge(a.get(k), b.get(k)) for k in sorted(a.keys() | b.keys())}
    if isinstance(a, list) and isinstance(b, list):
        return [merge(a[0] if a else None, b[0] if b else None)] if a or b else []
    if a == b:
        return a
    types = set(a.split(" | ")) if isinstance(a, str) else {"object"}
    types |= set(b.split(" | ")) if isinstance(b, str) else {"object"}
    return " | ".join(sorted(types))


class Api:
    def __init__(self, base: str, key: str, verify: bool) -> None:
        base = base.strip().rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        if urllib.parse.urlparse(base).scheme not in ("http", "https"):
            sys.exit("The address must start with http:// or https://")
        self.base = base
        self.headers = {"Authorization": f"Bearer {key}"}
        self.context = None if verify else ssl._create_unverified_context()  # noqa: S323

    def get(self, path: str, **params: Any) -> Any:
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers=self.headers)  # noqa: S310
        with urllib.request.urlopen(request, context=self.context, timeout=20) as resp:  # noqa: S310
            return json.load(resp).get("data")


def ask(prompt: str) -> str:
    # Prompts go to stderr so the report alone can be saved with "> file".
    print(prompt, end="", file=sys.stderr, flush=True)
    return input()


def main() -> None:
    base = ask("Integration API address (e.g. https://api.example.com): ")
    org = ask("Organization ID: ").strip()
    key = getpass.getpass("API key (not shown): ", stream=sys.stderr).strip()
    verify = ask("Verify SSL certificate? [Y/n]: ").strip().lower() != "n"
    api = Api(base, key, verify)
    report: dict[str, Any] = {}

    def fetch(label: str, path: str, **params: Any) -> Any:
        try:
            data = api.get(path, **params)
        except urllib.error.HTTPError as err:
            report[label] = f"error {err.code}"
            return None
        except (urllib.error.URLError, TimeoutError, ValueError) as err:
            report[label] = f"error {type(err).__name__}"
            return None
        report[label] = shape(data)
        return data

    fetch("GET /org/{orgId}", f"/org/{org}")

    lists = [
        ("sites", f"/org/{org}/sites", "sites", "siteId", "/site/{}", {}),
        ("resources", f"/org/{org}/resources", "resources", "resourceId", "/resource/{}", {}),
        ("private-resources", f"/org/{org}/private-resources", "siteResources",
         "siteResourceId", "/private-resource/{}", {}),
        ("clients", f"/org/{org}/clients", "clients", "clientId", "/client/{}",
         {"status": "active,blocked,archived"}),
        ("user-devices", f"/org/{org}/user-devices", "devices", "clientId", "/client/{}",
         {"status": "active,pending,denied,blocked,archived"}),
    ]
    for name, path, key_name, id_field, detail, extra in lists:
        data = fetch(f"GET {path.replace(org, '{orgId}')}", path, page=1, pageSize=20, **extra)
        items = (data or {}).get(key_name) or []
        # A few items' details are enough to see every field.
        for item in items[:3]:
            item_id = item.get(id_field)
            if item_id is None:
                continue
            label = f"GET {detail.format('{id}')} ({name})"
            detail_data = fetch(f"{label} #{item_id}", detail.format(item_id))
            if detail_data is not None:
                previous = report.pop(label, None)
                report[label] = merge(previous, report.pop(f"{label} #{item_id}"))
            else:
                report[label] = report.pop(f"{label} #{item_id}")
        if name == "resources" and items:
            first = items[0].get("resourceId")
            fetch("GET /resource/{id}/targets", f"/resource/{first}/targets")

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
