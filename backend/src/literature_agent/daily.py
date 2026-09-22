from __future__ import annotations

import argparse

from .config import Settings
from .db import Database
from .runner import run_subscription


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Literature Agent subscriptions")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-subscription", metavar="ID")
    group.add_argument("--run-enabled", action="store_true")
    parser.add_argument("--no-send", action="store_true", help="run retrieval without sending email")
    args = parser.parse_args()

    settings = Settings.from_env()
    database = Database(settings.db_path)
    subscriptions = [database.get_subscription(args.run_subscription)] if args.run_subscription else database.list_subscriptions(enabled_only=True)
    subscriptions = [item for item in subscriptions if item]
    if not subscriptions:
        parser.error("No matching subscription found")
    exit_code = 0
    for subscription in subscriptions:
        try:
            result = run_subscription(settings, database, subscription, send_email=not args.no_send)
            delivery = result.get("delivery") or {}
            detail = f" error={delivery.get('error')}" if delivery.get("error") else ""
            print(f"{subscription['id']}: run={result.get('id')} status={result.get('status')} delivery={delivery.get('status', 'skipped')}{detail}")
            if result.get("status") != "completed" or result.get("delivery", {}).get("status") == "failed":
                exit_code = 1
        except Exception as exc:
            print(f"{subscription['id']}: failed: {type(exc).__name__}: {exc}")
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
