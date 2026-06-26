import datetime
from typing import Dict, List, Optional

from app.db import get_campaigns_col

def get_campaign(campaign_id: str, include_history: bool = False) -> Optional[Dict]:
    """Fetch the campaign document from MongoDB.
    
    Args:
        campaign_id: The ID of the campaign.
        include_history: If True, returns the full 'state' array (all past turns). 
                         If False, returns only the most recent turn in the 'state' array.
                         
    Returns:
        A dictionary with the campaign data, or None if not found.
    """
    col = get_campaigns_col()
    campaign = col.find_one({"campaign_id": campaign_id}, {"_id": 0})
    if not campaign:
        return None
        
    if not include_history and "state" in campaign and campaign["state"]:
        # Only keep the latest state turn
        campaign["state"] = [campaign["state"][-1]]
        
    return campaign

def update_campaign(
    campaign_id: str,
    campaign_name: str = "tomb-of-annihilation",
    summary: Optional[str] = None,
    progress: Optional[float] = None,
    scene: Optional[str] = None,
    description: Optional[str] = None,
    metadata: Optional[dict] = None,
    initiative: Optional[List[str]] = None,
    party: Optional[dict] = None
) -> Dict:
    """Update campaign properties or append a new turn state to the campaign.
    
    Args:
        campaign_id: The ID of the campaign.
        campaign_name: The name of the adventure module.
        summary: Optional high-level summary of the campaign so far.
        progress: Optional completion percentage (0-100).
        scene: Title of the current scene. (Requires description, metadata, initiative, and party to append a turn)
        description: Natural language description of the current situation.
        metadata: e.g. {"chapter": "...", "section": "...", "asset_urls": []}
        initiative: Ordered list of characters in initiative order.
        party: Party state e.g. {"characters": {"Name": {"hp": 10, "max_hp": 10, "conditions": []}}}
        
    Returns:
        The updated campaign document.
    """
    col = get_campaigns_col()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    update_ops = {
        "$set": {
            "updated_at": now
        },
        "$setOnInsert": {
            "campaign_id": campaign_id,
            "campaign_name": campaign_name,
        }
    }
    
    if summary is not None:
        update_ops["$set"]["summary"] = summary
        update_ops["$set"]["summary_updated_at"] = now
        
    if progress is not None:
        update_ops["$set"]["progress"] = progress
        
    has_state_update = all(x is not None for x in [scene, description, metadata, initiative, party])
    if has_state_update:
        new_snapshot = {
            "scene": scene,
            "description": description,
            "metadata": metadata,
            "initiative": initiative,
            "party": party,
            "created_dt": now
        }
        update_ops["$push"] = {"state": new_snapshot}
        
    col.update_one(
        {"campaign_id": campaign_id},
        update_ops,
        upsert=True
    )
    
    return get_campaign(campaign_id, include_history=False)
