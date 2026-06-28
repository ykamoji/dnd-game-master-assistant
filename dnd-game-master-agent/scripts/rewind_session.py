#!/usr/bin/env python3
"""Rewind a session to a state before a specific invocation.

Usage:
    python scripts/rewind_session.py <session_id> <invocation_id>
"""

import argparse
import sys
import json
import sqlite3
from pathlib import Path

_DEFAULT_DB = Path(__file__).resolve().parent.parent / "app" / ".adk" / "session.db"

def dict_deep_update(base: dict, update: dict) -> dict:
    for k, v in update.items():
        if isinstance(v, dict) and k in base and isinstance(base[k], dict):
            dict_deep_update(base[k], v)
        else:
            base[k] = v
    return base

def rewind(session_id: str, invocation_id: str, db_path: Path):
    if not db_path.exists():
        sys.exit(f"Database not found at {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=rw", uri=True)
    conn.row_factory = sqlite3.Row

    try:
        # 1. Verify session exists
        session_row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not session_row:
            sys.exit(f"Session {session_id!r} not found in database.")

        # 2. Find the timestamp of the target invocation
        target_row = conn.execute(
            "SELECT timestamp FROM events WHERE session_id = ? AND invocation_id = ? ORDER BY timestamp ASC LIMIT 1",
            (session_id, invocation_id)
        ).fetchone()

        if not target_row:
            sys.exit(f"Invocation {invocation_id!r} not found in session {session_id!r}.")

        target_ts = target_row["timestamp"]

        # 3. Delete all events from this point forward
        deleted_count = conn.execute(
            "DELETE FROM events WHERE session_id = ? AND timestamp >= ?",
            (session_id, target_ts)
        ).rowcount
        
        print(f"Deleted {deleted_count} events from invocation {invocation_id} onwards.")

        # 4. Rebuild the session state from remaining events
        remaining_events = conn.execute(
            "SELECT event_data FROM events WHERE session_id = ? ORDER BY timestamp ASC, id ASC",
            (session_id,)
        ).fetchall()

        rebuilt_state = {}
        for row in remaining_events:
            event = json.loads(row["event_data"])
            actions = event.get("actions", {})
            state_delta = actions.get("state_delta", {})
            if state_delta:
                dict_deep_update(rebuilt_state, state_delta)

        # 5. Update the session table with the rebuilt state
        conn.execute(
            "UPDATE sessions SET state = ?, update_time = ? WHERE id = ?",
            (json.dumps(rebuilt_state), target_ts, session_id)
        )
        
        conn.commit()
        print("✅ Session successfully rewound and state rebuilt.")

    except Exception as e:
        conn.rollback()
        sys.exit(f"❌ Failed to rewind session: {e}")
    finally:
        conn.close()

def main():
    parser = argparse.ArgumentParser(description="Rewind a session to before a specific invocation.")
    parser.add_argument("session_id", help="The ID of the session to rewind")
    parser.add_argument("invocation_id", help="The invocation ID to rewind before (exclusive)")
    parser.add_argument("--db", type=Path, default=_DEFAULT_DB, help="Path to session.db")
    
    args = parser.parse_args()
    rewind(args.session_id, args.invocation_id, args.db)

if __name__ == "__main__":
    main()
