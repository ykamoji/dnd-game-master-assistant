import json
import os
import pytest
import time
from unittest.mock import patch, MagicMock

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agents.action_agent import action_agent
from app.agents.npc_dialogue_agent import npc_dialogue_agent
from app.agents.campaign_agent import campaign_agent
from app.agents.supervisor_agent import supervisor
from app.agents.story_agent import story_agent
from app.agents.output_agent import output_agent
from app.agents.schemas import ActionResult, NpcResult, CampaignResult

# Load datasets
DATASETS_DIR = os.path.join(os.path.dirname(__file__), "datasets")

def load_dataset(filename):
    with open(os.path.join(DATASETS_DIR, filename), "r") as f:
        return json.load(f)["tests"]

action_data = load_dataset("action_dataset.json")
npc_data = load_dataset("npc_dataset.json")
campaign_data = load_dataset("campaign_dataset.json")


@pytest.fixture
def session_service():
    return InMemorySessionService()


# Gemini's free tier allows only 15 requests/minute. Each agent test fires a
# burst of model calls (executor reasoning + parallel tool round-trips +
# story_agent), so running them back-to-back blows the quota and raises 429
# RESOURCE_EXHAUSTED. A single test stays under the cap, so we sleep before each
# test (except the first) long enough that the previous test's calls fully age
# out of the rolling 60-second window before the next burst starts.
_RATE_LIMIT_SLEEP_SECONDS = 5
_agent_tests_run = 0


@pytest.fixture(autouse=True)
def rate_limit_delay():
    """Space agent tests apart to respect Gemini free-tier limits (15 RPM)."""
    global _agent_tests_run
    if _agent_tests_run:
        time.sleep(_RATE_LIMIT_SLEEP_SECONDS)
    _agent_tests_run += 1
    yield

# Mock MongoDB tools
@pytest.fixture(autouse=True)
def mock_mongo_tools():
    with patch("app.tools.campaign.get_campaign") as mock_get, \
         patch("app.tools.campaign.update_campaign") as mock_update, \
         patch("app.agents.supervisor_agent.update_campaign", create=True) as mock_update_sup:
        
        # Mock get_campaign to return a valid starting state
        mock_get.return_value = {
            "campaign_id": "test_campaign",
            "campaign_name": "tomb-of-annihilation",
            "state": [{
                "scene": "Jungle Edge",
                "description": "You stand at the edge of the jungle.",
                "party": {"characters": {"Hero": {"hp": 10, "max_hp": 10}}},
                "initiative": ["Hero"]
            }]
        }
        
        # Mock update_campaign to just return the args as the new state
        mock_update.return_value = {"status": "success"}
        mock_update_sup.return_value = {"status": "success"}
        
        yield mock_get, mock_update


@pytest.mark.asyncio
@pytest.mark.parametrize("case", action_data)
async def test_action_agent(case, session_service):
    """Test the ActionAgent individually."""
    session_id = f"test_action_{case['id']}"
    initial_state = {
        "last_player_action": case["input"],
        "campaign_id": session_id,
        "tools_fired": [],
        "last_agent": [],
        "eval_feedback": ""
    }
    await session_service.create_session(app_name="app", user_id="test", session_id=session_id, state=initial_state)
    
    runner = Runner(agent=action_agent, app_name="app", session_service=session_service)
    
    new_message = types.Content(role="user", parts=[types.Part.from_text(text=case["input"])])
    
    response_text = ""
    async for event in runner.run_async(user_id="test", session_id=session_id, new_message=new_message):
        if event.content and event.content.parts and event.author == "action_checker":
            # The checker is the last agent in the loop
            response_text = event.content.parts[0].text
            
    # Verify the loop completed and wrote the result or feedback to state
    session = await session_service.get_session(app_name="app", user_id="test", session_id=session_id)
    if not session.state.get("eval_feedback"):
        assert "action_result" in session.state
        assert session.state["intent"] == "ACTION"
        # The checker stores schema-normalized JSON, so the result must parse
        # back into ActionResult (the contract output_agent now relies on).
        ActionResult.model_validate_json(session.state["action_result"])
    else:
        assert "Rejected" in session.state["eval_feedback"]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", npc_data)
async def test_npc_dialogue_agent(case, session_service):
    """Test the NpcDialogueAgent individually."""
    session_id = f"test_npc_{case['id']}"
    initial_state = {
        "last_player_action": case["input"],
        "campaign_id": session_id,
        "tools_fired": [],
        "last_agent": [],
        "eval_feedback": ""
    }
    await session_service.create_session(app_name="app", user_id="test", session_id=session_id, state=initial_state)
    
    runner = Runner(agent=npc_dialogue_agent, app_name="app", session_service=session_service)
    
    new_message = types.Content(role="user", parts=[types.Part.from_text(text=case["input"])])
    
    async for event in runner.run_async(user_id="test", session_id=session_id, new_message=new_message):
        pass
            
    session = await session_service.get_session(app_name="app", user_id="test", session_id=session_id)
    if not session.state.get("eval_feedback"):
        assert "npc_result" in session.state
        assert session.state["intent"] == "NPC_DIALOGUE"
        NpcResult.model_validate_json(session.state["npc_result"])
    else:
        assert "Rejected" in session.state["eval_feedback"]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", campaign_data)
async def test_campaign_agent(case, session_service):
    """Test the CampaignAgent individually."""
    session_id = f"test_campaign_{case['id']}"
    initial_state = {
        "last_player_action": case["input"],
        "campaign_id": session_id,
        "tools_fired": [],
        "last_agent": [],
        "eval_feedback": ""
    }
    await session_service.create_session(app_name="app", user_id="test", session_id=session_id, state=initial_state)
    
    runner = Runner(agent=campaign_agent, app_name="app", session_service=session_service)
    
    new_message = types.Content(role="user", parts=[types.Part.from_text(text=case["input"])])
    
    async for event in runner.run_async(user_id="test", session_id=session_id, new_message=new_message):
        pass
            
    session = await session_service.get_session(app_name="app", user_id="test", session_id=session_id)
    if not session.state.get("eval_feedback"):
        assert "campaign_result" in session.state
        assert session.state["intent"] == "CAMPAIGN"
        CampaignResult.model_validate_json(session.state["campaign_result"])
    else:
        assert "Rejected" in session.state["eval_feedback"]


def _no_mongo():
    """Patch the campaign collection so tool calls never touch real MongoDB.

    `update_campaign`/`get_campaign` resolve `get_campaigns_col` at call time, so
    patching it here is honored even though the FunctionTool wraps the original
    function. find_one -> None keeps get_campaign returning cleanly.
    """
    mock_col = MagicMock()
    mock_col.find_one.return_value = None
    mock_col.update_one.return_value = None
    return patch("app.tools.campaign.get_campaigns_col", return_value=mock_col)


@pytest.mark.asyncio
async def test_supervisor_routing(session_service):
    """Supervisor classifies an attack as ACTION and delegates to the specialist."""
    session_id = "test_supervisor_routing_1"
    player_action = "I swing my longsword at the goblin"
    # Intentionally do NOT seed last_player_action — init_turn_state must derive
    # it from the user message, otherwise the first delegation KeyErrors.
    await session_service.create_session(
        app_name="app", user_id="test", session_id=session_id,
        state={"campaign_id": session_id},
    )

    runner = Runner(agent=supervisor, app_name="app", session_service=session_service)
    new_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=player_action)],
    )

    with _no_mongo():
        async for event in runner.run_async(
            user_id="test", session_id=session_id, new_message=new_message
        ):
            pass

    session = await session_service.get_session(app_name="app", user_id="test", session_id=session_id)
    # Delegation ran the ACTION specialist, which records the intent on success.
    assert "action_executor" in session.state.get("last_agent", [])
    if not session.state.get("eval_feedback"):
        assert session.state.get("intent") == "ACTION"


@pytest.mark.asyncio
async def test_story_agent(session_service):
    """Story agent retrieves campaign content and returns a grounded response."""
    session_id = "test_story_1"
    await session_service.create_session(
        app_name="app", user_id="test", session_id=session_id,
        state={"campaign_id": session_id, "last_agent": [], "tools_fired": []},
    )

    runner = Runner(agent=story_agent, app_name="app", session_service=session_service)
    new_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text="What can you tell me about Port Nyanzaru from the campaign docs?")],
    )

    response_text = ""
    async for event in runner.run_async(
        user_id="test", session_id=session_id, new_message=new_message
    ):
        if event.author == "story_agent" and event.content and event.content.parts:
            text = event.content.parts[0].text
            if text:
                response_text = text

    session = await session_service.get_session(app_name="app", user_id="test", session_id=session_id)
    assert "story_agent" in session.state.get("last_agent", [])
    assert response_text.strip() != ""


@pytest.mark.asyncio
async def test_output_agent(session_service):
    """Output agent formats a specialist result into the GMResponse schema."""
    session_id = "test_output_1"
    # action_result is now a typed ActionResult JSON string (what the checker
    # stores), matching the contract output_agent consumes.
    action_result = ActionResult(
        narrative=(
            "You strike the goblin with your longsword for 9 slashing damage "
            "(1d8+3), dropping it. The path ahead is now clear."
        ),
        math_breakdown="Attack 1d20+5 = 19 vs AC 15 → hit; damage 1d8+3 = 9",
        requires_roll=False,
        suggested_actions=["Advance down the path", "Search the goblin", "Listen for more enemies"],
    ).model_dump_json()
    initial_state = {
        "campaign_id": session_id,
        "intent": "ACTION",
        "action_result": action_result,
        "npc_result": "",
        "campaign_result": "",
        "last_agent": ["action_executor", "action_checker"],
        "tools_fired": ["get_state"],
    }
    await session_service.create_session(
        app_name="app", user_id="test", session_id=session_id, state=initial_state,
    )

    runner = Runner(agent=output_agent, app_name="app", session_service=session_service)
    new_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text="Format the specialist result for the UI.")],
    )

    with _no_mongo():
        async for event in runner.run_async(
            user_id="test", session_id=session_id, new_message=new_message
        ):
            pass

    session = await session_service.get_session(app_name="app", user_id="test", session_id=session_id)
    gm_response = session.state.get("gm_response", "")
    assert gm_response, "Expected output_agent to write a gm_response"
    assert "ACTION" in str(gm_response)
