import json
import logging
import os
import sqlite3
import asyncio
import re
from typing import Any, Optional, Dict, List

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger("dnd.events")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db_path = os.path.join(AGENT_DIR, "app", ".adk", "session.db")

router = APIRouter()

# --- SSE API Schemas ---
class FunctionCall(BaseModel):
    name: str
    args: Dict[str, Any]

class FunctionResponse(BaseModel):
    name: str
    response: Any

class Part(BaseModel):
    text: Optional[Any] = None
    thought: Optional[bool] = None
    function_call: Optional[FunctionCall] = None
    function_response: Optional[FunctionResponse] = None

class Content(BaseModel):
    parts: List[Part] = []

class StateDelta(BaseModel):
    tools_fired: Any = None
    model_config = ConfigDict(extra="allow")

class Actions(BaseModel):
    state_delta: Optional[StateDelta] = None
    model_config = ConfigDict(extra="allow")

class SessionEvent(BaseModel):
    id: str
    invocation_id: str
    timestamp: float
    author: str = "?"
    content: Optional[Content] = None
    actions: Optional[Actions] = None
# -----------------------

def extract_json_from_string(text: Any) -> Any:
    if not isinstance(text, str):
        return text
    
    # Try to extract from markdown code blocks like ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", text, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        json_str = text.strip()
    
    if json_str.startswith("{") or json_str.startswith("["):
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
    return text

def parse_event_row(row: sqlite3.Row) -> Optional[SessionEvent]:
    ev_data = json.loads(row["event_data"])
    author = ev_data.get("author", "?")

    if author in ("output_agent",):
        delta = ev_data.get("actions") and ev_data.get("actions").get("state_delta")
        if not delta or not delta.get("tools_fired") or len(delta.get("tools_fired")) == 0:
            return None
    
    if author in ("user", "campaign_agent", "npc_dialogue_agent", "action_agent"):
        return None

    # if author in ("dnd_game_master_agent",):
    #     delta = ev_data.get("actions", {}).get("state_delta", {})
    #     if not delta or delta.get("intent") or "update_campaign" in delta.get("tools_fired", []):
    #         return None
        
    if author in ("intent_classifier", "campaign_executor", "action_executor", "npc_executor", "llm_evaluator"):
        parts = ev_data.get("content", {}).get("parts")
        if not parts:
            return None
    
    # Parse embedded JSON in state_delta
    actions = ev_data.get("actions")
    if actions and isinstance(actions.get("state_delta"), dict):
        sd = actions["state_delta"]
        for draft_key in ["campaign_draft", "action_draft", "npc_draft", "campaign_result", "action_result", "npc_result"]:
            if draft_key in sd:
                sd[draft_key] = extract_json_from_string(sd[draft_key])
    
    # Parse embedded JSON in content parts
    content = ev_data.get("content")
    if content and isinstance(content.get("parts"), list):
        for p in content["parts"]:
            if "text" in p:
                p["text"] = extract_json_from_string(p["text"])
            if "function_response" in p and isinstance(p["function_response"], dict):
                fr = p["function_response"]
                if isinstance(fr.get("response"), dict) and "result" in fr["response"]:
                    fr["response"]["result"] = extract_json_from_string(fr["response"]["result"])
    
    event_dict = {
        "id": row["id"],
        "invocation_id": row["invocation_id"],
        "timestamp": row["timestamp"],
        "author": author,
        "content": ev_data.get("content"),
        "actions": ev_data.get("actions"),
    }
    
    try:
        return SessionEvent(**event_dict)
    except Exception as e:
        logger.error(f"Failed to validate event {row['id']}: {e}")
        return None

@router.get("/ambient/sessions/{session_id}/invocations/{invocation_id}/events")
async def get_invocation_events(session_id: str, invocation_id: str) -> List[SessionEvent]:
    """Fetch all events for a specific invocation ID."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, invocation_id, timestamp, event_data FROM events "
            "WHERE session_id = ? AND invocation_id = ? ORDER BY timestamp, id",
            (session_id, invocation_id),
        ).fetchall()
        
        events = []
        for row in rows:
            event_obj = parse_event_row(row)
            if event_obj:
                events.append(event_obj)
        
        return events
    finally:
        conn.close()


@router.get("/ambient/sessions/{session_id}/stream")
async def stream_session_events(session_id: str):
    """
    Server-Sent Events endpoint to stream the session trace from the local DB.
    Mimics the behavior of `dump_session_trace.py` but yields full JSON strings.
    """
    def get_events():
        # First, find the latest invocation_id for this session
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            latest_row = conn.execute(
                "SELECT invocation_id FROM events WHERE session_id = ? ORDER BY timestamp DESC, id DESC LIMIT 1",
                (session_id,)
            ).fetchone()
            
            if not latest_row:
                return []
                
            latest_invocation_id = latest_row["invocation_id"]
            
            # Then query all events for that specific invocation
            return conn.execute(
                "SELECT id, invocation_id, timestamp, event_data FROM events "
                "WHERE session_id = ? AND invocation_id = ? ORDER BY timestamp, id",
                (session_id, latest_invocation_id),
            ).fetchall()
        finally:
            conn.close()


    async def event_generator():
        seen_ids = set()
        while True:
            try:
                rows = get_events()
                
                for row in rows:
                    if row["id"] in seen_ids:
                        continue
                    seen_ids.add(row["id"])
                    
                    event_obj = parse_event_row(row)
                    if not event_obj:
                        continue
                    
                    try:
                        # exclude_none keeps the output clean and similar to the raw trace
                        data_str = event_obj.model_dump_json(exclude_none=True)
                    except Exception as e:
                        logger.error(f"Failed to dump event {row['id']}: {e}")
                        continue
                    
                    yield f"data: {data_str}\n\n"
                
                # Sleep briefly before polling the db again
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in SSE stream: {e}")
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
