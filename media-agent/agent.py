import os
import uuid
import logging
from contextlib import asynccontextmanager
from collections import defaultdict

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from strands import Agent, tool
from strands.models.anthropic import AnthropicModel
from langfuse import get_client, propagate_attributes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("media-agent")

# Initialize Langfuse — enables automatic OTEL trace export from Strands
langfuse = get_client()
try:
    if langfuse.auth_check():
        logger.info("Langfuse connected")
    else:
        logger.warning("Langfuse auth failed — tracing disabled (check LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY)")
except Exception:
    logger.warning("Langfuse unreachable — tracing disabled (will work without it)")

# ── Config ────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MOVIE_AGENT_URL = os.environ.get("MOVIE_AGENT_URL", "http://movie-agent:8001")
TV_AGENT_URL = os.environ.get("TV_AGENT_URL", "http://tv-agent:8002")
MODEL_ID = os.environ.get("MODEL_ID", "claude-sonnet-4-20250514")

SYSTEM_PROMPT = """You are a media assistant that orchestrates movie and TV show requests.

You have two tools:
- movie_agent: Use this for anything related to MOVIES — searching, adding to Radarr, checking Plex movie library, movie downloads, etc.
- tv_agent: Use this for anything related to TV SHOWS / SERIES — searching, adding to Sonarr, checking Plex TV library, episode calendars, etc.

Guidelines:
- Analyze the user's request and route it to the correct agent(s).
- If a request involves BOTH movies and TV shows, call both agents.
- If it's ambiguous, ask the user to clarify or check both.
- Pass the user's request naturally — the sub-agents are conversational.
- Combine responses from multiple agents into a single coherent reply.
- Do NOT mention the internal agent routing to the user — just respond naturally.
"""

# ── State ─────────────────────────────────────────────────────

sessions: dict[str, list[dict]] = defaultdict(list)
agent: Agent | None = None


# ── Tools ─────────────────────────────────────────────────────

@tool
def movie_agent(request: str) -> str:
    """Send a request to the Movie Agent for movie-related tasks.
    Use this for: searching movies, adding movies to Radarr, checking Plex movie library,
    movie download queue, browsing movie library, recently added movies.

    Args:
        request: The user's movie-related request in natural language.

    Returns:
        The Movie Agent's response.
    """
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{MOVIE_AGENT_URL}/chat",
                json={"message": request},
            )
            resp.raise_for_status()
            return resp.json().get("response", "No response from Movie Agent.")
    except Exception as e:
        logger.error(f"Movie Agent error: {e}")
        return f"Movie Agent is unavailable: {e}"


@tool
def tv_agent(request: str) -> str:
    """Send a request to the TV Agent for TV show-related tasks.
    Use this for: searching TV series, adding shows to Sonarr, checking Plex TV library,
    episode calendar, TV download queue, browsing TV library, recently added episodes.

    Args:
        request: The user's TV-related request in natural language.

    Returns:
        The TV Agent's response.
    """
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{TV_AGENT_URL}/chat",
                json={"message": request},
            )
            resp.raise_for_status()
            return resp.json().get("response", "No response from TV Agent.")
    except Exception as e:
        logger.error(f"TV Agent error: {e}")
        return f"TV Agent is unavailable: {e}"


# ── App ───────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the orchestrator agent on startup."""
    global agent

    model = AnthropicModel(
        client_args={"api_key": ANTHROPIC_API_KEY},
        model_id=MODEL_ID,
        max_tokens=1024,
    )

    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[movie_agent, tv_agent],
    )

    # Verify sub-agents are reachable
    for name, url in [("Movie", MOVIE_AGENT_URL), ("TV", TV_AGENT_URL)]:
        try:
            with httpx.Client(timeout=5) as client:
                resp = client.get(f"{url}/health")
                resp.raise_for_status()
                logger.info(f"{name} Agent reachable at {url}")
        except Exception:
            logger.warning(f"{name} Agent not reachable at {url} — will retry on first request")

    logger.info("Media Agent ready")
    yield
    logger.info("Media Agent shut down")


app = FastAPI(title="Media Agent", lifespan=lifespan)


# ── Models ────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


# ── Endpoints ─────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Handle a chat message. Routes to Movie/TV sub-agents via the orchestrator."""
    if agent is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Agent not initialized yet."},
        )

    session_id = req.session_id or str(uuid.uuid4())

    sessions[session_id].append({"role": "user", "content": req.message})

    try:
        with langfuse.start_as_current_observation(as_type="span", name="media-agent-chat"):
            with propagate_attributes(session_id=session_id):
                result = agent(req.message)
                response_text = str(result)

        sessions[session_id].append({"role": "assistant", "content": response_text})
        return ChatResponse(response=response_text, session_id=session_id)

    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        error_msg = f"Sorry, I ran into an error: {str(e)}"
        sessions[session_id].append({"role": "assistant", "content": error_msg})
        return ChatResponse(response=error_msg, session_id=session_id)


@app.get("/health")
async def health():
    """Health check — also reports sub-agent reachability."""
    sub_agents = {}
    for name, url in [("movie", MOVIE_AGENT_URL), ("tv", TV_AGENT_URL)]:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{url}/health")
                sub_agents[name] = resp.json()
        except Exception:
            sub_agents[name] = {"status": "unreachable"}

    return {
        "status": "ok",
        "agent_ready": agent is not None,
        "sub_agents": sub_agents,
    }


# ── Run ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
