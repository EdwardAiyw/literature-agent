"""Read-only server snapshot. Stdlib only; may run via `ssh ... python3 -`."""
import json
import sqlite3
import sys
from pathlib import Path


def snapshot(database, subscription, since):
    connection = sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        deliveries = connection.execute(
            "SELECT id, run_id, subject, sent_at FROM deliveries "
            "WHERE subscription_id=? AND kind='digest' AND status='sent' "
            "AND sent_at>=? ORDER BY sent_at, id", (subscription, since),
        ).fetchall()
        result = []
        for delivery in deliveries:
            papers = []
            for row in connection.execute("SELECT id, payload FROM papers WHERE run_id=? ORDER BY id", (delivery["run_id"],)):
                paper = json.loads(row["payload"])
                paper["id"] = row["id"]
                imports = connection.execute(
                    "SELECT destination, payload FROM zotero_imports WHERE paper_id=? ORDER BY updated_at DESC", (row["id"],),
                ).fetchall()
                paper["obsidian_zotero"] = [{"destination": json.loads(r["destination"]), **json.loads(r["payload"])} for r in imports]
                papers.append(paper)
            result.append({**dict(delivery), "papers": papers})
        return {"deliveries": result}
    finally:
        connection.close()


if __name__ == "__main__":
    print(json.dumps(snapshot(*sys.argv[1:]), ensure_ascii=True))
