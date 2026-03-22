import os
import time
import uuid
import logging
from contextlib import asynccontextmanager
from collections import defaultdict

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from strands import Agent
from strands.models.anthropic import AnthropicModel
from strands.tools.mcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from langfuse import get_client, propagate_attributes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("movie-agent")

# Initialize Langfuse — enables automatic OTEL trace export from Strands
langfuse = get_client()
if langfuse.auth_check():
    logger.info("Langfuse connected")
else:
    logger.warning("Langfuse auth failed — tracing disabled (check LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY)")

# ── Config ────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MOVIE_MCP_URL = os.environ.get("MOVIE_MCP_URL", "http://movie-mcp-server:8101")
MODEL_ID = os.environ.get("MODEL_ID", "claude-haiku-4-5-20251001")

SYSTEM_PROMPT = """You are a helpful movie assistant connected to a home media server.

You can:
- Search for movies by title, genre, mood, or description
- Check if a movie is already available in the Plex library
- Add movies to Radarr for automatic download
- Check download queue status
- Browse the movie library
- Show recently added movies

Guidelines:
- When a user asks for a movie, check Plex first to see if it's already available.
- If a movie isn't in the library, offer to add it to Radarr for download.
- Be conversational and make recommendations based on what the user describes.
- When showing search results, highlight the most relevant matches.
- If the user asks for something vague like "a good sci-fi movie", use search creatively.
- Always confirm before adding a movie to Radarr for download.
"""

# ── State ─────────────────────────────────────────────────────

# Conversation history per session (in-memory, fine for single user)
sessions: dict[str, list[dict]] = defaultdict(list)

# MCP client and agent are initialized on startup
mcp_client: MCPClient | None = None
agent: Agent | None = None


# ── App ───────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start MCP client connection and create agent on startup."""
    global mcp_client, agent

    logger.info(f"Connecting to Movie MCP Server at {MOVIE_MCP_URL}")

    mcp_client = MCPClient(
        lambda: streamablehttp_client(url=f"{MOVIE_MCP_URL}/mcp")
    )

    # Retry connection — MCP server may still be starting up
    for attempt in range(5):
        try:
            mcp_client.__enter__()
            break
        except Exception:
            if attempt == 4:
                raise
            wait = 2 ** (attempt + 1)
            logger.warning(f"MCP connection attempt {attempt + 1} failed, retrying in {wait}s...")
            time.sleep(wait)

    tools = mcp_client.list_tools_sync()
    logger.info(f"Loaded {len(tools)} tools from Movie MCP Server")

    model = AnthropicModel(
        client_args={"api_key": ANTHROPIC_API_KEY},
        model_id=MODEL_ID,
        max_tokens=1024,
    )

    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=tools,
    )

    logger.info("Movie Agent ready")
    yield

    # Cleanup
    if mcp_client:
        mcp_client.__exit__(None, None, None)
    logger.info("Movie Agent shut down")


app = FastAPI(title="Movie Agent", lifespan=lifespan)


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
    """Handle a chat message. Sends to the Strands Agent with conversation history."""
    if agent is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Agent not initialized yet."},
        )

    session_id = req.session_id or str(uuid.uuid4())

    # Add user message to history
    sessions[session_id].append({"role": "user", "content": req.message})

    try:
        with langfuse.start_as_current_observation(as_type="span", name="movie-agent-chat"):
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
    return {"status": "ok", "agent_ready": agent is not None}


# ── Run ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
