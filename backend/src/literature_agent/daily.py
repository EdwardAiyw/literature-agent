from __future__ import annotations

import argparse
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from .config import Settings
from .db import Database
from .runner import run_subscription


def due_subscriptions(database: Database, subscriptions: list[dict], now_utc: datetime | None = None) -> list[dict]:
    """Return subscriptions whose local schedule has passed and have not run today."""
    current_utc = now_utc or datetime.now(timezone.utc)
    if current_utc.tzinfo is None:
        current_utc = current_utc.replace(tzinfo=timezone.utc)
    due: list[dict] = []
    for subscription in subscriptions:
        zone = ZoneInfo(subscription["timezone"])
        local_now = current_utc.astimezone(zone)
        hour, minute = (int(part) for part in subscription["schedule_time"].split(":"))
        scheduled = datetime.combine(local_now.date(), time(hour, minute), tzinfo=zone)
        if local_now < scheduled:
            continue
        local_day_start = datetime.combine(local_now.date(), time.min, tzinfo=zone)
        if database.has_run_since(subscription["task_id"], local_day_start.astimezone(timezone.utc).isoformat()):
            continue
        due.append(subscription)
    return due


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Literature Agent subscriptions")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--run-subscription", metavar="ID")
    group.add_argument("--run-enabled", action="store_true")
    group.add_argument("--run-due", action="store_true", help="run enabled subscriptions due in their configured timezone")
    parser.add_argument("--no-send", action="store_true", help="run retrieval without sending email")
    args = parser.parse_args()

    settings = Settings.from_env()
    database = Database(settings.db_path)
    try:
        subscriptions = [database.get_subscription(args.run_subscription)] if args.run_subscription else database.list_subscriptions(enabled_only=True)
        subscriptions = [item for item in subscriptions if item]
        if args.run_due:
            subscriptions = due_subscriptions(database, subscriptions)
            if not subscriptions:
                print("No subscriptions are due")
                return 0
        elif not subscriptions:
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
    finally:
        database.close()


if __name__ == "__main__":
    raise SystemExit(main())
