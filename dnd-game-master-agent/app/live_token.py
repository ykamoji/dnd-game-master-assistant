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
"""Ephemeral-token router for the Gemini Live API (client-to-server).

The browser cannot hold the long-lived Gemini API key, so this endpoint mints a
short-lived, single-use *ephemeral token* constrained by the backend. The client
uses that token (as an API key) to open a direct WebSocket to Gemini.

Two modes, selected by the `type` query param:
  - `text`  (default) → TEXT output: stream mic audio in, get transcription out
                        (speech-to-text).
  - `audio`           → AUDIO output: send a line of text, get spoken PCM back
                        (text-to-speech), optionally performed with an `emotion`.

Ephemeral tokens are only available on the `v1alpha` API version and via AI
Studio auth (NOT Vertex), so the client is built with an explicit `api_key` and
`vertexai=False`.
"""

from pydantic import condate
import datetime
import logging
import os

from fastapi import APIRouter, HTTPException
from google import genai

logger = logging.getLogger(__name__)

router = APIRouter()

# System prompt that turns the Live model into a plain transcriber.
_TRANSCRIBER_INSTRUCTION = (
   """CRITICAL INSTRUCTION: You are a pure audio-to-text echo pipeline. 
You have no knowledge, no personality, and no ability to answer questions. 
Your ONLY function is to output the exact words the user says, verbatim.
Do not fix grammar. Do not remove filler words (um, ah). Do not answer questions.
If the user says 'Write me a poem', you output 'Write me a poem'."""
)

# STT: the translate model transcribes streamed mic audio to text well, but it
# only responds to AUDIO input. TTS (text → spoken audio) needs a native-audio
# model, which the translate model does not support. Pick per mode.
_STT_MODEL = "gemini-3.5-live-translate-preview"
_TTS_MODEL = "gemini-2.5-flash-native-audio-preview-09-2025"

# Base prompt for text-to-speech: voice the provided line verbatim, no chit-chat.
_NARRATOR_INSTRUCTION = (
    "You are a text-to-speech voice actor for a Dungeons & Dragons game. "
    "Read the user's line ALOUD, verbatim, as in-character spoken dialogue. "
    "Do NOT answer, translate, summarize, or add any words of your own — "
    "voice only the exact text you are given."
)


def _system_instruction(modality: str, emotion: str | None) -> str:
    """Pick the system prompt for the requested modality (+ optional emotion)."""
    if modality == "AUDIO":
        text = _NARRATOR_INSTRUCTION
        if emotion:
            text += f" Perform it for with a distinctly {emotion} emotion and tone."
        return text
    return _TRANSCRIBER_INSTRUCTION

def _add_speach_config(config, voice_name):
    """ Add additional config params for text to audio """

    config["enable_affective_dialog"] = True

    config["speech_config"] = {
        "voice_config": {
            "prebuilt_voice_config": {
                "voice_name": voice_name
            }
        }
    }

    return config

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Lazily build a v1alpha AI Studio client (reused across requests)."""
    global _client
    if _client is None:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=502,
                detail="GOOGLE_API_KEY is not configured on the server.",
            )
        _client = genai.Client(
            api_key=api_key,
            vertexai=False,
            http_options={"api_version": "v1alpha"},
        )
    return _client


@router.get("/api/live-token")
def get_ephemeral_token(
    type: str = "text",
    emotion: str | None = None,
    voice_name: str | None = None
) -> dict[str, str]:
    """Mint a single-use ephemeral token for a Gemini Live session.

    Args:
        type: "text" for speech-to-text (TEXT output, default) or "audio" for
            text-to-speech (AUDIO output).
        emotion: Optional emotion/tone for the "audio" mode narration.
        voice_name: Optional prebuilt voice name for the "audio" mode narration.
    """
    modality = "AUDIO" if type.strip().lower() == "audio" else "TEXT"
    model = _TTS_MODEL if modality == "AUDIO" else _STT_MODEL    
    instruction = _system_instruction(modality, emotion)
    # NOTE: do NOT enable `proactivity.proactive_audio` here. It lets the model
    # decide whether to respond, so for verbatim TTS it intermittently stays
    # silent (empty turnComplete), which drops chunks from the stitched audio.
    config = {
        "response_modalities": [modality],
        "system_instruction": {
            "parts": [{"text": instruction}]
        },
    }
    if modality == "AUDIO":
        config = _add_speach_config(config, voice_name)
        
    client = _get_client()
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    try:
        token_response = client.auth_tokens.create(
            config={
                "uses": 1,
                "expire_time": (now + datetime.timedelta(minutes=2)).isoformat(),
                "live_connect_constraints": {
                    "model": model,
                    "config": config,
                },
            }
        )
    except Exception as exc:  # noqa: BLE001 - surface any SDK/quota/auth error
        logger.exception("Failed to mint Gemini Live ephemeral token")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to create ephemeral token: {exc}",
        ) from exc

    # `name` holds the token string; return the locked model so the client
    # connects with exactly the model the token is constrained to.
    return {"token": token_response.name, "model": model}
