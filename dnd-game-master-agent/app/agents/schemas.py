from pydantic import BaseModel, ConfigDict, Field

class CombatEntry(BaseModel):
    """A single line in a combat log (one attack, one spell, etc.)."""
    action: str = Field(description="The action taken (e.g., 'Longsword Attack')")
    target: str = Field(default="", description="Who/what was targeted")
    roll: str = Field(default="", description="Dice notation and result (e.g., '1d20+5 = 18')")
    result: str = Field(default="", description="Outcome (e.g., 'Hit! 8 slashing damage')")

class DialogueLine(BaseModel):
    """A single line of NPC dialogue."""
    speaker: str = Field(description="Name of the NPC speaking")
    text: str = Field(description="What the NPC says")
    emotion: str = Field(default="neutral", description="Emotional tone (e.g., 'angry', 'fearful')")
    gender: str = Field(default="", description="Gender of the NPC speaking")

class CharacterUpdate(BaseModel):
    """One character's mechanical state, for persistence to campaign state.

    Modeled as a flat list entry (with `name`) rather than a map so it round-trips
    cleanly through model structured-output, which handles lists of objects more
    reliably than open-ended dictionaries.
    """
    # `class` is a Python keyword, so the attribute is `class_` with the JSON key
    # pinned to "class" via alias; populate_by_name lets us also build it as class_=.
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="Character name")
    role: str = Field(default="", description="The character's party role (e.g., 'Tank', 'Healer', 'Striker', 'Controller')")
    class_: str = Field(default="", alias="class", description="The character's D&D class (e.g., 'Wizard', 'Fighter', 'Cleric')")
    hp: int = Field(description="Current hit points")
    max_hp: int = Field(description="Maximum hit points")
    conditions: list[str] = Field(default_factory=list, description="Active status conditions")
    armors: list[str] = Field(default_factory=list, description="Armor equipped/owned AFTER this turn; include only when known/changed, never invent")
    spells: list[str] = Field(default_factory=list, description="Spells prepared/known AFTER this turn; include only when known/changed, never invent")
    weapons: list[str] = Field(default_factory=list, description="Weapons carried AFTER this turn; include only when known/changed, never invent")
    magicitems: list[str] = Field(default_factory=list, description="Magic items possessed AFTER this turn; include only when known/changed, never invent")

class Assets(BaseModel):
    """
    Image assets that match the current scene.
    """
    URL: str = Field(description="URL of the asset (e.g., '004-0201.webp')")
    description: str = Field(description="Description of the asset (e.g., 'Chapter 1: Port Nyanzaru')")
    

class StoryResult(BaseModel):
    """Structured lookup result returned by story_agent to the calling agents.

    story_agent answers a lore question about the Tomb of Annihilation module.
    `content` is the rich GM-style excerpt; the other fields make the provenance
    and art machine-readable for the caller.
    """
    found: bool = Field(default=False, description="True if a matching module entry was located; False if nothing in the indexes matched the question")
    chapter: str = Field(default="", description="Chapter this content belongs to (e.g., 'Ch 1 Port Nyanzaru')")
    section: str = Field(default="", description="Section/location/scene name within the chapter (e.g., 'Arrival')")
    source_path: str = Field(default="", description="Repo path of the markdown file the content was drawn from, for citation")
    content: str = Field(default="", description="Rich, detailed narrative excerpt synthesized from the module, written like a true D&D Game Master")
    assets: list[Assets] = Field(default_factory=list, description="List of asset file and description for every matching chapter, map, scene, NPC")


class SetupResult(BaseModel):
    """Structured output of the setup_executor (first-turn campaign/party init).

    Produced once, before the game loop starts. The setup_executor parses the
    campaign name and party from the player's opening message and derives each
    member's starting HP / loadout from their class. `ready` gates persistence:
    when False the turn is rejected and the player is told what's missing.
    """
    campaign_name: str = Field(default="", description="Campaign/adventure name from the player's message")
    ready: bool = Field(default=False, description="True ONLY when a campaign name AND every party member's name, role, and class are present")
    message: str = Field(default="", description="If not ready: exactly what the player must still provide. If ready: a short confirmation that the adventure can begin")
    party: list[CharacterUpdate] = Field(default_factory=list, description="One entry per party member with class-derived hp = max_hp, weapons, and armors; empty when not ready")
    narrative: str = Field(description="Player-facing description of the current scene and situation")
    chapter: str = Field(default="", description="Current chapter name, taken from story_agent")
    section: str = Field(default="", description="Current section/location name, taken from story_agent")
    scene_summary: str = Field(default="", description="Short, evocative summary/title of the current location and situation")
    gm_notes: str = Field(default="", description="Private GM notes: key NPCs present, threats, opportunities")
    next_scene_suggestions: list[str] = Field(default_factory=list, description="2-3 suggested next scenes or story directions")
    assets: list[Assets] = Field(default_factory=list, description="List of asset file and description for every matching chapter, map, scene, NPC")
    progress: float | None = Field(default=None, description="Campaign completion percent (0-100); set ONLY if the campaign measurably advanced this turn, else null")
    initiative: list[str] = Field(default_factory=list, description="Combat turn order, only when in or entering combat; else empty")
    suggested_actions: list[str] = Field(default_factory=list, description="2-3 concrete next moves for the player")



class ActionResult(BaseModel):
    """Structured output of the action_executor (combat & rules resolution)."""
    narrative: str = Field(description="Vivid description of what happened when the action resolved")
    combat_log: list[CombatEntry] = Field(default_factory=list, description="One entry per attack/spell/check resolved this turn")
    math_breakdown: str = Field(default="", description="Explicit dice math: AC, attack rolls, modifiers, damage, saving throws")
    party: list[CharacterUpdate] = Field(default_factory=list, description="Per-character HP/conditions AFTER this action; include only characters whose state is known. NEVER invent hp/max_hp")
    requires_roll: bool = Field(default=False, description="True if the next suggested action likely needs a dice roll")
    suggested_actions: list[str] = Field(default_factory=list, description="2-3 concrete next moves the player can choose from")
    assets: list[Assets] = Field(default_factory=list, description="List of asset file and description for every matching chapter, map, scene, NPC")


class NpcResult(BaseModel):
    """Structured output of the npc_executor (in-character NPC dialogue)."""
    narrative: str = Field(description="Brief framing of the social scene around the dialogue")
    npc_name: str = Field(default="", description="Name of the NPC speaking")
    dialogue: list[DialogueLine] = Field(default_factory=list, description="Ordered in-character lines, each with speaker, text, and emotion")
    suggested_actions: list[str] = Field(default_factory=list, description="2-3 follow-up actions the player can take")
    assets: list[Assets] = Field(default_factory=list, description="List of asset file and description for every matching chapter, map, scene, NPC")


class CampaignResult(BaseModel):
    """Structured output of the campaign_executor (scene/state management)."""
    narrative: str = Field(description="Player-facing description of the current scene and situation")
    chapter: str = Field(default="", description="Current chapter name, taken from story_agent")
    section: str = Field(default="", description="Current section/location name, taken from story_agent")
    scene_summary: str = Field(default="", description="Short, evocative summary/title of the current location and situation")
    gm_notes: str = Field(default="", description="Private GM notes: key NPCs present, threats, opportunities")
    next_scene_suggestions: list[str] = Field(default_factory=list, description="2-3 suggested next scenes or story directions")
    assets: list[Assets] = Field(default_factory=list, description="List of asset file and description for every matching chapter, map, scene, NPC")
    progress: float | None = Field(default=None, description="Campaign completion percent (0-100); set ONLY if the campaign measurably advanced this turn, else null")
    initiative: list[str] = Field(default_factory=list, description="Combat turn order, only when in or entering combat; else empty")
    suggested_actions: list[str] = Field(default_factory=list, description="2-3 concrete next moves for the player")


class GMResponse(BaseModel):
    """Unified output schema for the UI renderer.

    The UI reads `intent` to decide which fields to render.
    All fields have defaults so only the relevant ones need to be populated.
    """
    intent: str = Field(description="ACTION | NPC_DIALOGUE | CAMPAIGN")
    narrative: str = Field(description="Main narrative text for the player")
    # ACTION fields
    combat_log: list[CombatEntry] = Field(default_factory=list, description="Combat log entries")
    math_breakdown: str = Field(default="", description="Detailed math for rolls/checks")
    # NPC_DIALOGUE fields
    npc_name: str = Field(default="", description="Name of the NPC in dialogue")
    dialogue: list[DialogueLine] = Field(default_factory=list, description="Dialogue lines")
    # CAMPAIGN fields
    chapter: str = Field(default="", description="The current chapter of the adventure")
    section: str = Field(default="", description="The current section or location name")
    scene_summary: str = Field(default="", description="Summary of the current scene")
    gm_notes: str = Field(default="", description="Private GM notes")
    next_scene_suggestions: list[str] = Field(default_factory=list, description="Suggested next scenes")
    assets: list[Assets] = Field(default_factory=list, description="Asset file and description for every matching chapter, map, scene, NPC")
    # Persistable campaign state — fill ONLY when known. An empty list / null
    # means "unchanged this turn"; the persistence layer carries the previous
    # value forward rather than blanking it. Do not invent values you don't have.
    progress: float | None = Field(default=None, description="Campaign completion percent (0-100), only if it advanced")
    initiative: list[str] = Field(default_factory=list, description="Turn order of combatants, if in/entering combat")
    party: list[CharacterUpdate] = Field(default_factory=list, description="Per-character mechanical state after this turn")
    # Common
    suggested_actions: list[str] = Field(default_factory=list, description="2-3 choices for the player")
    requires_roll: bool = Field(default=False, description="Whether the next action needs a dice roll")
    last_agent: list[str] = Field(default_factory=list, description="Observability: agents that ran")
    tools_fired: list[str] = Field(default_factory=list, description="Observability: tools that fired")
