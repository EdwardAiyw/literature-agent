"""Migrate existing legacy Zotero settings without exposing credentials or writing to Zotero."""
from __future__ import annotations

import argparse
from pathlib import Path

import httpx

from literature_agent.config import ConfigManager, Settings
from literature_agent.schemas import SettingsUpdate
from literature_agent.zotero import ZoteroClient, ZoteroError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("legacy_env", type=Path)
    args = parser.parse_args()
    legacy = {}
    for line in args.legacy_env.read_text(encoding="utf-8-sig").splitlines():
        if line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip().startswith("ZOTERO_"):
            legacy[key.strip().lower()] = value.strip().strip('"').strip("'")
    allowed = {"zotero_library_id", "zotero_library_type", "zotero_collection_key", "zotero_collection_name", "zotero_api_key"}
    payload = SettingsUpdate.model_validate({key: value for key, value in legacy.items() if key in allowed}).model_dump(exclude_none=True)
    manager = ConfigManager(Settings.from_env())
    if manager.get().zotero_api_key or manager.get().zotero_library_id:
        raise SystemExit("Zotero already configured; existing settings were preserved.")
    from dataclasses import replace
    candidate = replace(manager.get(), **payload)
    try:
        with httpx.Client(timeout=30) as client:
            ZoteroClient(candidate, client).check_connection()
    except ZoteroError as exc:
        raise SystemExit(str(exc)) from exc
    api_key = payload.pop("zotero_api_key")
    manager.update(payload, {"zotero_api_key": api_key})
    print("Zotero connection verified; configuration migrated. API key stored in Windows Credential Manager. Restart the service.")


if __name__ == "__main__":
    main()
