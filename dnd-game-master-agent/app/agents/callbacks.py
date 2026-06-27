import json
import logging
import re
from typing import Optional
from google.adk.agents.callback_context import CallbackContext
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import BaseTool, ToolContext
from google.genai import types
from pydantic import ValidationError

logger = logging.getLogger(__name__)

_INJECTION_PATTERNS = [
    r"ignore\s+(your|previous|all)\s+(instructions|rules|prompts)",
    r"you\s+are\s+now\s+a",
    r"pretend\s+to\s+be",
    r"act\s+as\s+(if\s+you\s+are\s+)?a",
    r"forget\s+(everything|your\s+instructions)",
    r"system\s*prompt",
    r"jailbreak",
]

_OUT_OF_SCOPE_PATTERNS = [
    r"write\s+(me\s+)?(a\s+)?(python|javascript|code|script|program)",
    r"what('s|\s+is)\s+the\s+weather",
    r"(stock|crypto)\s+price",
    r"(translate|summarize)\s+this\s+(article|document|text)",
    r"help\s+me\s+with\s+my\s+(homework|essay|resume)",
]

_INJECTION_REFUSAL = (
    "⚔️ I'm your D&D Game Master — I can only help with in-game actions, "
    "NPC dialogue, and campaign management. Let's get back to the adventure!"
)
_OUT_OF_SCOPE_REFUSAL = (
    "🎲 That's outside the realm of this adventure! I can help you with combat, "
    "NPC conversations, or campaign management. What would you like to do?"
)


def evaluate_input_safety(text: str) -> tuple[bool, str, str]:
    """Pure guardrail check used by both the callback and the workflow node.

    Returns (is_safe, rejection_reason, refusal_message). For safe input the
    reason and message are empty strings.
    """
    user_lower = (text or "").lower()

    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, user_lower):
            return False, "Prompt injection detected", _INJECTION_REFUSAL

    for pattern in _OUT_OF_SCOPE_PATTERNS:
        if re.search(pattern, user_lower):
            return False, "Out-of-scope request", _OUT_OF_SCOPE_REFUSAL

    return True, "", ""


async def guardrail_callback(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    """Before-model callback: short-circuits with a safe refusal if input is unsafe."""
    user_text = ""
    if llm_request.contents:
        for content in reversed(llm_request.contents):
            if content.role == "user" and content.parts:
                user_text = " ".join(
                    p.text for p in content.parts if hasattr(p, "text") and p.text
                )
                break

    is_safe, reason, refusal = evaluate_input_safety(user_text)
    callback_context.state["is_safe"] = is_safe
    callback_context.state["rejection_reason"] = reason
    if not is_safe:
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part.from_text(text=refusal)],
            )
        )
    return None

async def init_turn_state(callback_context: CallbackContext) -> None:
    """Initialize clean state at the start of every supervisor invocation."""
    callback_context.state["last_agent"] = []
    callback_context.state["tools_fired"] = []
    callback_context.state["intent"] = ""
    callback_context.state["eval_feedback"] = ""
    callback_context.state["player_rejected"] = False
    if "campaign_id" not in callback_context.state:
        callback_context.state["campaign_id"] = "default-campaign"

    # Capture the player's message so the specialist instruction templates can
    # resolve {last_player_action}. Without this the very first delegation fails
    # with `KeyError: Context variable not found: last_player_action`.
    player_text = ""
    user_content = callback_context.user_content
    if user_content and user_content.parts:
        player_text = " ".join(
            p.text for p in user_content.parts if getattr(p, "text", None)
        ).strip()
    callback_context.state["last_player_action"] = player_text

def make_track_agent_callback(agent_name: str):
    """Factory: creates a before_agent_callback that tracks agent name and resets tools."""
    async def _track(callback_context: CallbackContext) -> None:
        agents = callback_context.state.get("last_agent", [])
        agents.append(agent_name)
        callback_context.state["last_agent"] = agents
        callback_context.state["tools_fired"] = []
    return _track

async def track_tool_callback(
    tool: BaseTool, args: dict, tool_context: ToolContext, tool_response: dict
) -> Optional[dict]:
    """After-tool callback: appends the tool name to state.tools_fired."""
    fired = tool_context.state.get("tools_fired", [])
    fired.append(tool.name)
    tool_context.state["tools_fired"] = fired
    return None


# Matches a leading ```json / ``` fence and a trailing ``` fence, which weaker
# models (e.g. Gemma) emit despite being told to return raw JSON.
_JSON_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _parse_json(raw: object) -> dict:
    """Best-effort parse of a model's text output into a dict.

    Tolerates markdown code fences and leading/trailing prose by stripping the
    fence and, as a last resort, slicing from the first '{' to the last '}'.
    Returns {} if nothing parseable is found.
    """
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}

    text = _JSON_FENCE_RE.sub("", raw).strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Last resort: grab the outermost {...} block.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except (json.JSONDecodeError, ValueError):
            pass
    return {}


# Backwards-compatible alias: the output_agent persistence path parses gm_response.
def _parse_gm_response(raw: object) -> dict:
    """Tolerant parse of the output_agent's gm_response (see _parse_json)."""
    return _parse_json(raw)


def validate_draft(raw: object, schema) -> tuple[Optional[str], str]:
    """Validate a specialist draft against its Pydantic schema.

    Tolerantly parses `raw` (model text, possibly fenced) and validates it
    against `schema`. On success returns (normalized_json_str, ""); on failure
    returns (None, error_message). The normalized JSON string is what the
    checker stores into state so the output_agent always receives clean,
    schema-conformant JSON regardless of how the model fenced its reply.
    """
    if not raw or not str(raw).strip():
        return None, "Response is empty — the request was not resolved."

    parsed = _parse_json(raw)
    if not parsed:
        return None, "Output was not valid JSON matching the required schema."

    try:
        model = schema.model_validate(parsed)
    except ValidationError as exc:
        # Compact the pydantic errors into a single actionable line for the LLM.
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or '(root)'}: {e['msg']}"
            for e in exc.errors()
        )
        return None, f"Output did not match the {schema.__name__} schema: {problems}"

    # by_alias keeps reserved-word fields (e.g. CharacterUpdate.class_) serialized
    # under their real JSON key ("class") for the downstream output_agent.
    return model.model_dump_json(by_alias=True), ""


def _build_party_state(party_list: list, PartyState, CharacterState):
    """Convert GMResponse.party (list of {name, hp, max_hp, conditions}) into a
    PartyState, or None if absent/malformed.

    Returning None (rather than an empty PartyState) lets the persistence layer
    carry the previous party forward, so a turn that doesn't restate the party
    never wipes existing HP/conditions.
    """
    if not party_list:
        return None
    characters = {}
    for entry in party_list:
        try:
            characters[entry["name"]] = CharacterState(
                role=entry.get("role", ""),
                class_=entry.get("class", ""),
                hp=entry["hp"],
                max_hp=entry["max_hp"],
                conditions=entry.get("conditions", []),
                armors=entry.get("armors", []),
                spells=entry.get("spells", []),
                weapons=entry.get("weapons", []),
                magicitems=entry.get("magicitems", []),
            )
        except (KeyError, TypeError, ValueError):
            logger.warning(
                "persist_campaign_callback: skipping malformed party entry: %r", entry
            )
    return PartyState(characters=characters) if characters else None


def _build_dialogue(dialogue_list: list, DialogueLine):
    """Convert GMResponse.dialogue (list of {speaker, text, emotion}) into a list of
    DialogueLine, or None if absent/malformed.

    Returning None (rather than an empty list) lets the persistence layer carry the
    previous turn's dialogue forward, so a turn that has no dialogue never wipes it.
    """
    if not dialogue_list:
        return None
    lines = []
    for entry in dialogue_list:
        if not isinstance(entry, dict):
            logger.warning(
                "persist_campaign_callback: skipping malformed dialogue line: %r", entry
            )
            continue
        lines.append(
            DialogueLine(
                speaker=entry.get("speaker", ""),
                text=entry.get("text", ""),
                emotion=entry.get("emotion", ""),
            )
        )
    return lines or None


async def persist_campaign_callback(callback_context: CallbackContext) -> None:
    """After-agent callback for output_agent: deterministically persist state.

    Persistence must not depend on a weak model choosing to call a tool. The
    output_agent's only job is to format `gm_response`; this callback parses
    that result and writes the latest campaign state itself, so an update is
    guaranteed every turn (and shows up in state.tools_fired for observability).
    """
    # Imported lazily to avoid a heavy import (pymongo) at module load and any
    # import-order coupling between the agents and tools packages.
    from app.tools.campaign import (
        update_campaign,
        CampaignMetadata,
        PartyState,
        CharacterState,
        DialogueLine,
    )

    if callback_context.state.get("player_rejected"):
        return

    raw = callback_context.state.get("gm_response", "")
    resp = _parse_gm_response(raw)
    if not resp and raw:
        logger.warning(
            "persist_campaign_callback: could not parse gm_response as JSON; "
            "persisting timestamp only. head=%r",
            str(raw)[:80],
        )

    campaign_id = callback_context.state.get("campaign_id") or "default-campaign"
    summary = resp.get("scene_summary") or None
    description = resp.get("narrative") or None
    progress = resp.get("progress")  # may be None == "unchanged"

    # chapter/section/asset_urls + the GM-facing extras all live in scene metadata.
    chapter = resp.get("chapter") or None
    section = resp.get("section") or None
    asset_urls = resp.get("asset_urls") or []
    gm_notes = resp.get("gm_notes") or None
    next_scene_suggestions = resp.get("next_scene_suggestions") or []
    suggested_actions = resp.get("suggested_actions") or []
    # ACTION combat detail also persists into scene metadata for a durable history.
    combat_log = resp.get("combat_log") or []
    math_breakdown = resp.get("math_breakdown") or None
    requires_roll = bool(resp.get("requires_roll"))
    metadata = CampaignMetadata(
        chapter=chapter,
        section=section,
        asset_urls=asset_urls,
        gm_notes=gm_notes,
        next_scene_suggestions=next_scene_suggestions,
        suggested_actions=suggested_actions,
        combat_log=combat_log,
        math_breakdown=math_breakdown,
        requires_roll=requires_roll,
    ) if (chapter or section or asset_urls or gm_notes or next_scene_suggestions
          or suggested_actions or combat_log or math_breakdown or requires_roll) else None

    # initiative: empty list means "unchanged" -> pass None so the tool carries
    # the previous order forward instead of clobbering it.
    initiative = resp.get("initiative") or None

    # party: list[{name, hp, max_hp, conditions}] -> PartyState keyed by name.
    party = _build_party_state(resp.get("party") or [], PartyState, CharacterState)

    # NPC_DIALOGUE fields: persist the speaker, the turn narrative, and the lines.
    npc_name = resp.get("npc_name") or None
    narrative = resp.get("narrative") or None
    dialogue = _build_dialogue(resp.get("dialogue") or [], DialogueLine)

    # intent: prefer the workflow's resolved state value, fall back to the response.
    intent = callback_context.state.get("intent") or resp.get("intent") or None

    try:
        update_campaign(
            campaign_id=campaign_id,
            summary=summary,
            scene=summary,
            description=description,
            progress=progress,
            metadata=metadata,
            initiative=initiative,
            party=party,
            npc_name=npc_name,
            narrative=narrative,
            dialogue=dialogue,
            intent=intent,
        )
    except Exception:  # pragma: no cover - persistence must never break the turn
        logger.exception("persist_campaign_callback: update_campaign failed")
        return

    fired = callback_context.state.get("tools_fired", [])
    fired.append("update_campaign")
    callback_context.state["tools_fired"] = fired
