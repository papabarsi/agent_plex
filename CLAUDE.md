# Media Agent Stack

## Project Overview

A multi-agent media management system deployed as Docker containers via Portainer.

Built with **Strands Agents SDK** + **MCP** + **LiteLLM** + **OpenRouter**.

## Architecture

### Stage 2 — Media Multi Agent (CURRENT)

```
WebUI (:3000) → Media Agent (:8000) → Movie Agent (:8001) → Movie MCP Server (:8101) → Radarr + Plex (LAN)
                   (orchestrator)   → TV Agent (:8002)    → TV MCP Server (:8102)    → Sonarr + Plex (LAN)
                        ↕
                  LiteLLM → OpenRouter → NVIDIA Nemotron 3 Nano 30B A3B (free)
```

The Media Agent is an orchestrator that routes user requests to the appropriate sub-agent(s) via HTTP.
It uses Strands Agent with `movie_agent` and `tv_agent` as callable tools.

### Previous Stages

- **Stage 1**: Movie Agent + Movie MCP Server (direct WebUI → Agent)
- **Stage 1b**: Added TV Agent + TV MCP Server with mode toggle in WebUI

### Future — Strands Agent-as-Tool

Refactor to use Strands native agent-as-tool pattern where sub-agents are instantiated
directly inside the Media Agent process instead of called via HTTP.

## Tech Stack

- Python 3.12
- `strands-agents[openai]` — agent framework with OpenAI-compatible model provider
- `mcp` with `FastMCP` — MCP server SDK
- `strands.tools.mcp.MCPClient` — MCP client (built into Strands)
- FastAPI + uvicorn — HTTP servers
- httpx — async HTTP client
- Docker + docker-compose
- LiteLLM — in-stack OpenAI-compatible gateway to OpenRouter

## Observability (Langfuse)

Self-hosted Langfuse v3 provides tracing and session tracking for all agents.

- **Platform**: `langfuse/langfuse:3` (docker-compose services: langfuse-web, langfuse-worker, langfuse-postgres, langfuse-clickhouse, langfuse-minio, langfuse-redis)
- **SDK**: `langfuse>=3,<4` — pinned to v3 to match the platform (v4 SDK has incompatibilities with the v3 platform)
- **Session tracing**: Each agent wraps `agent()` calls in `langfuse.start_as_current_observation()` + `propagate_attributes(session_id=...)` to group traces into sessions
- **Config**: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` env vars (see `env.example`)

## Deployment

- Target: bare-metal Ubuntu Docker host (Portainer stack)
- External services on LAN: Radarr (:7878), Sonarr (:8989), Plex (:32400)

## Host Networking Notes

The host is **bare-metal Ubuntu** — there is no Proxmox/LXC layer. Docker bridge
networking works normally (outbound internet, DNS, inter-container DNS,
published ports). Historical LXC/AppArmor workarounds were removed from these
docs 2026-07-11 after verification; do not reintroduce them.

Two things future agents should know:

1. **Cloudflare tunnel routing**: `cloudflared` runs as a systemd service *on
   the host* and its ingress targets `http://localhost:<port>`. Any service
   exposed through the tunnel must be reachable on host loopback — either
   `network_mode: host` or a published `ports:` mapping. Bridge-only internal
   ports are not reachable by the tunnel.
2. **Leftover `security_opt: apparmor:unconfined`** entries in some compose
   files date from the old LXC deployment. They are not required on this host
   (they disable AppArmor confinement); don't copy them into new services.

## Rebuilding Agent Images

The agent services (movie-agent, tv-agent, media-agent) use locally built images
(`image: movie-agent:latest` etc.), NOT `build:` directives in docker-compose.yml.
This means `docker compose build` does nothing for them.

To rebuild after code or dependency changes:

```bash
docker build --no-cache -t movie-agent:latest ./movie-agent
docker build --no-cache -t tv-agent:latest ./tv-agent
docker build --no-cache -t media-agent:latest ./media-agent
docker compose up -d --force-recreate movie-agent tv-agent media-agent
```

Use `--no-cache` when changing pinned dependency versions to avoid stale pip layers.

## LLM Provider

The default model alias is `nemotron-3-free`, configured in `litellm/config.yaml` as
`openrouter/nvidia/nemotron-3-nano-30b-a3b:free`.

For local Docker Compose runs, inject the OpenRouter token with 1Password:

```bash
op run --env-file .env.op -- docker compose up -d litellm movie-agent tv-agent media-agent
```

`.env.op` stores only a 1Password secret reference and is ignored by git.

