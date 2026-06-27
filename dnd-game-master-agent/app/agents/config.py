import os

# Hosted default (unchanged behavior)
_HOSTED_MODEL = "gemma-4-31b-it" # "gemini-3.1-flash-lite" "gemma-4-26b-a4b-it"

# Local dev: route through a local Ollama model to avoid Google API rate limits.
# Enable with USE_LOCAL_LLM=1 (and `ollama run gemma4:e2b-mxfp8` running locally).
USE_LOCAL_LLM = os.getenv("USE_LOCAL_LLM", "").lower() in ("1", "true", "yes")

if USE_LOCAL_LLM:
    from google.adk.models.lite_llm import LiteLlm

    LOCAL_MODEL = os.getenv("LOCAL_LLM_MODEL", "ollama_chat/gemma4:e2b-mxfp8")
    MODEL = LiteLlm(
        model=LOCAL_MODEL,
        api_base=os.getenv("OLLAMA_API_BASE", "http://localhost:11434"),
    )
else:
    MODEL = _HOSTED_MODEL

from google.genai import types

THINKING_CONFIG = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_budget=-1, thinking_level=types.ThinkingLevel.HIGH)
)
