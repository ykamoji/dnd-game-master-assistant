import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.db import get_campaigns_col

class CampaignMetadata(BaseModel):
    """Metadata for the current scene."""
    chapter: Optional[str] = Field(default=None, description="The current chapter of the adventure")
    section: Optional[str] = Field(default=None, description="The current section or location name")
    asset_urls: List[str] = Field(default_factory=list, description="URLs to any visual assets for the scene")
    gm_notes: Optional[str] = Field(default=None, description="Private GM notes for the current scene (key NPCs, threats, opportunities)")
    next_scene_suggestions: List[str] = Field(default_factory=list, description="Suggested next scenes or story directions")
    suggested_actions: List[str] = Field(default_factory=list, description="Suggested next actions offered to the player")
    combat_log: List[Dict] = Field(default_factory=list, description="Combat log entries from this turn ({action, target, roll, result})")
    math_breakdown: Optional[str] = Field(default=None, description="Explicit dice math for this turn's action resolution")
    requires_roll: bool = Field(default=False, description="Whether the next suggested action likely needs a dice roll")

class DialogueLine(BaseModel):
    """A single line of NPC dialogue persisted with the turn snapshot."""
    speaker: str = Field(default="", description="Name of the NPC speaking")
    text: str = Field(default="", description="What the NPC says")
    emotion: str = Field(default="", description="Emotional tone of the line (e.g., 'wary')")

class CharacterState(BaseModel):
    """State of a single character in the party."""
    # `class` is reserved; attribute is `class_`, JSON/Mongo key pinned to "class".
    model_config = ConfigDict(populate_by_name=True)

    role: str = Field(default="", description="The character's party role (e.g., 'Tank', 'Healer', 'Striker', 'Controller')")
    class_: str = Field(default="", alias="class", description="The character's D&D class (e.g., 'Wizard', 'Fighter', 'Cleric')")
    hp: int = Field(description="Current hit points")
    max_hp: int = Field(description="Maximum hit points")
    conditions: List[str] = Field(default_factory=list, description="List of current status conditions")
    armors: List[str] = Field(default_factory=list, description="Armor the character currently has equipped/owned")
    spells: List[str] = Field(default_factory=list, description="Spells the character currently has prepared/known")
    weapons: List[str] = Field(default_factory=list, description="Weapons the character currently carries")
    magicitems: List[str] = Field(default_factory=list, description="Magic items the character currently possesses")

class PartyState(BaseModel):
    """The state of the entire party."""
    characters: Dict[str, CharacterState] = Field(
        description="Dictionary mapping character names to their current state"
    )

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

def get_state(campaign_id: str) -> Optional[Dict]:
    """Fetch the latest turn state for the action agent, with party + combat_log guaranteed.

    Returns the campaign doc trimmed to a SINGLE snapshot: the latest turn (so the
    current chapter, scene, location, and description are preserved). However, the
    latest turn may not restate the party or this-turn combat_log (e.g. it was an
    NPC/CAMPAIGN turn). To make sure the action agent always sees the live combat
    context, this back-fills the most recent non-empty `party` and `metadata.combat_log`
    from earlier snapshots and injects them into the returned snapshot's `metadata`
    (`metadata["party"]`, `metadata["combat_log"]`).

    Args:
        campaign_id: The ID of the campaign.

    Returns:
        The campaign doc with `state` set to one back-filled snapshot, or None if the
        campaign does not exist. If there are no snapshots yet, the doc is returned as-is.
    """
    col = get_campaigns_col()
    campaign = col.find_one({"campaign_id": campaign_id}, {"_id": 0})
    if not campaign:
        return None

    states = campaign.get("state") or []
    if not states:
        return campaign

    # Latest snapshot — keeps current chapter/scene/location/description.
    latest = dict(states[-1])
    metadata = dict(latest.get("metadata") or {})

    # Back-fill party: prefer the latest snapshot's own, else the most recent that has one.
    party = latest.get("party")
    if not party:
        for snap in reversed(states):
            if snap.get("party"):
                party = snap["party"]
                break

    # Back-fill combat_log (lives in metadata): latest's own, else most recent non-empty.
    combat_log = metadata.get("combat_log")
    if not combat_log:
        for snap in reversed(states):
            snap_combat = (snap.get("metadata") or {}).get("combat_log")
            if snap_combat:
                combat_log = snap_combat
                break

    # Inject the recovered live combat context into the returned snapshot's metadata.
    if party:
        metadata["party"] = party
    if combat_log:
        metadata["combat_log"] = combat_log
    latest["metadata"] = metadata

    campaign["state"] = [latest]
    return campaign

def update_campaign(
    campaign_id: str,
    campaign_name: str = "tomb-of-annihilation",
    summary: Optional[str] = None,
    progress: Optional[float] = None,
    scene: Optional[str] = None,
    description: Optional[str] = None,
    metadata: Optional[CampaignMetadata] = None,
    initiative: Optional[List[str]] = None,
    party: Optional[PartyState] = None,
    npc_name: Optional[str] = None,
    narrative: Optional[str] = None,
    dialogue: Optional[List[DialogueLine]] = None,
    intent: Optional[str] = None,
) -> Dict:
    """Update campaign properties or append a new turn state to the campaign.

    Args:
        campaign_id: The ID of the campaign.
        campaign_name: The name of the adventure module.
        summary: Optional high-level summary of the campaign so far.
        progress: Optional completion percentage (0-100).
        scene: Title of the current scene. (Requires description, metadata, initiative, and party to append a turn)
        description: Natural language description of the current situation.
        metadata: CampaignMetadata object containing chapter, section, asset_urls,
                  gm_notes, next_scene_suggestions, and suggested_actions.
        initiative: Ordered list of characters in initiative order.
        party: PartyState object mapping character names to their hp, max_hp, and conditions.
        npc_name: Name of the NPC speaking this turn (for NPC_DIALOGUE turns).
        narrative: The turn's player-facing narrative text.
        dialogue: Ordered NPC dialogue lines (speaker, text, emotion) for this turn.
        intent: The resolved intent for this turn (ACTION | NPC_DIALOGUE | CAMPAIGN).

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
        
    # A turn snapshot is persisted whenever any state field is supplied. Fields
    # not supplied this turn are carried forward from the latest stored snapshot,
    # so a partial update (e.g. only party HP) never blanks out the scene,
    # initiative, or other fields that simply didn't change.
    snapshot_fields = [scene, description, metadata, initiative, party, npc_name, narrative, dialogue, intent]
    if any(x is not None for x in snapshot_fields):
        existing = col.find_one(
            {"campaign_id": campaign_id}, {"_id": 0, "state": {"$slice": -1}}
        )
        prior_state = (existing or {}).get("state") or []
        last = prior_state[-1] if prior_state else {}

        def _dump(value):
            # by_alias keeps reserved-word fields (e.g. CharacterState.class_) stored
            # under their real JSON key ("class"); harmless for models without aliases.
            return value.model_dump(by_alias=True) if hasattr(value, "model_dump") else value

        new_snapshot = {
            "scene": scene if scene is not None else last.get("scene"),
            "description": description if description is not None else last.get("description"),
            "metadata": _dump(metadata) if metadata is not None else last.get("metadata"),
            "initiative": initiative if initiative is not None else last.get("initiative"),
            "party": _dump(party) if party is not None else last.get("party"),
            "npc_name": npc_name if npc_name is not None else last.get("npc_name"),
            "narrative": narrative if narrative is not None else last.get("narrative"),
            "dialogue": [_dump(d) for d in dialogue] if dialogue is not None else last.get("dialogue"),
            "intent": intent if intent is not None else last.get("intent"),
            "created_dt": now
        }
        update_ops["$push"] = {"state": new_snapshot}
        
    col.update_one(
        {"campaign_id": campaign_id},
        update_ops,
        upsert=True
    )
    
    return get_campaign(campaign_id, include_history=False)
