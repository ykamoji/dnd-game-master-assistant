from typing import AsyncGenerator
from google.adk.agents import Agent, BaseAgent, LoopAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.tools import FunctionTool
from google.genai import types

from app.agents.config import USE_LOCAL_LLM, MODEL, THINKING_CONFIG
from app.agents.callbacks import (
    make_track_agent_callback,
    track_tool_callback,
    validate_draft,
)
from app.agents.schemas import ActionResult
from app.agents.story_agent import story_tool
from app.tools.campaign import get_state
from app.tools.character_lookup import lookup_character
from app.tools.open5e_lookup import lookup_character_resource
from app.agents.evaluator_judge import evaluate_draft_semantically

action_executor = Agent(
    name="action_executor",
    model=MODEL,
    generate_content_config=THINKING_CONFIG,
    include_contents="none",
    instruction="""You are the Combat & Rules Arbiter — a precise, impartial D&D 5e referee. You resolve a player's action by the rules, show the math, and never fudge or invent numbers.

    Latest Campaign State:
    {campaign_state}

    Player's action: {last_player_action}
    Campaign ID: {campaign_id}
    Previous feedback (if retrying — fix exactly this): {eval_feedback}

    Procedure:
    1. Call `get_state` (use the Campaign ID above) to load the CURRENT party HP and conditions, the recent combat_log, and the current scene/chapter/location.
       `get_state` is your authoritative party source — it always returns the latest party even when the most recent scene turn didn't restate it.
    2. Call `lookup_character` for a creature/monster/NPC stat block (attacker or target), and `lookup_character_resource` for a spell, class, armor, weapon, or magic item.
    3. If you need module rules or scene context, call `story_agent` — but ask ONLY about game lore using location / NPC / monster / chapter names. 
       NEVER pass the Campaign ID, session ID, or player HP/state; story_agent only knows Tomb-of-Annihilation content and cannot look anything up by ID.
    4. Call `get_state`, `lookup_character`, `lookup_character_resource`, `story_agent` simultaneously. Issue all neccessary calls in a single, parallel batch. Do not look them up one by one.
       Once all parallel tool results are returned, construct the response from what the tools returned. 
    5. Resolve the action under D&D 5e rules: roll attacks/saves, apply AC, modifiers, damage, and conditions. Show every step of the math.
    6. Report each character's resulting HP/conditions ONLY when you actually know them from a tool — never invent hp or max_hp.
    7. For each character in `party`, also report their `role` (party role, e.g. Tank, Healer, Striker) and `class` (D&D class, e.g. Wizard, Fighter) from the campaign state or a tool — carry these forward unchanged; do not invent them.
    8. Track each character's loadout in `party`: their armors, spells, weapons, and magicitems. Update these when this action changes them (an item is picked up, consumed, equipped, a spell is learned/expended, etc.). 
       Only list items you actually know from a tool or the campaign state — never invent gear.

    MANDATORY TOOL USE: You do NOT know party state, stat blocks, or rules until the tool ACTUALLY returns them. 
    NEVER simulate, assume, pretend, or imagine a tool result — phrases like "(simulated)" or "assuming this returns…" are forbidden.
    Issue the real tool call and wait for its response before resolving anything. If a needed tool returns nothing, say so in `narrative` instead of inventing data.

    Return a single JSON object matching this schema (no prose outside the JSON):
    {
      "narrative": "what happened, vividly described",
      "combat_log": [{"action": "...", "target": "...", "roll": "1d20+5 = 18", "result": "Hit! 8 slashing"}],
      "math_breakdown": "AC 15 vs attack 18 → hit; damage 1d8+3 = 8",
      "party": [{"name": "...", "role": "...", "class": "...", "hp": 0, "max_hp": 0, "conditions": ["..."], "armors": ["..."], "spells": ["..."], "weapons": ["..."], "magicitems": ["..."]}],
      "requires_roll": true,
      "next_scene_suggestions": ["str"],
      "suggested_actions": ["str"],
      "assets": [{{"URL":"str", "description":"str"}}, ...]
    }

    Rules: always show your math; be specific about dice and modifiers; omit a character from `party` entirely rather than guessing their hp.

    CRITICAL: ALWAYS return the JSON object and nothing else — no prose before or after it. 
    If information is missing or you would ask the player a question, put that text in `narrative` and leave the unknown fields at their defaults. 
    Never reply with a plain-text message.""",
    tools=[
        FunctionTool(get_state),
        FunctionTool(lookup_character),
        FunctionTool(lookup_character_resource),
        story_tool,
    ],
    output_schema=None if USE_LOCAL_LLM else ActionResult,
    output_key="action_draft",
    before_agent_callback=make_track_agent_callback("action_executor"),
    after_tool_callback=track_tool_callback,
)


class ActionEvaluator(BaseAgent):
    """Evaluator for ActionAgent output."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        agents = ctx.session.state.get("last_agent", [])
        agents.append(self.name)
        ctx.session.state["last_agent"] = agents

        draft = ctx.session.state.get("action_draft", "")
        normalized, error = validate_draft(draft, ActionResult)

        if error:
            feedback = "Rejected by action_evaluator: " + error
            ctx.session.state["eval_feedback"] = feedback
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text=f"[Evaluator] {feedback}")]
                ),
                actions=EventActions(state_delta={"eval_feedback": feedback}),
            )
        else:
            # Semantic evaluation
            intent = "ACTION"
            query = ctx.session.state.get("last_player_action", "")
            async for ev in evaluate_draft_semantically(intent, query, normalized, ctx):
                yield ev

            is_valid, llm_feedback = ctx.session.state.get("evaluation_result_outcome", (True, ""))

            if not is_valid:
                feedback = "Rejected by action_evaluator: " + llm_feedback
                ctx.session.state["eval_feedback"] = feedback
                yield Event(
                    author=self.name,
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=f"[Evaluator] {feedback}")]
                    ),
                    actions=EventActions(state_delta={"eval_feedback": feedback}),
                )
            else:
                ctx.session.state["action_result"] = normalized
                ctx.session.state["eval_feedback"] = ""
                ctx.session.state["intent"] = intent
                yield Event(
                    author=self.name,
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text="[Evaluator] Action resolved successfully.")]
                    ),
                    actions=EventActions(
                        escalate=True,
                        state_delta={
                            "action_result": normalized,
                            "eval_feedback": "",
                            "intent": intent,
                        },
                    ),
                )


action_evaluator = ActionEvaluator(name="action_evaluator")

action_agent = LoopAgent(
    name="action_agent",
    sub_agents=[action_executor, action_evaluator],
    max_iterations=3,
    description="Combat and rules arbiter. Resolves player actions with D&D rules and mechanics.",
)
