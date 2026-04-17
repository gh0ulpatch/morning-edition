#!/usr/bin/env python3
"""
upload_to_sharepoint.py — Upsert today's conferences into a SharePoint List.

Uses the Microsoft Graph API with app-only authentication (client credentials).
Each conference becomes a native SharePoint list item — sortable, filterable,
and viewable in any SharePoint view without needing to open a file.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ONE-TIME AZURE AD SETUP  (ask your tenant admin if you can't do this)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Go to https://portal.azure.com → Azure Active Directory (Entra ID)
   → App registrations → New registration
   Name: "Morning Edition"  |  Account type: single tenant  |  Register

2. Note the Application (client) ID and Directory (tenant) ID shown on
   the app overview page.

3. Certificates & secrets → New client secret → copy the Value
   (shown once only).

4. API permissions → Add a permission → Microsoft Graph
   → Application permissions → Sites → Sites.ReadWrite.All → Add
   Then click "Grant admin consent for [your org]"

5. Add these secrets to your GitHub repo
   (Settings → Secrets and variables → Actions):

     SHAREPOINT_TENANT_ID      Directory (tenant) ID from step 2
     SHAREPOINT_CLIENT_ID      Application (client) ID from step 2
     SHAREPOINT_CLIENT_SECRET  Secret value from step 3
     SHAREPOINT_SITE_URL       Full SharePoint site URL
                               e.g. https://yourorg.sharepoint.com/sites/yoursite
     SHAREPOINT_LIST_NAME      Name for the list (created automatically if absent)
                               e.g. Morning Edition Conferences

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
TRACKER_FILE = ROOT / "data" / "tracker.json"

# SharePoint list columns created automatically if missing.
# Internal names must be alphanumeric (no spaces).
COLUMNS = [
    {"name": "IssueDate",      "type": "dateTime",  "label": "Issue date"},
    {"name": "IssueIndex",     "type": "number",    "label": "Issue #"},
    {"name": "Verdict",        "type": "text",      "label": "Verdict"},
    {"name": "Domain",         "type": "text",      "label": "Domain"},
    {"name": "ConferenceDate", "type": "text",      "label": "Conference date"},
    {"name": "Location",       "type": "text",      "label": "Location"},
    {"name": "Host",           "type": "text",      "label": "Host"},
    {"name": "WhyItMatters",   "type": "text",      "label": "Why it matters"},
    {"name": "Watch",          "type": "text",      "label": "Watch"},
    {"name": "Source",         "type": "text",      "label": "Source URL"},
]


# ──────────────────────────────────────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────────────────────────────────────

def get_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    try:
        import msal
    except ImportError:
        print("ERROR: msal is not installed. Run: pip install msal")
        sys.exit(1)

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id,
        authority=authority,
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    if "access_token" not in result:
        raise RuntimeError(
            f"Authentication failed: {result.get('error_description', result)}"
        )
    return result["access_token"]


# ──────────────────────────────────────────────────────────────────────────────
# Graph helpers
# ──────────────────────────────────────────────────────────────────────────────

def graph(method: str, path: str, token: str, **kwargs):
    import urllib.request
    import urllib.error

    url = f"https://graph.microsoft.com/v1.0{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = json.dumps(kwargs["json"]).encode() if "json" in kwargs else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"Graph API {method} {path} → {e.code}: {detail}") from e


def get_site_id(site_url: str, token: str) -> str:
    parsed = urlparse(site_url)
    hostname = parsed.netloc
    site_path = parsed.path.rstrip("/")
    data = graph("GET", f"/sites/{hostname}:{site_path}", token)
    return data["id"]


def get_or_create_list(site_id: str, list_name: str, token: str) -> str:
    """Return the list ID, creating the list (and its columns) if it doesn't exist."""
    data = graph("GET", f"/sites/{site_id}/lists?$filter=displayName eq '{list_name}'", token)
    items = data.get("value", [])

    if items:
        list_id = items[0]["id"]
        print(f"Found existing list: {list_name} ({list_id})")
    else:
        print(f"Creating SharePoint list: {list_name}")
        result = graph("POST", f"/sites/{site_id}/lists", token, json={
            "displayName": list_name,
            "columns": [],
            "list": {"template": "genericList"},
        })
        list_id = result["id"]
        _ensure_columns(site_id, list_id, token)

    return list_id


def _ensure_columns(site_id: str, list_id: str, token: str) -> None:
    existing = {
        col["name"]
        for col in graph("GET", f"/sites/{site_id}/lists/{list_id}/columns", token).get("value", [])
    }
    for col in COLUMNS:
        if col["name"] in existing:
            continue
        body: dict = {"name": col["name"], "displayName": col["label"]}
        if col["type"] == "text":
            body["text"] = {}
        elif col["type"] == "number":
            body["number"] = {}
        elif col["type"] == "dateTime":
            body["dateTime"] = {"displayAs": "standard"}
        graph("POST", f"/sites/{site_id}/lists/{list_id}/columns", token, json=body)
        print(f"  Created column: {col['name']}")


def existing_sources(site_id: str, list_id: str, token: str) -> set[str]:
    """Fetch all Source values already in the list for deduplication."""
    sources: set[str] = set()
    path = f"/sites/{site_id}/lists/{list_id}/items?$select=fields&$expand=fields($select=Source)&$top=999"
    while path:
        data = graph("GET", path, token)
        for item in data.get("value", []):
            src = item.get("fields", {}).get("Source", "")
            if src:
                sources.add(src)
        path = data.get("@odata.nextLink", "").replace("https://graph.microsoft.com/v1.0", "") or None
    return sources


def add_item(site_id: str, list_id: str, token: str, row: dict) -> None:
    fields = {
        "Title":          row.get("title", "")[:255],
        "IssueDate":      row.get("issue_date", ""),
        "IssueIndex":     row.get("issue_index", 0),
        "Verdict":        row.get("applies", ""),
        "Domain":         row.get("tag", ""),
        "ConferenceDate": row.get("date", "")[:255],
        "Location":       row.get("location", "")[:255],
        "Host":           row.get("host", "")[:255],
        "WhyItMatters":   row.get("why", "")[:255],
        "Watch":          row.get("watch", "")[:255],
        "Source":         row.get("source", "")[:255],
    }
    graph("POST", f"/sites/{site_id}/lists/{list_id}/items", token, json={"fields": fields})


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    missing = [v for v in (
        "SHAREPOINT_TENANT_ID", "SHAREPOINT_CLIENT_ID",
        "SHAREPOINT_CLIENT_SECRET", "SHAREPOINT_SITE_URL", "SHAREPOINT_LIST_NAME",
    ) if not os.environ.get(v)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "See the script docstring for setup instructions."
        )

    tenant_id     = os.environ["SHAREPOINT_TENANT_ID"]
    client_id     = os.environ["SHAREPOINT_CLIENT_ID"]
    client_secret = os.environ["SHAREPOINT_CLIENT_SECRET"]
    site_url      = os.environ["SHAREPOINT_SITE_URL"]
    list_name     = os.environ["SHAREPOINT_LIST_NAME"]

    if not TRACKER_FILE.exists():
        print("No tracker.json found — nothing to upload.")
        return

    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        tracker = json.load(f)

    if not tracker:
        print("Tracker is empty — nothing to upload.")
        return

    print("Authenticating with Microsoft Graph…")
    token = get_token(tenant_id, client_id, client_secret)

    print(f"Locating SharePoint site: {site_url}")
    site_id = get_site_id(site_url, token)

    list_id = get_or_create_list(site_id, list_name, token)

    print("Checking for existing items…")
    already_uploaded = existing_sources(site_id, list_id, token)

    new_rows = [r for r in tracker if r.get("source") not in already_uploaded]
    print(f"Uploading {len(new_rows)} new item(s) (skipping {len(tracker) - len(new_rows)} already present)…")

    for row in new_rows:
        add_item(site_id, list_id, token, row)
        print(f"  + {row.get('title', '')[:60]}")

    print(f"Done — SharePoint list '{list_name}' now has entries for {len(tracker)} conference(s).")


if __name__ == "__main__":
    main()
