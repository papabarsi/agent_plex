import os
import logging

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webui")

MEDIA_AGENT_URL = os.environ.get("MEDIA_AGENT_URL", "http://media-agent:8000")

app = FastAPI(title="Media Agent WebUI")


# ── Models ────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


# ── Endpoints ─────────────────────────────────────────────────

@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Proxy chat messages to the Media Agent orchestrator."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{MEDIA_AGENT_URL}/chat",
                json={"message": req.message, "session_id": req.session_id},
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        logger.error(f"Cannot connect to Media Agent at {MEDIA_AGENT_URL}")
        return JSONResponse(
            status_code=502,
            content={"error": "Cannot connect to Media Agent. Is it running?"},
        )
    except httpx.HTTPStatusError as e:
        logger.error(f"Agent returned error: {e.response.status_code}")
        return JSONResponse(
            status_code=e.response.status_code,
            content={"error": f"Agent error: {e.response.text}"},
        )
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": str(e)},
        )


@app.get("/api/health")
async def health():
    """Check if the Media Agent is reachable."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{MEDIA_AGENT_URL}/health")
            agent_health = resp.json()
    except Exception:
        agent_health = {"status": "unreachable"}

    return {"webui": "ok", "agent": agent_health}


@app.get("/")
async def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
