# Media Agent Stack

AI-powered media management using Strands Agents + MCP + OpenRouter.

## Quick Start

1. Copy `env.example` to `.env` and fill in your API keys and service URLs
2. Deploy as a Portainer stack or run:

```bash
docker-compose up --build
```

3. Open `http://<host-ip>:3000` in your browser

## Architecture

```
WebUI (:3000) → Media Agent (:8000) → Movie Agent (:8001) → Movie MCP (:8101) → Radarr + Plex
                   (orchestrator)   → TV Agent (:8002)    → TV MCP (:8102)    → Sonarr + Plex
                        ↕
                  LiteLLM → OpenRouter → NVIDIA Nemotron 3 Nano 30B A3B (free)
```

## What it does

- **Search** for movies and TV shows by title, genre, mood, or description
- **Check** if media is already in your Plex library
- **Add** movies to Radarr or series to Sonarr for automatic download
- **Monitor** download queue progress
- **Browse** your full movie and TV library
- **Intelligent routing** — ask about movies and TV in a single conversation

## Stages

- **Stage 1**: Movie Agent + Movie MCP Server
- **Stage 1b**: Added TV Agent + TV MCP Server (Sonarr)
- **Stage 2** (current): Media Agent orchestrator — unified chat, routes to sub-agents
- **Future**: Strands agent-as-tool refactor for native sub-agent orchestration

## Configuration

Copy `env.example` to `.env` and fill in:

- `OPENROUTER_API_KEY` — your OpenRouter API key
- `MODEL_ID` — optional LiteLLM model alias; defaults to `nemotron-3-free`
- `RADARR_URL` / `RADARR_API_KEY` — your Radarr instance
- `SONARR_URL` / `SONARR_API_KEY` — your Sonarr instance
- `PLEX_URL` / `PLEX_TOKEN` — your Plex instance
