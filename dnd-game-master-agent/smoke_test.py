import asyncio
import os

import httpx

from app.db import get_client, close_client, check_health
from app.tools import TOOL_FUNCTIONS

async def run_tests():
    print("=== Phase 1: Direct Function Calls ===")
    
    # 1. DB Health
    print("Testing DB Health...")
    db_ok = False
    try:
        res = check_health()
        print(f"DB Health: {res}")
        if res.get("status") == "ok":
            db_ok = True
    except Exception as e:
        print(f"DB Health error: {e}")
        
    # 2. Lookup Character
    print("\nTesting lookup_character...")
    try:
        char = TOOL_FUNCTIONS["lookup_character"]("Acererak")
        if char:
            print(f"Found {char['Name']}, AC: {char['AC']}, HP: {char['HP']}")
        else:
            print("Acererak not found in Appendix D.")
    except Exception as e:
        print(f"Lookup Character error: {e}")
        
    # 3. Character resource Lookups (Open5e: spells/classes/armor/weapons/magicitems)
    print("\nTesting character resource lookups...")
    try:
        spell = TOOL_FUNCTIONS["lookup_character_resource"]("spells", "Fireball")
        if spell:
            print(f"Found spell: {spell.get('name')}")
        else:
            print("Fireball not found.")

        weapon = TOOL_FUNCTIONS["lookup_character_resource"]("weapons", "Longsword")
        if weapon:
            print(f"Found weapon: {weapon.get('name')}")
    except Exception as e:
        print(f"Character resource lookup error: {e}")
        
    # 4. Asset URL
    print("\nTesting get_asset_url...")
    try:
        asset = TOOL_FUNCTIONS["get_asset_url"]("Port Nyanzaru")
        if "url" in asset:
            print(f"Found asset: {asset['url']}")
        else:
            print("Asset not found.")
    except Exception as e:
        print(f"Asset lookup error: {e}")
        
    # DB dependent tests
    if db_ok:
        print("\nTesting campaign state updates (DB dependent)...")
        try:
            cid = "smoke_test_campaign_002"
            # Update campaign summary and progress
            res = TOOL_FUNCTIONS["update_campaign"](
                campaign_id=cid,
                summary="Smoke test summary 2",
                progress=10.0
            )
            print(f"Update campaign summary: {res.get('summary')}")
            
            # Update state turn
            res = TOOL_FUNCTIONS["update_campaign"](
                campaign_id=cid,
                scene="Smoke Test Scene 2",
                description="Testing the API.",
                metadata={"chapter": "test", "asset_urls": []},
                initiative=["Tester"],
                party={"characters": {"Tester": {"hp": 10, "max_hp": 10, "conditions": []}}},
            )
            print(f"Update campaign state: appended turn")
            
            # Get campaign
            camp = TOOL_FUNCTIONS["get_campaign"](cid)
            print(f"Get campaign (no history): {camp.get('summary')} | {len(camp.get('state', []))} turn")
            
            camp_full = TOOL_FUNCTIONS["get_campaign"](cid, include_history=True)
            print(f"Get campaign (with history): {len(camp_full.get('state', []))} turns")
            
        except Exception as e:
            print(f"State test error: {e}")
    else:
        print("\nSkipping campaign updates because MongoDB is not reachable.")
        
    print("\n=== Phase 2: HTTP Route Calls ===")
    from app.fast_api_app import app
    
    # We use ASGI transport to hit the FastAPI app without running a server
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # DB Health
        res = await client.get("/health/db")
        print(f"GET /health/db: {res.status_code}")
        
        # Lookup Character
        res = await client.get("/tools/lookup_character/Acererak")
        print(f"GET /tools/lookup_character/Acererak: {res.status_code}")
        
        # Lookup character resource (monsters/spells/classes)
        res = await client.get("/tools/lookup_character_resource/spells/Fireball")
        print(f"GET /tools/lookup_character_resource/spells/Fireball: {res.status_code}")
        
    print("\nSmoke tests completed.")
    close_client()

if __name__ == "__main__":
    asyncio.run(run_tests())
