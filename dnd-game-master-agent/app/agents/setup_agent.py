# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""First-turn Setup agent.

Runs ONCE per campaign, before the intent classifier, when no campaign skeleton
exists yet. It parses the opening message into a campaign name and party, derives
each member's starting HP / loadout from their class, and emits a validated
`SetupResult`. The `setup_finalize` graph node then persists the skeleton
deterministically (see app/agent.py).
"""

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
from app.agents.schemas import SetupResult
from app.tools.open5e_lookup import lookup_character_resource

setup_executor = Agent(
    name="setup_executor",
    model=MODEL,
    generate_content_config=THINKING_CONFIG,
    include_contents="none",
    instruction="""You are the Session Zero Coordinator. 
    
    Before the adventure can begin, you set up the campaign and the party from the player's opening message. 
    You do NOT play the game, narrate scenes, or resolve actions — you only prepare the roster.

    Player's message: {last_player_action}
    Existing campaign state (should be empty on a fresh campaign): {campaign_state}
    Previous feedback (if retrying — fix exactly this): {eval_feedback}

    Required to start: a campaign name AND, for EVERY party member, a name, a role
    (e.g. Tank, Healer, Striker, Controller) and a D&D class (e.g. Fighter, Wizard,
    Cleric).

    Procedure:
    1. Read the message and extract the campaign name and each party member's name,
       role, and class.
    2. If the campaign name is missing, OR there are no party members, OR any member
       is missing a name, role, or class: set "ready": false, "party": [], and write
       in "message" exactly what is still needed — e.g. "Before we start the
       adventure I need a campaign name and, for each party member, a name, a role,
       and a class." Do NOT call any tools in this case.
    3. Otherwise, you MUST look up the class data for EVERY party member simultaneously. 
       Issue all necessary tool calls to lookup_character_resource in a single, parallel 
       batch (one tool call per party member). Do not look them up one by one. Once all 
       parallel tool results are returned, use the data to:
         - Set max_hp to the leading whole number of "hp_at_1st_level" (e.g.
           "10 + your Constitution modifier" -> 10), and set hp = max_hp (the party
           starts at full health).
         - Seed "weapons" and "armors" from the class's "prof_weapons" / "prof_armor"
           (a reasonable starting loadout). Only list gear grounded in the tool data —
           never invent specific magic items.
         - Set "conditions": [].
       Then set "ready": true and a short "message" confirming the party is ready.

    MANDATORY TOOL USE: You do NOT know a class's HP or proficiencies until lookup_character_resource ACTUALLY returns them. 
    NEVER simulate, assume, or imagine a tool result. Issue the real tool call and wait for its response before filling hp/max_hp/weapons/armors. 
    If the lookup returns nothing for a class, set "ready": false and say which class could not be found in "message".

    Return a single JSON object matching this schema (no prose outside the JSON):
    {
      "campaign_name": "...",
      "ready": true,
      "message": "...",
      "party": [{"name": "...", "role": "...", "class": "...", "hp": 0, "max_hp": 0, "conditions": [], "armors": ["..."], "spells": [], "weapons": ["..."], "magicitems": []}]
    }

    CRITICAL: ALWAYS return the JSON object and nothing else — no prose before or after it.""",
    tools=[
        FunctionTool(lookup_character_resource),
    ],
    output_schema=None if USE_LOCAL_LLM else SetupResult,
    output_key="setup_draft",
    before_agent_callback=make_track_agent_callback("setup_executor"),
    after_tool_callback=track_tool_callback,
)


class SetupEvaluator(BaseAgent):
    """Evaluator for SetupAgent output."""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        agents = ctx.session.state.get("last_agent", [])
        agents.append(self.name)
        ctx.session.state["last_agent"] = agents

        draft = ctx.session.state.get("setup_draft", "")
        normalized, error = validate_draft(draft, SetupResult)

        if error:
            feedback = "Rejected by setup_checker: " + error
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
            ctx.session.state["setup_result"] = normalized
            ctx.session.state["eval_feedback"] = ""
            yield Event(
                author=self.name,
                content=types.Content(
                    role="model",
                    parts=[types.Part.from_text(text="[Evaluator] Setup validated successfully.")]
                ),
                actions=EventActions(
                    escalate=True,
                    state_delta={
                        "setup_result": normalized,
                        "eval_feedback": "",
                    },
                ),
            )


setup_checker = SetupEvaluator(name="setup_checker")

setup_agent = LoopAgent(
    name="setup_agent",
    sub_agents=[setup_executor, setup_checker],
    max_iterations=3,
    description="One-time campaign/party setup. Validates the opening message and "
                "derives each member's starting HP and loadout from their class.",
)
