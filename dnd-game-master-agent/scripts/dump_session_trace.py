#!/usr/bin/env python3
"""Dump an ADK session trace from the local `.adk/session.db` for investigation.

ADK's DatabaseSessionService persists every event (LLM thoughts, function
calls, function responses, state deltas) to a local SQLite db. MongoDB only
holds the final committed campaign state, so to understand *why* a model made a
decision — e.g. why `output_agent` skipped `update_campaign` — you need the
event stream, not the DB snapshot.

Usage:
    python scripts/dump_session_trace.py                  # latest session, pretty
    python scripts/dump_session_trace.py --list           # list sessions
    python scripts/dump_session_trace.py --session <id>   # a specific session
    python scripts/dump_session_trace.py --jsonl out.jsonl  # export one event per line
    python scripts/dump_session_trace.py --db path/to/session.db

Dependency-free (stdlib sqlite3 + json only).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sqlite3
import sys
from pathlib import Path

# Default db: <repo>/app/.adk/session.db, resolved relative to this file so the
# script works regardless of the current working directory.
_DEFAULT_DB = Path(__file__).resolve().parent.parent / "app" / ".adk" / "session.db"

_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_MAGENTA = "\033[35m"


def _parse_ts(epoch, fmt: str) -> str:
    if isinstance(epoch, str):
        try:
            return _dt.datetime.fromisoformat(epoch).strftime(fmt)
        except ValueError:
            pass
    return _dt.datetime.fromtimestamp(float(epoch), _dt.timezone.utc).strftime(fmt)


def _ts(epoch) -> str:
    return _parse_ts(epoch, "%H:%M:%S")


def _color(text: str, code: str, enabled: bool) -> str:
    return f"{code}{text}{_RESET}" if enabled else text


def _connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        sys.exit(f"session.db not found at {db_path}\n(run the agent at least once, or pass --db)")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def list_sessions(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT s.id, s.user_id, s.create_time, s.update_time,
               (SELECT COUNT(*) FROM events e WHERE e.session_id = s.id) AS n_events
        FROM sessions s
        ORDER BY s.update_time DESC
        """
    ).fetchall()
    if not rows:
        print("No sessions found.")
        return
    print(f"{'SESSION ID':38}  {'USER':10}  {'UPDATED (UTC)':19}  EVENTS")
    for r in rows:
        updated = _parse_ts(r["update_time"], "%Y-%m-%d %H:%M:%S")
        print(f"{r['id']:38}  {r['user_id']:10}  {updated:19}  {r['n_events']}")


def _latest_session_id(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT id FROM sessions ORDER BY update_time DESC LIMIT 1"
    ).fetchone()
    return row["id"] if row else None


def _iter_events(conn: sqlite3.Connection, session_id: str, last_only: bool = False):
    rows = conn.execute(
        "SELECT id, invocation_id, timestamp, event_data FROM events "
        "WHERE session_id = ? ORDER BY timestamp, id",
        (session_id,),
    ).fetchall()
    if last_only and rows:
        last_inv_id = rows[-1]["invocation_id"]
        rows = [r for r in rows if r["invocation_id"] == last_inv_id]
    return rows


def dump_jsonl(conn: sqlite3.Connection, session_id: str, out_path: Path, last_only: bool = False) -> int:
    n = 0
    with out_path.open("w") as fh:
        for row in _iter_events(conn, session_id, last_only):
            ev = json.loads(row["event_data"])
            ev.setdefault("id", row["id"])
            ev.setdefault("invocation_id", row["invocation_id"])
            ev.setdefault("timestamp", row["timestamp"])
            fh.write(json.dumps(ev) + "\n")
            n += 1
    return n


def _summarize_part(part: dict, color: bool) -> list[str]:
    """Render one content part into one or more annotated lines."""
    lines: list[str] = []
    fc = part.get("function_call")
    fr = part.get("function_response")
    text = part.get("text")
    is_thought = part.get("thought")

    if fc:
        name = fc.get("name", "?")
        args = fc.get("args", {})
        lines.append(
            _color(f"    🛠  FUNCTION_CALL {name}(", _GREEN, color)
            + json.dumps(args, default=str)
            + _color(")", _GREEN, color)
        )
    if fr:
        name = fr.get("name", "?")
        resp = json.dumps(fr.get("response", fr), default=str)
        # if len(resp) > 400:
        #     resp = resp[:400] + "…"
        lines.append(_color(f"    ⤷  FUNCTION_RESPONSE {name}: ", _MAGENTA, color) + resp)
    if text:
        label = "💭 THOUGHT" if is_thought else "💬 TEXT"
        code = _YELLOW if is_thought else ""
        body = text.strip()
        # if len(body) > 1500:
        #     body = body[:1500] + "…[truncated]"
        prefix = _color(f"    {label}: ", code, color)
        # indent continuation lines for readability
        indented = body.replace("\n", "\n      ")
        lines.append(prefix + indented)
    return lines


def dump_pretty(conn: sqlite3.Connection, session_id: str, color: bool, last_only: bool = False) -> None:
    sess = conn.execute(
        "SELECT user_id, create_time, state FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if sess is None:
        sys.exit(f"No session with id {session_id!r}. Try --list.")

    rows = _iter_events(conn, session_id, last_only)
    print(_color("=" * 78, _DIM, color))
    print(_color(f"SESSION {session_id}", _BOLD, color))
    print(f"  user={sess['user_id']}  created={_ts(sess['create_time'])}  events={len(rows)}")
    print(_color("=" * 78, _DIM, color))

    tool_calls = 0
    last_invocation = None
    for row in rows:
        ev = json.loads(row["event_data"])
        if row["invocation_id"] != last_invocation:
            last_invocation = row["invocation_id"]
            print(_color(f"\n── invocation {last_invocation} ──", _DIM, color))

        author = ev.get("author", "?")
        head = f"[{_ts(row['timestamp'])}] " + _color(author, _CYAN, color)
        print(f"\n{head}")

        for part in (ev.get("content") or {}).get("parts") or []:
            for line in _summarize_part(part, color):
                print(line)
            if part.get("function_call"):
                tool_calls += 1

        actions = ev.get("actions") or {}
        delta = actions.get("state_delta") or {}
        if delta:
            keys = ", ".join(delta.keys())
            tf = delta.get("tools_fired", "—")
            print(_color(f"    ◆ state_delta: {keys}  | tools_fired={tf}", _DIM, color))

    print(_color("\n" + "=" * 78, _DIM, color))
    print(f"Summary: {len(rows)} events, {tool_calls} function call(s) emitted.")
    if tool_calls == 0:
        print(
            _color(
                "⚠  No tool/function calls in this session — inspect the 💭 THOUGHT "
                "parts above to see the model's reasoning for skipping them.",
                _YELLOW,
                color,
            )
        )


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=_DEFAULT_DB, help="Path to session.db")
    ap.add_argument("--session", help="Session id (default: most recently updated)")
    ap.add_argument("--list", action="store_true", help="List sessions and exit")
    ap.add_argument("--jsonl", type=Path, metavar="PATH", help="Export events to JSONL instead of pretty-printing")
    ap.add_argument("--last", action="store_true", help="Dump only the last invocation of the session")
    ap.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    args = ap.parse_args(argv)

    conn = _connect(args.db)
    try:
        if args.list:
            list_sessions(conn)
            return

        session_id = args.session or _latest_session_id(conn)
        if not session_id:
            sys.exit("No sessions in db.")

        if args.jsonl:
            n = dump_jsonl(conn, session_id, args.jsonl, args.last)
            print(f"Wrote {n} events for session {session_id} → {args.jsonl}")
            return

        color = sys.stdout.isatty() and not args.no_color
        dump_pretty(conn, session_id, color, args.last)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
