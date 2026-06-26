import os
import sys
from typing import Dict, Literal, Optional

# Since app/tools is inside dnd-game-master-agent, we can add the agent root to sys.path
agent_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if agent_root not in sys.path:
    sys.path.insert(0, agent_root)

from data.loader import lookup_by_name

def lookup_open5e(resource_type: Literal["monsters", "spells", "classes"], name: str) -> Optional[Dict]:
    """Look up D&D data from Open5e API.
    
    Args:
        resource_type: The type of data to look up. Allowed values: 'monsters', 'spells', 'classes'.
        name: The name of the resource (e.g., 'Fireball', 'Goblin', 'Wizard').
    """
    if resource_type not in ["monsters", "spells", "classes"]:
        raise ValueError("Invalid resource_type. Must be 'monsters', 'spells', or 'classes'.")
    return lookup_by_name(resource_type, name)
