#!/usr/bin/env python3
import asyncio
import os
import sys

# Add the agent root directory to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.adk.runners import Runner
from google.adk.sessions.database_session_service import DatabaseSessionService
from google.genai.types import Content, Part
from app.agents.story_agent import story_agent

async def main():
    # Setup runner with the SQLite DatabaseSessionService so it logs to session.db
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", ".adk", "session.db")
    runner = Runner(
        app_name="app",
        agent=story_agent,
        session_service=DatabaseSessionService(db_url=f"sqlite+aiosqlite:///{db_path}")
    )
    
    # Create a fresh session for this test
    session = await runner.session_service.create_session(
        app_name="app",
        user_id="user"
    )
    
    print(f"Created session {session.id}. Running story_agent...\n")
    
    # You can change this query to test specific lore lookups
    query = "Build the first scene for the campaign where the players are teleported to chult."
    print(f"Query: {query}\n")
    
    # Iterate over the stream to execute it and print live output
    async for event in runner.run_async(
        session_id=session.id, 
        user_id="user",
        new_message=Content(role="user", parts=[Part.from_text(text=query)])
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    if part.thought:
                        print(f"\033[90m[THOUGHT]\n{part.text}\033[0m\n")
                    else:
                        print(f"[RESPONSE]\n{part.text}\n")
                        
    print(f"--- Done ---")
    # print(f"Run the following to see the full event stream (including tool calls):")
    # print(f"python scripts/dump_session_trace.py --session {session.id}")

if __name__ == "__main__":
    asyncio.run(main())
