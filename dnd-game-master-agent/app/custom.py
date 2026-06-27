from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
