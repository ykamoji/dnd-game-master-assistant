from typing import Literal, AsyncGenerator
from pydantic import BaseModel, Field
from google.adk.agents import Agent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event
from app.agents.config import USE_LOCAL_LLM, MODEL
from google.genai import types
import time

class EvaluationResult(BaseModel):
    grade: Literal["pass", "fail"] = Field(
        description="The evaluation result. Fail if the draft does not properly address the user query or ignores instructions."
    )
    comment: str = Field(
        description="Actionable explanation of why it failed or passed. Keep it brief."
    )

_judge = Agent(
    name="llm_evaluator",
    model=MODEL,
    include_contents="none",
    instruction="""You are a D&D Game Master Quality Assurance Judge.
Your job is to review a drafted response and determine if it is meaningful, logically sound, and directly addresses the game master's or player's query based on the intent.
    
- If the response is good: Grade it as 'pass' and provide a brief sentence on why it works.
- If the response fails (does not address the query, ignores the player, breaks game rules, or contains hallucinated nonsense): Grade it as 'fail' and provide actionable feedback on exactly what the agent should change.
""",
    output_schema=None if USE_LOCAL_LLM else EvaluationResult,
    output_key="evaluation_result",
)

async def evaluate_draft_semantically(
    intent: str, query: str, draft: str, ctx: InvocationContext
) -> AsyncGenerator[Event, None]:
    """Evaluates the draft semantically using an LLM.

    Yields events so they are captured by the parent evaluator and persisted to
    the session database.
    Writes result to ctx.session.state["evaluation_result_outcome"] = (is_valid, feedback)
    """
    prompt = f"Intent: {intent}\nPlayer Query: {query}\nDrafted Response: {draft}"
    
    ctx.session.state["evaluation_result"] = None
    ctx.session.state["evaluation_result_outcome"] = (True, "")
    
    # 1. Yield a user event for the prompt so it shows up in the trace and the model receives it
    prompt_event = Event(
        id=Event.new_id(),
        invocation_id=ctx.invocation_id,
        author="user",
        timestamp=time.time(),
        content=types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)]
        )
    )
    ctx.session.events.append(prompt_event)
    yield prompt_event
    
    try:
        async for event in _judge.run_async(ctx):
            if event.actions and event.actions.state_delta:
                ctx.session.state.update(event.actions.state_delta)
            yield event
    except Exception as e:
        # If the LLM call fails (e.g. rate limit), fail open so we don't block the game
        return
        
    result = ctx.session.state.get("evaluation_result")
    if result:
        if isinstance(result, EvaluationResult):
            if result.grade != "pass":
                ctx.session.state["evaluation_result_outcome"] = (False, result.comment)
        elif isinstance(result, dict):
            grade = result.get("grade", "pass")
            comment = result.get("comment", "")
            if grade != "pass":
                ctx.session.state["evaluation_result_outcome"] = (False, comment)
        elif isinstance(result, str):
            # Parse local LLM raw response if needed (it outputs "fail\n<comment>" or "pass\n<comment>")
            lines = result.strip().split("\n", 1)
            grade = lines[0].strip().lower()
            comment = lines[1].strip() if len(lines) > 1 else ""
            if "fail" in grade:
                ctx.session.state["evaluation_result_outcome"] = (False, comment)
