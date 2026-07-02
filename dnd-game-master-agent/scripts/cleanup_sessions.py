#!/usr/bin/env python3
import sqlite3
import argparse
import os

def main():
    parser = argparse.ArgumentParser(description="Cleanup sessions with few events.")
    parser.add_argument("--db", default="app/.adk/session.db", help="Path to session database")
    parser.add_argument("--threshold", type=int, default=8, help="Delete sessions with strictly fewer than this many events")
    args = parser.parse_args()

    # Make path relative to this script if run from repo root
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if args.db == "app/.adk/session.db":
        db_path = os.path.join(base_dir, "app", ".adk", "session.db")
    else:
        db_path = os.path.abspath(args.db)

    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Find sessions with < threshold events
    c.execute("""
        SELECT id, (SELECT COUNT(*) FROM events e WHERE e.session_id = s.id) as ev_count
        FROM sessions s
    """)
    all_rows = c.fetchall()
    
    # Filter for sessions with fewer than the threshold
    to_delete = [r for r in all_rows if r[1] < args.threshold]
    
    if not to_delete:
        print(f"No sessions found with fewer than {args.threshold} events.")
        return
        
    print(f"Found {len(to_delete)} sessions to delete:")
    for row in to_delete:
        print(f"  Session {row[0]} (events: {row[1]})")

    session_ids = [r[0] for r in to_delete]
    placeholders = ",".join("?" * len(session_ids))
    
    # Delete events first, then sessions
    c.execute(f"DELETE FROM events WHERE session_id IN ({placeholders})", session_ids)
    events_deleted = c.rowcount
    
    c.execute(f"DELETE FROM sessions WHERE id IN ({placeholders})", session_ids)
    sessions_deleted = c.rowcount

    conn.commit()
    conn.close()

    print(f"\nCleanup complete. Deleted {events_deleted} events across {sessions_deleted} sessions.")

if __name__ == "__main__":
    main()
