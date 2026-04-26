"""
Shared LLM client construction for all agents.

Points the OpenAI Agents SDK at Vertex AI's OpenAI-compatible endpoint.
Auth is Application Default Credentials (ADC) — no API key in environment.

Usage:
  - Call configure_default_client() once at app startup (main.py lifespan).
    The token lasts ~1 hour, which is long enough for any single demo session.
    The synchronous credentials.refresh() must run in a synchronous context
    (FastAPI lifespan startup, before yield) to avoid deadlocking inside an
    async event loop.
  - Each agent calls get_chat_model(settings.llm_model) to get a model object
    that bypasses the SDK's prefix router and talks directly to Vertex AI.
"""

from __future__ import annotations

import logging

import google.auth
import google.auth.transport.requests
from agents import OpenAIChatCompletionsModel, set_tracing_disabled
from openai import AsyncOpenAI

from backend.config import get_settings

logger = logging.getLogger(__name__)

# Module-level client cache — built once at startup, reused across agents.
_client: AsyncOpenAI | None = None


def _build_client_sync() -> AsyncOpenAI:
    """Synchronous client construction.

    Calls google.auth.default() and credentials.refresh() — both are blocking
    HTTP/network calls. Must run in a synchronous context (startup) or in a
    thread executor; never directly inside the async event loop, since the
    auth library can deadlock there.
    """
    settings = get_settings()

    credentials, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(google.auth.transport.requests.Request())

    base_url = (
        f"https://{settings.gcp_location}-aiplatform.googleapis.com"
        f"/v1beta1/projects/{settings.gcp_project}"
        f"/locations/{settings.gcp_location}/endpoints/openapi"
    )

    logger.debug("Vertex AI base_url: %s", base_url)
    return AsyncOpenAI(api_key=credentials.token, base_url=base_url)


def configure_default_client() -> None:
    """Build the Vertex AI client and cache it. Call once at startup.

    Safe to call from FastAPI lifespan startup (which runs in a sync context
    before the event loop accepts requests). Also disables SDK tracing —
    the default trace exporter targets OpenAI's platform API, which rejects
    our GCP bearer token.
    """
    global _client
    _client = _build_client_sync()
    set_tracing_disabled(True)

    settings = get_settings()
    logger.info(
        "LLM client configured: Vertex AI / %s / %s",
        settings.gcp_project,
        settings.llm_model,
    )


def get_chat_model(model_name: str) -> OpenAIChatCompletionsModel:
    """Return an SDK model object wired to Vertex AI.

    Uses OpenAIChatCompletionsModel directly so the model name (e.g.
    'google/gemini-2.5-flash') is passed as-is to Vertex without going
    through the SDK's prefix router, which only knows openai/ and anthropic/.

    If the client wasn't initialised at startup (e.g. a one-off CLI smoke
    call), build it eagerly here. This still runs in a sync caller context
    (asyncio.run hasn't been entered yet, or this is being called from
    within the loop's startup phase).
    """
    global _client
    if _client is None:
        _client = _build_client_sync()
        set_tracing_disabled(True)

    return OpenAIChatCompletionsModel(model=model_name, openai_client=_client)
