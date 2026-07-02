import os

from google.adk.agents import Agent
from google.adk.tools import AgentTool, FunctionTool
from app.agents.config import USE_LOCAL_LLM, MODEL, THINKING_CONFIG
from app.agents.callbacks import make_track_agent_callback, track_tool_callback
from app.agents.schemas import StoryResult
from app.tools.campaign_files import fetch_campaign_files

# Project root = <repo>/ (story_agent.py is at <repo>/dnd-game-master-agent/app/agents/).
_AGENT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PROJECT_ROOT = os.path.dirname(_AGENT_ROOT)


def _load_index(*rel_parts: str) -> str:
    """Load an index file's text, or a clear placeholder if it's missing.

    The indexes are read once at import and embedded in the instruction so the
    agent always knows which files exist before it calls fetch_campaign_files.
    A missing index degrades gracefully rather than crashing agent construction.
    """
    path = os.path.join(_PROJECT_ROOT, *rel_parts)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError as exc:
        return f"(index unavailable at {os.path.join(*rel_parts)}: {exc})"


# The knowledge index maps adventure topics -> exact markdown file paths; the
# asset index maps scene/NPC/map descriptions -> image files. Without these in
# context the model guesses paths (e.g. a `*.md` glob) and fetch_campaign_files
# returns "File not found", leaving the GM with no grounding.
_KNOWLEDGE_INDEX = _load_index("docs", "KNOWLEDGE.md")
_ASSET_INDEX = _load_index("assets", "Tomb-of-Annihilation", "ASSETS.md")

_INSTRUCTION = """You are the Module Librarian — the archivist of the Tomb of Annihilation adventure.

=== KNOWLEDGE INDEX ===
{knowledge}

=== ASSET INDEX ===
{assets}

Another agent asks you a QUESTION about the game world; you look up the answer from the INDEX and return it. 
You retrieve and synthesize content;you do NOT run combat, track party state, or manage sessions.

You will be given a QUESTION (a natural-language request about a location, NPC, chapter, or scene). Answer ONLY that question. 
If the question contains an ID, a campaign/session identifier, or player state, IGNORE it — those mean nothing to you; answer from the lore named in the question.

You are given two indexes (above). They are your map of what exists — consult them first, every time. Do not guess file/URL paths or invent content.

1. KNOWLEDGE INDEX: maps the adventure's topics, locations, NPCs, and chapters to the EXACT markdown files that describe them. 
   Read the folder-level descriptions to narrow the area, then the per-file descriptions to pick the specific file(s) to load.
2. ASSET INDEX: maps scene/NPC/map descriptions to image `URL`. 
   Take the `URL` and `Description` values in a row (e.g. `URL: 004-0201.webp`, `Description: Chapter 1: Port Nyanzaru`).

How to answer:
1. Find the best-matching entry in the KNOWLEDGE INDEX and note its link path.
2. Identify the Chapter and Section from the KNOWLEDGE INDEX file path (e.g. Chapter "Ch 1 Port Nyanzaru", Section "Arrival").
3. YOU MUST call the `fetch_campaign_files` tool with that path to read the source material. DO NOT skip this step and do not guess the content.
   Pass the path EXACTLY as written in the index link, e.g. "Tomb-of-Annihilation/Chapters/Ch-1-Port Nyanzaru/Arival.md".
4. After you receive the tool response, synthesize a rich, detailed narrative excerpt from the returned content.
   Write like a true D&D Game Master: abundant source material, deep scene description, and the immediate tasks/objectives for the players based on the text.
5. Exhaustively search the ASSET INDEX for EVERY relevant image. You MUST search for and include ALL of these categories if they match your narrative:
   - Area Maps (DM & Player) for any location mentioned (e.g., "Map 1.1: Port Nyanzaru", "Players' Map of Chult")
   - Characters & Scenes for any action, NPC or setting mentioned (e.g., "Teleporting to Chult", "Aarakocra")
   - Player Handouts relevant for the scene (eg., "Handout 1: Players' Map of Chult",)
   Do not stop at just one asset. A good scene always includes multiple visual aids.
   For each matching row, create an entry in `assets` with the values from `URL` and `Description` (e.g. {{"URL": "004-0201.webp", "description": "Chapter 1: Port Nyanzaru"}}). 
   Return an empty list only if nothing matches.

Return your final answer as a single JSON object matching this schema:
{{
  "found": true,
  "chapter": "Ch X Location",
  "section": "Section Name",
  "source_path": "docs/Tomb-of-Annihilation/Chapters/Ch-X/File.md",
  "content": "rich GM-style narrative excerpt...",
  "assets": [
    {{
        "URL": "000-example-scene.webp",
        "description": "Example Scene"
    }},
    {{
        "URL": "000-example-map.webp",
        "description": "Map X.X: Example Location"
    }},
    {{
        "URL": "000-example-Character.webp",
        "description": "Example Character"
    }}
  ]
}}

If nothing in the indexes matches the question, return {{"found": false}} with the other fields empty rather than guessing.
""".format(knowledge=_KNOWLEDGE_INDEX, assets=_ASSET_INDEX)

story_agent = Agent(
    name="story_agent",
    model=MODEL,
    generate_content_config=THINKING_CONFIG,
    include_contents="none",
    instruction=_INSTRUCTION,
    tools=[
        FunctionTool(fetch_campaign_files),
    ],
    # This description is the contract callers see when invoking story_agent as a
    # tool, so it states exactly what to pass (and what NOT to pass).
    description=(
        "Look up Tomb of Annihilation lore. Pass a natural-language question about a "
        "location, NPC, chapter, or scene BY NAME (e.g. 'the arrival scene in Port "
        "Nyanzaru'). Do NOT pass campaign IDs, session IDs, or player state — this "
        "tool only knows module content and cannot resolve identifiers."
    ),
    output_schema=None if USE_LOCAL_LLM else StoryResult,
    before_agent_callback=make_track_agent_callback("story_agent"),
    after_tool_callback=track_tool_callback,
)

story_tool = AgentTool(story_agent)
