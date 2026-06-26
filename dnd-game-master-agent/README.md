# D&D Game Master Agent

An interactive D&D Game Master assistant built with ADK 2.0 graph workflows. It handles campaigns, narrative generation, and dynamically queries Open5e data and local D&D adventure assets (e.g. Tomb of Annihilation).

## Project Structure

```
dnd-game-master-agent/
├── app/                       # Core application code
│   ├── agent.py               # Main graph workflow logic
│   ├── custom.py              # Custom FastAPI UI routes
│   ├── db.py                  # MongoDB client connection
│   ├── fast_api_app.py        # FastAPI root server
│   ├── tools/                 # Backend tools (used by agent and UI)
│   └── app_utils/             # App utilities and helpers
├── data/                      # Open5e data fetch scripts
├── smoke_test.py              # E2E Smoke test suite
├── tests/                     # Unit, integration, and load tests
└── pyproject.toml             # Project dependencies
```

> 💡 **Tip:** Use [Gemini CLI](https://github.com/google-gemini/gemini-cli) for AI-assisted development - project context is pre-configured in `GEMINI.md`.

## Backend APIs & Tools

The agent includes a set of custom backend tools that are exposed both as ADK `FunctionTool`s for the LLM graph and directly as HTTP routes for the React frontend UI.

### State & Campaign Management (MongoDB)
- **`update_campaign`** (POST `/campaign/{campaign_id}/update`): Updates the campaign summary, progress, or appends a new state turn. 
- **`get_campaign`** (GET `/campaign/{campaign_id}?include_history=False`): Fetches the campaign summary, progress, and current state turn.

### Adventure Files & Assets
- **`fetch_campaign_files`** (POST `/tools/fetch_campaign_files`): Securely reads raw `.md` files from the local `docs/` directory.
- **`get_asset_url`** (POST `/tools/get_asset_url`): Fuzzy-matches and resolves image URLs from `ASSETS.md`.

### D&D Rules & Stats Lookups
- **`lookup_character`** (GET `/tools/lookup_character/{name}`): Pulls full stat blocks for specific campaign NPCs and monsters from `Appendix D.csv`.
- **`lookup_open5e`** (GET `/tools/lookup_open5e/{resource_type}/{name}`): Fallback query for standard Open5e `monsters`, `spells`, or `classes`.

### System Health
- **`health_db`** (GET `/health/db`): Pings MongoDB to verify connection status.

*(Note: Dice rolling is handled entirely client-side, so no server-side dice API is provided.)*

## Requirements

Before you begin, ensure you have:
- **uv**: Python package manager (used for all dependency management in this project) - [Install](https://docs.astral.sh/uv/getting-started/installation/)
- **agents-cli**: Agents CLI - Install with `uv tool install google-agents-cli`
- **MongoDB**: Provide `MONGO_URI` via `.env` file for campaign state persistence.

## Quick Start

Install required packages:
```bash
make install
```

Test the tools and routes without the agent:
```bash
make smoke-test
```

Run the local playground:
```bash
make playground
```

## Commands

| Command              | Description                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------------- |
| `make install`       | Install dependencies using uv                                                               |
| `make playground`    | Launch local development environment (agent + API)                                          |
| `make smoke-test`    | Run smoke tests for tools and custom routes                                                 |
| `make test`          | Run unit and integration tests                                                              |
| `agents-cli lint`    | Run code quality checks                                                                     |
| `agents-cli eval`    | Evaluate agent behavior (generate, grade, analyze, and more)                                |

---

## Development

Edit your agent logic in `app/agent.py` and tools in `app/tools/`. Test with `make playground` - it auto-reloads on save.

## Observability

GCP telemetry is disabled by default for local development to avoid missing credentials errors. Built-in telemetry exports to Cloud Trace, BigQuery, and Cloud Logging when deployed.
