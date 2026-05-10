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

## LLM Provider

The default model alias is `nemotron-3-free`, configured in `litellm/config.yaml` as
`openrouter/nvidia/nemotron-3-nano-30b-a3b:free`.

For local Docker Compose runs, inject the OpenRouter token with 1Password:

```bash
op run --env-file .env.op -- docker compose up -d litellm movie-agent tv-agent media-agent
```

`.env.op` stores only a 1Password secret reference and is ignored by git.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **media** (392 symbols, 450 relationships, 3 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/media/context` | Codebase overview, check index freshness |
| `gitnexus://repo/media/clusters` | All functional areas |
| `gitnexus://repo/media/processes` | All execution flows |
| `gitnexus://repo/media/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
