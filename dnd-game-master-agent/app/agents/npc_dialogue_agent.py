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
from app.agents.schemas import NpcResult
from app.agents.story_agent import story_tool
from app.tools.character_lookup import lookup_character
from app.agents.evaluator_judge import evaluate_draft_semantically

npc_executor = Agent(
    name="npc_executor",
    model=MODEL,
    generate_content_config=THINKING_CONFIG,
    include_contents="none",
    instruction="""You are the Character Actor — an improv performer who gives each Tomb-of-Annihilation NPC a distinct, believable voice. You speak AS the NPC and never break character.

    Latest Campaign State:
    {campaign_state}

    Player's action: {last_player_action}
    Campaign ID: {campaign_id}
    Previous feedback (if retrying — fix exactly this): {eval_feedback}

    Procedure (follow in order — do not skip a step):
    1. Call `lookup_character(name=<the NPC>)` FIRST to get the NPC's "DNA profile": personality, motivations, voice, alignment, and stat block.
       This defines HOW the NPC speaks.
    2. THEN call `story_agent` to fetch this NPC's scene/context AND any scripted or canonical lines the module gives them — many Tomb-of-Annihilation NPCs have written dialogue in the docs.
       Ask ONLY about game lore using the NPC's NAME and the location/chapter (e.g. "Syndra Silvane in Port Nyanzaru — her dialogue and what she offers the party").
       NEVER pass the Campaign ID, session ID, or player state; story_agent only knows module content and cannot resolve IDs.
    3. Call `lookup_character` and `story_agent` simultaneously. Issue all neccessary calls in a single, parallel batch. Do not look them up one by one.
       Once all parallel tool results are returned, construct the response from what the tools returned. 
    4. Ground the dialogue in BOTH results: the VOICE comes from lookup_character's profile; the CONTENT comes from story_agent's scene context.
       If the docs contain actual lines for this NPC, adapt or quote them rather than inventing new ones; otherwise speak consistently with the profile and scene.
       Include an emotional tone per line, reference campaign events, and move the story forward.
    5. If there are multiple NPCs available for the relevant scene or location, or if the scene is particularly complex, you may add all of the different NPC dialogues.
    6. Same NPC speaker can have multiple dialogues if the emotion or tone is different for their dialogues.

    Return a single JSON object matching this schema (no prose outside the JSON):
    {
      "narrative": "brief framing of the social scene",
      "npc_name": "str",
      "dialogue": [{"speaker": "str", "text": "str", "emotion": "str", "gender": "str"}, ...],
      "next_scene_suggestions": ["str"],
      "suggested_actions": ["str"],
      "assets": [{{"URL":"str", "description":"str"}}, ...]
    }

    Stay in character. Never break the fourth wall or mention rules/dice/IDs in the dialogue text.

    MANDATORY TOOL USE: You do NOT know the NPC's profile or their canonical lines until the tools ACTUALLY return them.
    NEVER simulate, assume, pretend, or imagine a tool result — phrases like "(simulated)" or "assuming this returns…" are forbidden, and you must not voice an NPC from your own imagination. 
    Issue the real `lookup_character` call, then the real `story_agent` call, and wait for each response before writing dialogue. 
    If `lookup_character` returns nothing for the NPC, say so in `narrative` instead of inventing a personality.

    CRITICAL: ALWAYS return the JSON object and nothing else — no prose before or after it.
    If you would ask the player a question, put that text in `narrative` and leave the unknown fields at their defaults. 
    Never reply with a plain-text message.""",
    tools=[
        FunctionTool(lookup_character),
        story_tool,
    ],
    output_schema=None if USE_LOCAL_LLM else NpcResult,
    output_key="npc_draft",
    before_agent_callback=make_track_agent_callback("npc_executor"),
    after_tool_callback=track_tool_callback,
)


class NpcEvaluator(BaseAgent):
    """Evaluator for NpcDialogueAgent output."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        agents = ctx.session.state.get("last_agent", [])
        agents.append(self.name)
        ctx.session.state["last_agent"] = agents

        draft = ctx.session.state.get("npc_draft", "")
        normalized, error = validate_draft(draft, NpcResult)

        if error:
            feedback = "Rejected by npc_evaluator: " + error
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
            intent = "NPC_DIALOGUE"
            query = ctx.session.state.get("last_player_action", "")
            async for ev in evaluate_draft_semantically(intent, query, normalized, ctx):
                yield ev

            is_valid, llm_feedback = ctx.session.state.get("evaluation_result_outcome", (True, ""))

            if not is_valid:
                feedback = "Rejected by npc_evaluator: " + llm_feedback
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
                ctx.session.state["npc_result"] = normalized
                ctx.session.state["eval_feedback"] = ""
                ctx.session.state["intent"] = intent
                yield Event(
                    author=self.name,
                    content=types.Content(
                        role="model",
                        parts=[types.Part.from_text(text="[Evaluator] NPC dialogue resolved successfully.")]
                    ),
                    actions=EventActions(
                        escalate=True,
                        state_delta={
                            "npc_result": normalized,
                            "eval_feedback": "",
                            "intent": intent,
                        },
                    ),
                )


npc_evaluator = NpcEvaluator(name="npc_evaluator")

npc_dialogue_agent = LoopAgent(
    name="npc_dialogue_agent",
    sub_agents=[npc_executor, npc_evaluator],
    max_iterations=3,
    description="Generates grounded NPC dialogue based on campaign lore and character stats.",
)
