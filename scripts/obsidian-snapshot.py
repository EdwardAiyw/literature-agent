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
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        metrics = [json.loads(row[0]) for row in connection.execute("SELECT payload FROM journal_metrics")] if "journal_metrics" in tables else []
        deliveries = connection.execute(
            "SELECT id, run_id, subject, sent_at FROM deliveries "
            "WHERE subscription_id=? AND kind='digest' AND status='sent' "
            "AND sent_at>=? ORDER BY sent_at, id", (subscription, since),
        ).fetchall()
        result = []
        for delivery in deliveries:
            artifacts = {r["node"]: json.loads(r["payload"]) for r in connection.execute(
                "SELECT node, payload FROM run_artifacts WHERE run_id=? AND node IN (?, ?, ?, ?)",
                (delivery["run_id"], "email_digest." + delivery["id"], "subscription_snapshot", "retrieval", "dedupe"),
            )} if "run_artifacts" in tables else {}
            archive = artifacts.get("email_digest." + delivery["id"])
            papers = []
            stored = [{**json.loads(r["payload"]), "id": r["id"]} for r in connection.execute("SELECT id, payload FROM papers WHERE run_id=? ORDER BY json_extract(payload, '$.relevance_score') DESC", (delivery["run_id"],))]
            for original in archive.get("papers", stored) if archive else stored:
                paper = dict(original)
                imports = connection.execute(
                    "SELECT destination, payload FROM zotero_imports WHERE paper_id=? ORDER BY updated_at DESC", (paper["id"],),
                ).fetchall()
                paper["obsidian_zotero"] = [{"destination": json.loads(r["destination"]), **json.loads(r["payload"])} for r in imports]
                papers.append(paper)
            result.append({**dict(delivery), "papers": papers, "email_archive": archive,
                           "subscription": artifacts.get("subscription_snapshot", {}).get("subscription", {}),
                           "diagnostics": artifacts.get("retrieval", {}).get("sources", {}), "dedupe": artifacts.get("dedupe", {})})
        return {"deliveries": result, "journal_metrics": metrics}
    finally:
        connection.close()


if __name__ == "__main__":
    print(json.dumps(snapshot(*sys.argv[1:]), ensure_ascii=True))
