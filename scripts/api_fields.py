"""List every field the Pangolin Integration API returns, without the values.

Calls the list and detail endpoints this integration cares about and prints
each response's structure: field names and value types only. No domains,
addresses, emails, keys or names are printed, so the output is safe to share
in an issue or with a contributor.

Usage (Python 3.10+, no extra packages): double-click it, or run

    python scripts/api_fields.py

It asks for the Integration API address, organization ID and API key (the key
isn't echoed or saved) and checks them first, offering a retry if they don't
work. Only then does it save the result as api-fields.json next to this script.
It waits for Enter before closing. Endpoints the key can't read are
reported as errors and skipped.
"""

from __future__ import annotations

import getpass
import json
import os
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
    # Empty on some items, filled on others: keep the filled structure.
    if a == "null" and isinstance(b, (dict, list)):
        return b
    if b == "null" and isinstance(a, (dict, list)):
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
        # The prompt already shows "https://api.", so a bare domain goes after
        # it. A full address is used as typed.
        if "://" not in base:
            base = "https://" + (base if base.startswith("api.") else "api." + base)
        if not base.endswith("/v1"):
            base += "/v1"
        if urllib.parse.urlparse(base).scheme not in ("http", "https"):
            raise ValueError("The address must start with http:// or https://")
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


def call(api: Api, path: str, **params: Any) -> tuple[Any, str | None]:
    """Return (data, None) on success or (None, "error ...")."""
    try:
        return api.get(path, **params), None
    except urllib.error.HTTPError as err:
        return None, f"error {err.code}"
    except (urllib.error.URLError, TimeoutError, ValueError) as err:
        return None, f"error {type(err).__name__}"


def ask(prompt: str) -> str:
    # Prompts go to stderr so they never end up in the saved report.
    print(prompt, end="", file=sys.stderr, flush=True)
    return input()


def explain(error: str, base: str, org: str) -> tuple[str, bool]:
    """Say what went wrong, and whether carrying on could still be useful."""
    if error == "error 401":
        return "The API key was rejected. Check that you copied the whole key.", False
    if error == "error 403":
        return (
            f"The key was accepted, but it can't read organization '{org}'. Check "
            "the organization ID, or give the key the Get Organization permission.",
            True,
        )
    if error == "error 404":
        return f"Nothing at {base} answered like the Pangolin Integration API. Check the address.", False
    reason = error.removeprefix("error ")
    return (
        f"Couldn't reach {base} ({reason}). Check the address, and that the "
        "Integration API is enabled and reachable.",
        False,
    )


def connect() -> tuple[Api, str, Any, str | None] | None:
    """Ask for the details until they work. None means the user quit."""
    while True:
        print(
            "Integration API address. Type your domain, or a full http(s):// "
            "address if the API isn't on api.<domain>.",
            file=sys.stderr,
        )
        base = ask("https://api.")
        org = ask("Organization ID: ").strip()
        key = getpass.getpass("API key (not shown): ", stream=sys.stderr).strip()
        verify = ask("Verify SSL certificate? [Y/n]: ").strip().lower() != "n"

        can_continue = False
        error: str | None = None
        org_data: Any = None
        try:
            api = Api(base, key, verify)
        except ValueError as err:
            message = str(err)
        else:
            if not key or not org:
                message = "The organization ID and API key can't be empty."
            else:
                org_data, error = call(api, f"/org/{org}")
                if error is None:
                    return api, org, org_data, None
                message, can_continue = explain(error, api.base, org)

        print(f"\n{message}", file=sys.stderr)
        options = "[R]etry, [C]ontinue anyway, [Q]uit" if can_continue else "[R]etry, [Q]uit"
        choice = ask(f"{options} (Enter = retry): ").strip().lower()
        if choice == "q":
            return None
        if choice == "c" and can_continue:
            return api, org, org_data, error
        print(file=sys.stderr)


def main() -> None:
    connected = connect()
    if connected is None:
        print("\nNothing was saved.", file=sys.stderr)
        return
    api, org, org_data, org_error = connected
    report: dict[str, Any] = {"GET /org/{orgId}": org_error or shape(org_data)}

    def fetch(label: str, path: str, **params: Any) -> Any:
        data, error = call(api, path, **params)
        report[label] = error if error else shape(data)
        return data

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
        # A few items' details are enough to see every field. Use real IDs
        # from the list; if it couldn't be read, try the first few IDs.
        ids = [i[id_field] for i in items[:3] if i.get(id_field) is not None]
        label = f"GET {detail.format('{id}')} ({name})"
        if not ids:
            ids = [1, 2, 3]
            label += " [guessed IDs 1-3]"
        merged: Any = None
        last_error: str | None = None
        found: list[Any] = []
        for item_id in ids:
            detail_data, error = call(api, detail.format(item_id))
            if error:
                last_error = error
                continue
            merged = merge(merged, shape(detail_data))
            found.append(item_id)
        report[label] = merged if merged is not None else last_error
        if name == "resources":
            first = (found or ids)[0]
            fetch("GET /resource/{id}/targets", f"/resource/{first}/targets")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api-fields.json")
    with open(out, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)
    print(f"\nSaved to {out}", file=sys.stderr)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nNothing was saved.", file=sys.stderr)
    except Exception as err:  # noqa: BLE001 - show any failure before the window closes
        print(f"\nSomething went wrong: {err}\nNothing was saved.", file=sys.stderr)
    # Double-clicked scripts get their own window; keep it open to read.
    try:
        ask("\nPress Enter to close.")
    except (KeyboardInterrupt, EOFError):
        pass
