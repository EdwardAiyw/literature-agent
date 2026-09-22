from datetime import datetime, timezone

from literature_agent.daily import due_subscriptions
from literature_agent.db import Database


def _subscription(database: Database, name: str, schedule_time: str) -> dict:
    task = database.create_task({"name": name, "topic": name})
    return database.create_subscription(task["id"], {
        "name": name,
        "topic": name,
        "recipient": "researcher@example.org",
        "schedule_time": schedule_time,
        "timezone": "Asia/Hong_Kong",
        "target_count": 10,
        "sources": ["openalex"],
        "enabled": True,
    })


def test_due_subscriptions_honor_local_time_and_run_once_per_day(tmp_path):
    database = Database(tmp_path / "daily.db")
    morning = _subscription(database, "Morning", "08:00")
    afternoon = _subscription(database, "Afternoon", "14:00")
    now_utc = datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc)  # 09:00 in Hong Kong

    assert [item["id"] for item in due_subscriptions(database, [morning, afternoon], now_utc)] == [morning["id"]]

    run = database.create_run(morning["task_id"], total_steps=6)
    database.update_run(run["id"], started_at="2026-09-22T00:05:00+00:00")
    assert due_subscriptions(database, [morning, afternoon], now_utc) == []
    database.close()
