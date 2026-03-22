# Media Agent Stack

## Project Overview

A multi-agent media management system deployed as Docker containers via Portainer.

Built with **Strands Agents SDK** + **MCP** + **Claude Haiku 4.5** (Anthropic API).

## Architecture

### Stage 2 — Media Multi Agent (CURRENT)

```
WebUI (:3000) → Media Agent (:8000) → Movie Agent (:8001) → Movie MCP Server (:8101) → Radarr + Plex (LAN)
                   (orchestrator)   → TV Agent (:8002)    → TV MCP Server (:8102)    → Sonarr + Plex (LAN)
                        ↕
                  Claude API (Haiku 4.5)
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
- `strands-agents[anthropic]` — agent framework
- `mcp` with `FastMCP` — MCP server SDK
- `strands.tools.mcp.MCPClient` — MCP client (built into Strands)
- FastAPI + uvicorn — HTTP servers
- httpx — async HTTP client
- Docker + docker-compose

## Observability (Langfuse)

Self-hosted Langfuse v3 provides tracing and session tracking for all agents.

- **Platform**: `langfuse/langfuse:3` (docker-compose services: langfuse-web, langfuse-worker, langfuse-postgres, langfuse-clickhouse, langfuse-minio, langfuse-redis)
- **SDK**: `langfuse>=3,<4` — pinned to v3 to match the platform (v4 SDK has incompatibilities with the v3 platform)
- **Session tracing**: Each agent wraps `agent()` calls in `langfuse.start_as_current_observation()` + `propagate_attributes(session_id=...)` to group traces into sessions
- **Config**: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` env vars (see `env.example`)

## Deployment

- Target: Proxmox LXC Docker host via Portainer stack
- External services on LAN: Radarr (:7878), Sonarr (:8989), Plex (:32400)

## LXC + Docker Setup (Proxmox)

Running Docker inside an unprivileged LXC container requires specific configuration.
These steps must be done **before installing Docker** for best results.

### 1. Proxmox LXC Config (`/etc/pve/lxc/<CT_ID>.conf`)

Add these three lines:

```
lxc.mount.auto: proc:rw sys:rw
lxc.apparmor.profile: unconfined
lxc.mount.entry: /sys/kernel/security sys/kernel/security none bind,optional 0 0
```

Then restart the container: `pct stop <CT_ID> && pct start <CT_ID>`

### 2. AppArmor Fix for Docker Builds

Even with the LXC config above, `docker build` fails with:
```
unable to apply apparmor profile: apparmor failed to apply profile: write fsmount:fscontext:proc/thread-self/attr/apparmor/exec: no such file or directory
```

**Fix**: Hide `apparmor_parser` so runc skips AppArmor entirely:

```bash
sudo mv /sbin/apparmor_parser /sbin/apparmor_parser.bak
sudo systemctl restart docker
```

This must be done on each Docker LXC host. To undo: `sudo mv /sbin/apparmor_parser.bak /sbin/apparmor_parser`

### 3. Portainer Agent

The Portainer agent container must be created with `--security-opt apparmor=unconfined`,
otherwise it fails with `permission denied` on `/sys/kernel/security/apparmor/profiles`.

Every time Docker is restarted, the agent container dies and must be recreated:

```bash
docker rm -f portainer_agent
docker run -d \
  --name portainer_agent \
  --restart=always \
  --security-opt apparmor=unconfined \
  -p 9001:9001 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /var/lib/docker/volumes:/var/lib/docker/volumes \
  portainer/agent:2.39.0
```

### 4. Docker Compose Services

All services in `docker-compose.yml` need `security_opt: apparmor:unconfined`
to run inside the LXC container.

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
