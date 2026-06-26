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

"""D&D Game Master Workflow Agent.

Defines the graph-based workflow layout and state transitions for the D&D session.
"""

import re
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.apps import App, ResumabilityConfig
from google.adk.events.event import Event, EventActions
from google.adk.events.request_input import RequestInput
from google.adk.workflow import START, Edge, Workflow, node
from google.genai import types
from pydantic import BaseModel, Field




class PlayerInput(BaseModel):
    message: str = Field(description="The action, choice, or command from the player.")


class NarratorOutput(BaseModel):
    narrative: str = Field(
        description="The atmospheric narration describing what happens."
    )
    suggested_options: list[str] = Field(
        description="A list of 2-3 logical next choices for the player."
    )
    requires_roll: bool = Field(
        description="Whether the next suggested actions require a dice check (e.g. combat, stealth, lockpicking)."
    )


@node
def orchestrator(ctx: Context, node_input: Any) -> Event:
    # Resolve the player's message text from various possible input types
    if isinstance(node_input, PlayerInput):
        player_msg = node_input.message
    elif isinstance(node_input, str):
        player_msg = node_input
    elif hasattr(node_input, "message"):
        player_msg = node_input.message
    elif hasattr(node_input, "parts") and node_input.parts:
        player_msg = "".join(
            [p.text for p in node_input.parts if hasattr(p, "text") and p.text]
        )
    else:
        player_msg = str(node_input)

    player_msg = player_msg.strip()

    return Event(
        output=player_msg,
        actions=EventActions(
            route="narrate", state_delta={"last_player_action": player_msg}
        ),
    )


@node
def prepare_narrator_input(ctx: Context, node_input: str) -> str:
    # Retrieve the state to prepare the prompt for narrator
    last_action = ctx.state.get("last_player_action", "Start the adventure")

    prompt = f"Player Action: {last_action}\n"
    prompt += "\nNarrate the consequences of this action as the D&D Game Master."
    return prompt


narrator = LlmAgent(
    name="narrator",
    model="gemma-4-31b-it",
    instruction="""You are a D&D 5e Game Master (Narrator).
    Use the provided Player Action and Dice Roll Result to narrate the next segment of the adventure.
    Provide rich, atmospheric narrative. Keep it under 4 sentences.
    Give 2-3 suggested choices/options for what the player can do next.
    Indicate if the next action requires a roll.
    """,
    output_schema=NarratorOutput,
    output_key="narrator_result",
)


@node(rerun_on_resume=False)
async def ask_player(ctx: Context, node_input: NarratorOutput):
    # Format the message containing narrative and options
    narrative_text = node_input.narrative
    options_text = "\n".join([f"- {opt}" for opt in node_input.suggested_options])
    message = f"{narrative_text}\n\n**What do you do next?**\n{options_text}"
    if node_input.requires_roll:
        message += "\n\n*(This action likely requires a roll, e.g., type 'roll d20')*"

    # Emit a content event so it is visible in the chat interface
    yield Event(
        content=types.Content(role="model", parts=[types.Part.from_text(text=message)])
    )

    # Yield a RequestInput to pause the workflow and wait for player action
    yield RequestInput(interrupt_id="player_action", message=message)


root_agent = Workflow(
    name="dnd_game_master",
    input_schema=PlayerInput,
    edges=[
        (START, orchestrator),
        Edge(
            from_node=orchestrator,
            to_node=prepare_narrator_input,
            route="narrate",
        ),
        (prepare_narrator_input, narrator),
        (narrator, ask_player),
        (ask_player, orchestrator),
    ],
    description="An interactive D&D Game Master assistant that guides players through adventures, handles rolls, and asks for actions.",
)


app = App(
    root_agent=root_agent,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True),
)
