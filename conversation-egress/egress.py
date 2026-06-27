"""Egress agent conversation logs into MongoDB.

Reads the JSON conversation logs produced by the Claude and Antigravity CLI
agents and pushes them into the ``logs`` collection of the ``vibe_coding``
database. A single ``google_hackathon`` user is ensured in the ``user``
collection and its ``user_id`` is stamped onto every log document.

Connection details are read from a ``.env`` file:

    MONGODB_URI=mongodb+srv://user:pass@cluster.example.mongodb.net/
    DB_NAME=vibe_coding

Usage:
    uv run egress.py            # read logs and push to MongoDB
    uv run egress.py --dry-run  # parse logs and report counts, no DB writes
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

# Repo root is the parent of the directory holding this script.
REPO_ROOT = Path(__file__).resolve().parent.parent

# Map each agent log directory to the cli_agent label it should be tagged with.
LOG_SOURCES = {
    REPO_ROOT / ".claude" / "agent_logs": "claude",
    REPO_ROOT / ".agents" / "agent_logs": "antigravity",
}

# Files in the log directories that are not conversation logs.
IGNORED_FILES = {"debug_payload.json"}

USER_NAME = "google_hackathon"


def load_logs() -> list[dict]:
    """Read every conversation log JSON file and return enriched documents.

    Each file holds a JSON array of log entries; every entry becomes one
    document tagged with ``cli_agent`` and ``session_id`` (the file name).
    """
    documents: list[dict] = []

    for log_dir, cli_agent in LOG_SOURCES.items():
        if not log_dir.is_dir():
            print(f"[warn] missing log directory, skipping: {log_dir}")
            continue

        for json_file in sorted(log_dir.glob("*.json")):
            if json_file.name in IGNORED_FILES:
                continue

            session_id = json_file.stem  # file name without the .json extension
            try:
                with json_file.open(encoding="utf-8") as fh:
                    payload = json.load(fh)
            except (json.JSONDecodeError, OSError) as exc:
                print(f"[warn] could not read {json_file}: {exc}")
                continue

            # A file is normally an array of entries; tolerate a single object.
            entries = payload if isinstance(payload, list) else [payload]

            for idx, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    entry = {"value": entry}
                doc = dict(entry)
                doc["cli_agent"] = cli_agent
                doc["session_id"] = session_id
                doc["entry_index"] = idx  # position within the session file
                documents.append(doc)

            print(
                f"[ok] {json_file.name}: {len(entries)} entries "
                f"(cli_agent={cli_agent})"
            )

    return documents


def ensure_user(db) -> str:
    """Return the user_id for the google_hackathon user, creating it if absent."""
    users = db["users"]
    existing = users.find_one({"username": USER_NAME})
    if existing:
        print(f"[ok] user '{USER_NAME}' already exists (user_id={existing['user_id']})")
        return existing["user_id"]

    user_id = str(uuid.uuid4())
    users.insert_one(
        {
            "user_id": user_id,
            "username": USER_NAME,
            "email": "",
            "role": "viewer",
            "created_at": datetime.now(timezone.utc),
        }
    )
    print(f"[ok] created user '{USER_NAME}' (user_id={user_id})")
    return user_id


def push_logs(db, documents: list[dict], user_id: str) -> None:
    """Add only log entries that aren't already stored.

    Each entry is keyed by (session_id, cli_agent, entry_index). Existing
    documents are left untouched and only new entries are inserted, so the
    script is safe to re-run and picks up newly appended conversation logs.
    """
    logs = db["logs"]

    if not documents:
        print("[warn] no log documents to insert")
        return

    operations = []
    for doc in documents:
        doc["user_id"] = user_id
        key = {
            "session_id": doc["session_id"],
            "cli_agent": doc["cli_agent"],
            "entry_index": doc["entry_index"],
        }
        payload = {k: v for k, v in doc.items() if k not in key}
        set_on_insert_payload = {k: v for k, v in payload.items() if k != "completed At"}
        update_doc = {"$setOnInsert": set_on_insert_payload}
        if "completed At" in payload:
            update_doc["$set"] = {"completed At": payload["completed At"]}
        operations.append(UpdateOne(key, update_doc, upsert=True))

    result = logs.bulk_write(operations, ordered=False)
    skipped = len(documents) - result.upserted_count
    print(f"[ok] added {result.upserted_count} new log documents ({skipped} already present, skipped or updated)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="parse logs and report counts without connecting to MongoDB",
    )
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parent / ".env")

    documents = load_logs()
    print(f"[info] collected {len(documents)} log documents total")

    if args.dry_run:
        print("[info] dry run: skipping MongoDB connection and writes")
        return 0

    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("DB_NAME", "vibe_coding")
    if not uri:
        print("[error] MONGODB_URI is not set in the .env file", file=sys.stderr)
        return 1

    client = MongoClient(uri)
    try:
        client.admin.command("ping")  # fail fast on bad credentials/URI
        db = client[db_name]
        user_id = ensure_user(db)
        push_logs(db, documents, user_id)
    finally:
        client.close()

    print("[done] egress complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
