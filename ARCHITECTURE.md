# media — Architecture

## Purpose

A multi-agent media management stack that lets a single user manage their home
Plex library through natural-language chat. A web UI proxies requests to an
orchestrator agent, which routes to specialist movie/TV agents; those agents
call MCP tool servers that wrap Radarr, Sonarr, and Plex REST APIs. The
contract: given a chat message, the system answers questions about the local
Plex library and queues new movies/series in Radarr/Sonarr without the user
ever opening those *arr UIs directly.

## Components

| Component | Path | Responsibility | Runtime |
|---|---|---|---|
| `webui` | `webui/` | Static chat UI + thin proxy to the orchestrator | Docker (`media-webui`, :3000) |
| `media-agent` | `media-agent/` | Orchestrator; routes user messages to movie/tv sub-agents via HTTP `@tool`s | Docker (`media-agent`, :8000) |
| `movie-agent` | `movie-agent/` | Movie specialist Strands agent; consumes movie MCP tools | Docker (`movie-agent`, :8001) |
| `tv-agent` | `tv-agent/` | TV specialist Strands agent; consumes tv MCP tools | Docker (`tv-agent`, :8002) |
| `movie-mcp-server` | `movie-mcp-server/` | FastMCP server wrapping Radarr + Plex movie endpoints | Docker (`movie-mcp-server`, :8101) |
| `tv-mcp-server` | `tv-mcp-server/` | FastMCP server wrapping Sonarr + Plex TV endpoints | Docker (`tv-mcp-server`, :8102) |
| `litellm` | `litellm/config.yaml` | OpenAI-compatible LLM proxy, fans out to OpenRouter/Anthropic, emits Langfuse traces | Docker (`litellm`, :4001 host → :4000 container) |
| `langfuse-web` | (compose service) | Langfuse v3 UI + ingest | Docker (`langfuse-web`, :3001) |
| `langfuse-worker` | (compose service) | Langfuse v3 async event processor | Docker (`langfuse-worker`) |
| `langfuse-postgres` | (compose service) | Metadata store for Langfuse | Docker (`langfuse-postgres`) |
| `langfuse-clickhouse` | (compose service) | Trace/event store for Langfuse | Docker (`langfuse-clickhouse`) |
| `langfuse-minio` | (compose service) | S3-compatible blob store for Langfuse uploads | Docker (`langfuse-minio`, :9090) |
| `langfuse-redis` | (compose service) | Queue/cache for Langfuse worker | Docker (`langfuse-redis`) |

Built with **Strands Agents SDK** (`strands-agents[openai,otel]`) and the
**MCP** Python SDK (`mcp` + `FastMCP`, streamable-HTTP transport). All
inter-service calls are HTTP within the `media-agent-net` bridge network.

## Dependencies

| Dependency | Kind | Hard / Soft | Failure Mode |
|---|---|---|---|
| OpenRouter (Nemotron 3 Nano 30B A3B free) | LLM | hard | All agents 5xx on `/chat`; LiteLLM returns upstream error |
| LiteLLM proxy | LLM gateway | hard | Agents fail to obtain model on startup; `/chat` returns the captured exception |
| Radarr (LAN, :7878) | media indexer/downloader | hard for movie ops | `movie-mcp-server` tool calls raise; movie-agent surfaces the error in chat |
| Sonarr (LAN, :8989) | media indexer/downloader | hard for TV ops | `tv-mcp-server` tool calls raise; tv-agent surfaces the error in chat |
| Plex (LAN, :32400) | library/playback | hard for "is it in library" lookups | MCP tool returns error string; agent reports unavailability |
| Langfuse v3 self-hosted | observability | soft | Agents log `Langfuse unreachable — tracing disabled` and continue (`media-agent/agent.py:21-27`) |
| Anthropic API (`ANTHROPIC_API_KEY`) | LLM | soft | Only used by the Claude model aliases in `litellm/config.yaml:8-25`; Nemotron path unaffected |
| Postgres 17 / ClickHouse / MinIO / Redis 7 | Langfuse backing | hard for Langfuse only | Langfuse degrades; agents continue (see soft Langfuse above) |

Pinned versions of note:
- `langfuse>=3,<4` (SDK pinned to match self-hosted v3 platform — CLAUDE.md §Observability).
- `ghcr.io/berriai/litellm:v1.83.7-stable` (`docker-compose.yml:141`, pinned for CVE-2026-42208 per commit `6cd026a`).
- `docker.io/langfuse/langfuse:3`, `docker.io/postgres:17`, `docker.io/redis:7`.

## Integrations

| Direction | Integration | Protocol | Auth | Notes |
|---|---|---|---|---|
| out | OpenRouter | HTTPS (OpenAI-compatible) | `OPENROUTER_API_KEY` | Via LiteLLM, model alias `nemotron-3-free` (`litellm/config.yaml:2-6`) |
| out | Anthropic API | HTTPS | `ANTHROPIC_API_KEY` (optional) | Only for the Claude aliases in `litellm/config.yaml:8-25`; not used by default media routes |
| out | Radarr REST v3 | HTTP | `X-Api-Key` header | `movie-mcp-server/server.py:14-15` |
| out | Sonarr REST v3 | HTTP | `X-Api-Key` header | `tv-mcp-server/` |
| out | Plex | HTTP | `X-Plex-Token` header | `movie-mcp-server/server.py:18-19` |
| internal | media-agent → movie-agent / tv-agent | HTTP JSON `/chat` | none (intra-network) | `media-agent/agent.py:74-109` |
| internal | movie-agent / tv-agent → MCP server | MCP streamable-HTTP | none | `MCPClient(streamablehttp_client(...))` in `movie-agent/agent.py` |
| internal | webui → media-agent | HTTP JSON `/chat` | none | `webui/server.py:27-37` |
| out | Langfuse ingest (OTEL) | HTTP | public/secret key pair | `LANGFUSE_*` env vars; Strands exports via OTEL BSP |
| in | User chat | HTTP browser → `:3000` | none | LAN-only deployment |

## Data Model

The stack is **stateless across restarts** for the agent/MCP services.
Conversation state lives entirely in process memory:

- `media-agent/agent.py:55` — `sessions: dict[str, list[dict]]` keyed by
  `session_id` (UUID, generated server-side if not supplied), holding the
  raw `{"role": ..., "content": ...}` turns.
- `media-agent/agent.py:56` — `agents: dict[str, Agent]`, one Strands `Agent`
  instance per session. The Strands agent owns its own internal conversation
  state; the `sessions` dict above is kept for echoing only.
- `movie-agent/agent.py` and `tv-agent/agent.py` mirror this shape with their
  own per-session dicts.

A process restart discards all sessions. There is no database for chat
history; this is intentional for a single-user home deployment.

Persistent state belongs to Langfuse and its backing stores:

| Volume | Backing service | Contents |
|---|---|---|
| `langfuse_postgres_data` | `langfuse-postgres` | Langfuse metadata: orgs, projects, users, traces index |
| `langfuse_clickhouse_data` / `langfuse_clickhouse_logs` | `langfuse-clickhouse` | Trace events, scores, observations |
| `langfuse_minio_data` | `langfuse-minio` | Uploaded event blobs and media |
| `langfuse_redis_data` | `langfuse-redis` | Queue + cache for the Langfuse worker |

Tool I/O over MCP is plain text/JSON; no schema is persisted between calls.
Radarr/Sonarr/Plex hold their own libraries — this stack does not duplicate
them.

## Configuration & Secrets

| Variable | Required | Source | Purpose |
|---|---|---|---|
| `OPENROUTER_API_KEY` | yes | 1Password (via `.env.op`, see CLAUDE.md §LLM Provider) | OpenRouter access for the default Nemotron model |
| `ANTHROPIC_API_KEY` | optional | 1Password | Only needed if the Claude aliases in `litellm/config.yaml` are exercised |
| `LITELLM_API_KEY` | optional | env (defaults to `sk-local`) | Client-side key for the in-stack LiteLLM proxy; treated as a shared secret on the internal network |
| `MODEL_ID` | optional | env (default `nemotron-3-free`) | Which LiteLLM alias the agents request |
| `LLM_MAX_TOKENS` | optional | env (default `4096`) | Output cap per agent turn |
| `RADARR_URL` | yes | `.env` | Movie MCP target |
| `RADARR_API_KEY` | yes | `.env` | Radarr auth |
| `RADARR_QUALITY_PROFILE_ID` | optional | `.env` (default `1`) | Profile used when adding movies |
| `SONARR_URL` | yes | `.env` | TV MCP target |
| `SONARR_API_KEY` | yes | `.env` | Sonarr auth |
| `SONARR_QUALITY_PROFILE_ID` | optional | `.env` (default `1`) | Profile used when adding series |
| `PLEX_URL` | yes | `.env` | Plex base URL |
| `PLEX_TOKEN` | yes | `.env` | Plex auth |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | optional | `.env` (must match `LANGFUSE_INIT_PROJECT_*`) | Agent → Langfuse auth |
| `LANGFUSE_URL` | yes for first-boot init | `.env` | Public URL of the Langfuse web UI |
| `LANGFUSE_NEXTAUTH_SECRET` / `LANGFUSE_SALT` / `LANGFUSE_ENCRYPTION_KEY` | yes for Langfuse | `.env` | Required Langfuse secrets; defaults in compose are placeholders |
| `LANGFUSE_INIT_*` | optional | `.env` | Seeds org/project/admin user on first Langfuse boot |
| `LANGFUSE_CLICKHOUSE_PASSWORD` / `LANGFUSE_MINIO_PASSWORD` / `LANGFUSE_REDIS_PASSWORD` | optional | `.env` (compose defaults exist) | Backing-store passwords |
| `OTEL_BSP_*` / `OTEL_EXPORTER_OTLP_TIMEOUT` | tuned in compose | `docker-compose.yml:34-38` | Bound OTEL batch exporter so a Langfuse outage cannot block agent shutdown (commit `16d1d50`) |

Source-of-truth conventions:
- Local-dev runs use `op run --env-file .env.op -- docker compose up -d ...`
  to resolve 1Password references (CLAUDE.md §LLM Provider).
- `.env` itself is gitignored; `env.example` is the schema (committed).

## Patterns Used

- **PAT-08 (retired 2026-07-11)** — `docker-compose.yml:330-332` — this
  compose file runs on a user-defined bridge network (`media-agent-net`)
  with explicit `ports:` mappings, which is the correct configuration: the
  host is bare-metal Ubuntu and bridge networking has full egress/DNS
  (verified 2026-07-11). The old LXC-era guidance mandating
  `network_mode: host` no longer applies. Note the Cloudflare tunnel targets
  `localhost:3000` for `media.happylandagt.com`, served here by the
  published `media-webui` port.
- **PAT-09 (inverse)** — `litellm/config.yaml:8-25` / `docker-compose.yml:152`
  — *Inverse of the shared pattern. PAT-09 mandates OAuth subscription
  credentials for Claude **Code** workloads; the media agents are explicitly
  the documented exception and use the Anthropic **API key** for Claude
  aliases routed through LiteLLM. The default media path uses OpenRouter
  (Nemotron free tier), not Anthropic, so the API key is optional in
  practice.*
- **LL-01 leftover (retired 2026-07-11)** —
  `docker-compose.yml:7,21,49,67,95,113,144,167,...` — Every service still
  declares `security_opt: ["apparmor:unconfined"]`, a leftover from the
  retired LXC AppArmor fix. Not required on the bare-metal host (it disables
  AppArmor confinement); do not copy into new services.

The other shared patterns (PAT-01..07, PAT-10..14) do not apply: this stack
has no external-source preflight, no quota-limited free-tier APIs in the
data path beyond OpenRouter (which is rate-limited by HTTP status, not by a
daily counter), no APScheduler jobs, and no `subprocess` calls to the Claude
CLI. (Cloudflare Tunnel ingress: `media.happylandagt.com` →
`localhost:3000` → the published `media-webui` port.)

## Lessons Learned

#### LXC AppArmor lesson retired — 2026-07-11
The former "LXC AppArmor blocks unprivileged Docker" lesson (shared LL-01)
was retired: the deployment host is bare-metal Ubuntu, not a Proxmox LXC, so
the AppArmor workarounds no longer apply. The
`security_opt: ["apparmor:unconfined"]` entries still present throughout
`docker-compose.yml` are inert legacy from that era — safe to leave, but do
not copy into new services (they disable AppArmor confinement for no
benefit).

#### OTEL batch exporter blocks on Langfuse outage — 2026-04-XX (commit `16d1d50`)
**Symptom:** When Langfuse was unreachable, agent containers became
unresponsive on shutdown/reload because the OTEL batch span processor
queued indefinitely and held the process open.
**Root cause:** Default OTEL BSP timeouts and queue sizes assume a healthy
collector; with Langfuse down, the exporter buffered until shutdown then
blocked on flush.
**Fix:** Pin BSP knobs in `docker-compose.yml` for every agent service —
`OTEL_BSP_SCHEDULE_DELAY_MILLIS=5000`, `OTEL_BSP_MAX_QUEUE_SIZE=2048`,
`OTEL_BSP_MAX_EXPORT_BATCH_SIZE=512`, `OTEL_BSP_EXPORT_TIMEOUT_MILLIS=2000`,
`OTEL_EXPORTER_OTLP_TIMEOUT=2000` (lines 34-38, 80-84, 127-131). Combined
with the soft-Langfuse pattern at `media-agent/agent.py:21-27`, a Langfuse
outage now degrades silently rather than wedging agent startup/shutdown.
**Guardrail:** OTEL env vars are kept in compose (not in image defaults)
so an operator can re-tune without rebuilding images.

#### LiteLLM CVE-2026-42208 — 2026-04-XX (commit `6cd026a`)
**Symptom:** Public CVE against unpinned LiteLLM images.
**Root cause:** `latest` tag tracked an affected version.
**Fix:** Pin to `ghcr.io/berriai/litellm:v1.83.7-stable`
(`docker-compose.yml:141`).
**Guardrail:** No `latest` tags in this compose file; LLM proxy upgrades
must be explicit commits so the pin can be audited.

#### Locally built images, not `build:` directives — 2026-04-XX
**Symptom:** `docker compose build` reported success but agent code
changes never took effect; restart cycled the old image.
**Root cause:** The agent services in `docker-compose.yml` declare
`image: movie-agent:latest` etc. without a `build:` block (lines 18, 64,
110), so compose neither builds nor pulls — it just runs whatever the
local Docker daemon already has tagged. A separate
`docker-compose.build.yml` (referenced by `build.sh:7`) holds the build
context.
**Fix:** The documented workflow is
`docker build --no-cache -t <name>:latest ./<dir>` followed by
`docker compose up -d --force-recreate <services>`
(`CLAUDE.md §Rebuilding Agent Images`). `--no-cache` is required when
`requirements.txt` changes, because pip layers are otherwise reused.
**Guardrail:** `build.sh` is the canonical entry point and points at
`docker-compose.build.yml`; the operator runbook in `CLAUDE.md`
discourages reliance on `docker compose build` against
`docker-compose.yml`.

#### Agent startup crash + wrong quality profile — 2026-04-XX (commit `7cb7fc9`)
**Symptom:** Movie/TV agent containers crashed on first chat; added
items landed in Radarr/Sonarr at the wrong quality.
**Root cause:** Combined fix — startup ordering / MCP client init bug,
plus a hard-coded quality profile ID that didn't match the operator's
Radarr/Sonarr config.
**Fix:** `RADARR_QUALITY_PROFILE_ID` / `SONARR_QUALITY_PROFILE_ID` were
made env-configurable (`movie-mcp-server/server.py:11`,
`docker-compose.yml:58, 104`), and startup logic was hardened.
**Guardrail:** Quality profile IDs live in `env.example` so any new
deployment notices they exist.

## Known Gaps & Risks

- **No persistence for chat history.** A `media-agent` restart wipes every
  active session (`media-agent/agent.py:55-56`). For a single-user home
  deployment this is acceptable; surfacing it here so an upgrade does not
  surprise the operator mid-conversation.
- **Per-session `Agent` instances grow without bound.** The `agents` dict in
  each agent process is never pruned. Long-running deployments will leak
  memory proportional to unique `session_id`s. Mitigation today: restart
  the container; production fix would be a TTL eviction.
- **Sub-agent calls are synchronous HTTP with a 60 s timeout
  (`media-agent/agent.py:75, 100`).** A slow MCP tool (Plex library scan,
  Radarr lookup) can stall the orchestrator turn. Strands does not retry;
  the user gets `"Movie Agent is unavailable: ..."`.
- **In-stack `LITELLM_API_KEY` defaults to `sk-local`** (`docker-compose.yml:26,
  72, 118`). The LiteLLM proxy is only on the internal bridge network, so
  this is acceptable, but any future exposure of `:4001` to the LAN would
  effectively be open.
- **No automated tests in CI.** `movie-agent/tests/` and
  `media-agent/tests/` exist but are not wired to a CI pipeline; build.sh
  only builds images.
- **Doc drift between READMEs.** `/home/barsi/projects/CLAUDE.md` (parent
  doc) still describes this stack as Strands + direct Anthropic API
  (Sonnet 4.5 / Haiku 4.5). The committed code (`media-agent/agent.py:12-13`,
  `litellm/config.yaml:2-6`) routes through LiteLLM → OpenRouter Nemotron
  by default. The parent doc should be updated; this `ARCHITECTURE.md` is
  the source of truth.
- ~~PAT-08 deviation~~ — resolved 2026-07-11: bridge networking with
  `ports:` is the correct configuration on the bare-metal host (PAT-08/LL-02
  retired); no host-networking migration is needed.

## 10. Health Checks

```yaml
checks:
  - id: media-agent-container
    description: Orchestrator media-agent container running
    type: container
    name: media-agent
    severity: critical
    interval: 5m
    owner: media-agent
    remediation: "docker compose -f /home/barsi/projects/media/docker-compose.yml up -d media-agent"

  - id: movie-agent-container
    description: Movie agent container running
    type: container
    name: movie-agent
    severity: warning
    interval: 5m
    owner: movie-agent

  - id: tv-agent-container
    description: TV agent container running
    type: container
    name: tv-agent
    severity: warning
    interval: 5m
    owner: tv-agent

  - id: movie-mcp-container
    description: Movie MCP server container running
    type: container
    name: movie-mcp-server
    severity: warning
    interval: 5m
    owner: movie-mcp-server

  - id: tv-mcp-container
    description: TV MCP server container running
    type: container
    name: tv-mcp-server
    severity: warning
    interval: 5m
    owner: tv-mcp-server

  - id: webui-container
    description: WebUI container running
    type: container
    name: media-webui
    severity: warning
    interval: 5m
    owner: webui

  - id: webui-http
    description: WebUI reachable on :3000
    type: http
    url: http://localhost:3000/
    expect_status: 200
    severity: warning
    interval: 10m
    owner: webui

  - id: litellm-http
    description: Media-stack LiteLLM proxy reachable on :4001
    type: http
    url: http://localhost:4001/health
    expect_status: 200
    severity: warning
    interval: 10m
    owner: litellm
    # verify: 200 confirmed via curl during §10 backfill (2026-05-11).
```
