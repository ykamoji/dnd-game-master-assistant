from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import sqlite3
import json
from pathlib import Path

from app.db import check_health
from app.tools import TOOL_FUNCTIONS

router = APIRouter()

class PathsRequest(BaseModel):
    paths: List[str]

class DescriptionRequest(BaseModel):
    description: str

class UpdateCampaignRequest(BaseModel):
    campaign_name: str = "tomb-of-annihilation"
    summary: Optional[str] = None
    progress: Optional[float] = None
    scene: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[dict] = None
    initiative: Optional[List[str]] = None
    party: Optional[dict] = None

@router.get("/health/db")
def health_db():
    result = check_health()
    if result["status"] == "ok":
        return result
    raise HTTPException(status_code=503, detail=result)

@router.get("/campaign/{campaign_id}")
def api_get_campaign(campaign_id: str, include_history: bool = False):
    state = TOOL_FUNCTIONS["get_campaign"](campaign_id, include_history)
    if not state:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return state

@router.get("/state/{campaign_id}")
def api_get_state(campaign_id: str):
    state = TOOL_FUNCTIONS["get_state"](campaign_id)
    if not state:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return state

@router.post("/campaign/{campaign_id}/update")
def api_update_campaign(campaign_id: str, req: UpdateCampaignRequest):
    return TOOL_FUNCTIONS["update_campaign"](
        campaign_id=campaign_id,
        campaign_name=req.campaign_name,
        summary=req.summary,
        progress=req.progress,
        scene=req.scene,
        description=req.description,
        metadata=req.metadata,
        initiative=req.initiative,
        party=req.party
    )

@router.post("/tools/fetch_campaign_files")
def api_fetch_campaign_files(req: PathsRequest):
    return TOOL_FUNCTIONS["fetch_campaign_files"](req.paths)

@router.get("/tools/lookup_character/{name}")
def api_lookup_character(name: str):
    res = TOOL_FUNCTIONS["lookup_character"](name)
    if not res:
        raise HTTPException(status_code=404, detail="Character not found")
    return res

@router.get("/tools/lookup_character_resource/{resource_type}/{name}")
def api_lookup_character_resource(resource_type: str, name: str):
    if resource_type not in ["monsters", "spells", "classes", "armor", "weapons", "magicitems"]:
        raise HTTPException(status_code=400, detail="Invalid resource_type")
    res = TOOL_FUNCTIONS["lookup_character_resource"](resource_type, name)
    if not res:
        raise HTTPException(status_code=404, detail="Resource not found")
    return res

@router.post("/tools/get_asset_url")
def api_get_asset_url(req: DescriptionRequest):
    res = TOOL_FUNCTIONS["get_asset_url"](req.description)
    if "error" in res:
        raise HTTPException(status_code=404, detail=res["error"])
    return res

def dict_deep_update(base: dict, update: dict) -> dict:
    for k, v in update.items():
        if isinstance(v, dict) and k in base and isinstance(base[k], dict):
            dict_deep_update(base[k], v)
        else:
            base[k] = v
    return base

@router.delete("/session/{session_id}")
def api_delete_last_invocation(session_id: str):
    db_path = Path(__file__).resolve().parent / ".adk" / "session.db"
    if not db_path.exists():
        raise HTTPException(status_code=500, detail="Database not found")

    conn = sqlite3.connect(f"file:{db_path}?mode=rw", uri=True)
    conn.row_factory = sqlite3.Row

    try:
        # 1. Verify session exists
        session_row = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")

        # 2. Find the last invocation_id
        last_event = conn.execute(
            "SELECT invocation_id, timestamp FROM events WHERE session_id = ? ORDER BY timestamp DESC LIMIT 1",
            (session_id,)
        ).fetchone()

        if not last_event:
            raise HTTPException(status_code=404, detail="No events found for session")

        last_invocation_id = last_event["invocation_id"]

        # 3. Delete ONLY the events for the last invocation
        deleted_count = conn.execute(
            "DELETE FROM events WHERE session_id = ? AND invocation_id = ?",
            (session_id, last_invocation_id)
        ).rowcount

        # 4. Rebuild the session state from all remaining prior events
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
        new_last_event = conn.execute(
            "SELECT timestamp FROM events WHERE session_id = ? ORDER BY timestamp DESC LIMIT 1",
            (session_id,)
        ).fetchone()
        
        update_ts = new_last_event["timestamp"] if new_last_event else last_event["timestamp"]

        conn.execute(
            "UPDATE sessions SET state = ?, update_time = ? WHERE id = ?",
            (json.dumps(rebuilt_state), update_ts, session_id)
        )
        
        conn.commit()
        return {"status": "success", "deleted_invocation_id": last_invocation_id, "deleted_events": deleted_count}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

