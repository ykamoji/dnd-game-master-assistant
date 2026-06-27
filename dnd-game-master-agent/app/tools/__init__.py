from google.adk.tools import FunctionTool

from .assets import get_asset_url
from .campaign_files import fetch_campaign_files
from .campaign import get_campaign, get_state, update_campaign
from .character_lookup import lookup_character
from .open5e_lookup import lookup_character_resource

TOOL_FUNCTIONS = {
    "get_campaign": get_campaign,
    "get_state": get_state,
    "update_campaign": update_campaign,
    "fetch_campaign_files": fetch_campaign_files,
    "lookup_character": lookup_character,
    "lookup_character_resource": lookup_character_resource,
    "get_asset_url": get_asset_url,
}

# Wrap all functions as ADK FunctionTools for use in the agent graph
ADK_TOOLS = [FunctionTool(func) for func in TOOL_FUNCTIONS.values()]
