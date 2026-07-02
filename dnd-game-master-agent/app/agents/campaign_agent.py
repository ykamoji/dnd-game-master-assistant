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
from app.agents.schemas import CampaignResult
from app.agents.story_agent import story_tool
from app.tools.campaign import get_state
from app.agents.evaluator_judge import evaluate_draft_semantically

campaign_executor = Agent(
    name="campaign_executor",
    model=MODEL,
    generate_content_config=THINKING_CONFIG,
    include_contents="none",
    instruction="""You are the Lorekeeper & Scene Director — the keeper of the Tomb-of-Annihilation world state who frames each scene for the table and points the players toward what comes next.

    Latest Campaign State:
    {campaign_state}

    Player's action: {last_player_action}
    Campaign ID: {campaign_id}
    Previous feedback (if retrying — fix exactly this): {eval_feedback}

    Procedure:
    1. Call `get_state` (use the Campaign ID above) to load the saved scene, progress, party, and initiative.
    2. Call story_agent to pull the relevant chapter/scene content and its asset URL. Ask ONLY about game lore using location / NPC / chapter / scene NAMES (e.g. "the arrival scene in Port Nyanzaru").
       NEVER pass the Campaign ID, session ID, or player state — story_agent only knows module content and cannot resolve IDs.
    3. Call `get_state` and `story_agent` simultaneously. Issue both tool calls in a single, parallel batch. Do not look them up one by one.
    4. Once all parallel tool results are returned, build the scene framing from what `get_state` and `story_agent` returned. 
       Take chapter, section, and asset URLs from story_agent's result — do not invent them.

    Return a single JSON object matching this schema (no prose outside the JSON):
    {
      "narrative": "player-facing description of the current scene",
      "chapter": "from story_agent",
      "section": "from story_agent",
      "scene_summary": "short evocative title/summary",
      "gm_notes": "key NPCs present, threats, opportunities",
      "next_scene_suggestions": ["str"],
      "assets": [{URL: "from story_agent", description: "from story_agent"}, ...],
      "progress": 0.1,
      "initiative": ["str"],
      "suggested_actions": ["str"]
    }

    Set `progress` value based on the chapter progression and scene within the chapter (total 5 chapters). 
    Set `progress`, `initiative`, and `party` ONLY when this turn actually changed them; otherwise leave them 0, null, and empty, respectively so saved state is preserved.
    Never invent hp/max_hp. Be concise but vivid; include asset URLs when story_agent provides them.

    MANDATORY TOOL USE: You do NOT know the saved state or scene content until the tool ACTUALLY returns it. NEVER simulate, assume, pretend, or imagine a tool result — phrases like "(simulated)" or "assuming this returns…" are forbidden.
    Issue the real `get_state` and `story_agent` calls and wait for their responses before framing the scene. Take chapter/section/asset URLs from story_agent's real output; if it returns nothing, say so in `narrative` instead of inventing lore.

    CRITICAL: ALWAYS return the JSON object and nothing else — no prose before or after it. 
    If campaign state is missing or you would ask the player a question, put that text in `narrative` and leave the unknown fields at their defaults.
    Never reply with a plain-text message.""",
    tools=[
        FunctionTool(get_state),
        story_tool,
    ],
    output_schema=None if USE_LOCAL_LLM else CampaignResult,
    output_key="campaign_draft",
    before_agent_callback=make_track_agent_callback("campaign_executor"),
    after_tool_callback=track_tool_callback,
)


class CampaignEvaluator(BaseAgent):
    """Evaluator for CampaignAgent output."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        agents = ctx.session.state.get("last_agent", [])
        agents.append(self.name)
        ctx.session.state["last_agent"] = agents

        draft = ctx.session.state.get("campaign_draft", "")
        normalized, error = validate_draft(draft, CampaignResult)

        if error:
            feedback = "Rejected by campaign_evaluator: " + error
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
            intent = "CAMPAIGN"
            query = ctx.session.state.get("last_player_action", "")
            async for ev in evaluate_draft_semantically(intent, query, normalized, ctx):
                yield ev

            is_valid, llm_feedback = ctx.session.state.get("evaluation_result_outcome", (True, ""))

            if not is_valid:
                feedback = "Rejected by campaign_evaluator: " + llm_feedback
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
                ctx.session.state["campaign_result"] = normalized
                ctx.session.state["eval_feedback"] = ""
                ctx.session.state["intent"] = intent
                yield Event(
                    author=self.name,
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text="[Evaluator] Campaign summary resolved successfully.")]
                    ),
                    actions=EventActions(
                        escalate=True,
                        state_delta={
                            "campaign_result": normalized,
                            "eval_feedback": "",
                            "intent": intent,
                        },
                    ),
                )


campaign_evaluator = CampaignEvaluator(name="campaign_evaluator")

campaign_agent = LoopAgent(
    name="campaign_agent",
    sub_agents=[campaign_executor, campaign_evaluator],
    max_iterations=3,
    description="Scene summaries, GM notes, next-scene suggestions, and asset URLs.",
)
