import os
import sys
from typing import Dict, Literal, Optional

# Since app/tools is inside dnd-game-master-agent, we can add the agent root to sys.path
agent_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if agent_root not in sys.path:
    sys.path.insert(0, agent_root)

from data.loader import lookup_by_name

def lookup_character_resource(
    resource_type: Literal["spells", "classes", "armor", "weapons", "magicitems"], name: str
) -> Optional[Dict]:
    """Look up a D&D character resource — a spell, class, armor, weapon, or magic item.

    Use this to fetch the rules data behind a character's loadout and abilities
    (e.g. Fireball's damage, a Wizard's features, Plate armor's AC, a Longsword's
    damage dice, or a Ring of Protection's effect). Backed by the Open5e dataset.

    Args:
        resource_type: The kind of resource to look up. Allowed values: 'spells',
            'classes', 'armor', 'weapons', 'magicitems'.
        name: The name of the resource (e.g., 'Fireball', 'Wizard', 'Plate',
            'Longsword', 'Ring of Protection').
    """
    allowed = ["spells", "classes", "armor", "weapons", "magicitems"]
    if resource_type not in allowed:
        raise ValueError(f"Invalid resource_type. Must be one of: {', '.join(allowed)}.")
    return lookup_by_name(resource_type, name)
