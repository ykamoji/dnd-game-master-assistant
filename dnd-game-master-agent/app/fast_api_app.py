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
"""FastAPI Application Server for D&D Game Master Agent.

Exposes the agent's graph workflow via HTTP endpoints for interaction and playground integration.
"""

import logging
import os

from dotenv import load_dotenv

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Load environment variables before importing/initializing the ADK agents.
load_dotenv(os.path.join(AGENT_DIR, ".env"))

from fastapi import FastAPI
from google.adk.cli.fast_api import get_fast_api_app

from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback

# Standard Python logging for console output (ambient event handling, etc.).
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

setup_telemetry()


try:
    import google.auth
    from google.cloud import logging as google_cloud_logging
    _, project_id = google.auth.default()
    logging_client = google_cloud_logging.Client()
    logger = logging_client.logger(__name__)
except Exception as e:
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.warning("GCP authentication failed. Falling back to local logging.")
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

# Artifact bucket for ADK (created by Terraform, passed via env var)
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

# Session storage. Default (None) resolves to per-agent local SQLite at
# app/.adk/session.db locally, which the ambient handler and the built-in /run
# resume endpoint share. On Cloud Run/GKE that falls back to in-memory, so set
# SESSION_SERVICE_URI (e.g. a postgres URI) for durable, resumable sessions.
session_service_uri = os.getenv("SESSION_SERVICE_URI")

artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=False,
)
app.title = "dnd-game-master-agent"
app.description = "API for interacting with the Agent dnd-game-master-agent"

from app.ambient import router as ambient_router
from app.custom import router as custom_router
from app.events import router as events_router
from app.live_token import router as live_token_router
from app.db import close_client

app.include_router(custom_router)
# Ambient entry point: Pub/Sub push events drive the workflow (no chat needed).
app.include_router(ambient_router)
# SSE Streaming endpoint for live UI
app.include_router(events_router)
# Ephemeral-token minting for the browser's direct Gemini Live (STT) connection.
app.include_router(live_token_router)

@app.on_event("shutdown")
def shutdown_event():
    close_client()

@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    logger.log_struct(feedback.model_dump(), severity="INFO")
    return {"status": "success"}


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
