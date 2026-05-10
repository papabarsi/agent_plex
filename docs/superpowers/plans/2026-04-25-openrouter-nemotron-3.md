# OpenRouter Nemotron 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the media stack's Strands LLM provider from Anthropic to OpenRouter, defaulting to OpenRouter's free NVIDIA Nemotron 3 Nano 30B A3B model.

**Architecture:** Keep the existing LiteLLM gateway and Langfuse tracing path. Each Strands agent uses `OpenAIModel` against LiteLLM's OpenAI-compatible `/v1` API, while LiteLLM maps a local alias to `openrouter/nvidia/nemotron-3-nano-30b-a3b:free`.

**Tech Stack:** Python 3.12, Strands Agents SDK `OpenAIModel`, LiteLLM proxy, OpenRouter, FastAPI, pytest, Docker Compose.

---

## Review Findings

- `media/media-agent/agent.py`, `media/movie-agent/agent.py`, and `media/tv-agent/agent.py` all import `AnthropicModel` and read `ANTHROPIC_API_KEY`, so changing only the orchestrator leaves the sub-agents on Claude.
- The current working tree has a new `media/litellm/config.yaml` and Compose wiring for `LITELLM_BASE_URL`, but the agents still instantiate an Anthropic provider. For OpenRouter, use Strands `OpenAIModel` because OpenRouter and LiteLLM both expose OpenAI-compatible chat completions.
- `LITELLM_BASE_URL` is currently `http://litellm:4000`. For OpenAI SDK compatibility, set it to `http://litellm:4000/v1`.
- `media/README.md`, `media/CLAUDE.md`, and `media/env.example` still describe Claude/Anthropic as the primary provider.
- There are no existing tests under `media/`; add focused provider configuration tests before changing runtime code.
- The in-memory `sessions` lists are appended to but not passed into `agent(...)`. This is unrelated to the provider switch and should not be refactored in this change.

## Target Files

- Modify `media/litellm/config.yaml`: add the OpenRouter Nemotron 3 free alias and route it with `OPENROUTER_API_KEY`.
- Modify `media/docker-compose.yml`: pass OpenAI-compatible LiteLLM URLs and model aliases to all three agents; pass `OPENROUTER_API_KEY` to LiteLLM.
- Modify `media/env.example`: replace Anthropic-first configuration with OpenRouter-first configuration.
- Modify `media/media-agent/requirements.txt`, `media/movie-agent/requirements.txt`, `media/tv-agent/requirements.txt`: install the Strands OpenAI provider extra.
- Modify `media/media-agent/agent.py`, `media/movie-agent/agent.py`, `media/tv-agent/agent.py`: replace `AnthropicModel` construction with `OpenAIModel`.
- Add `media/media-agent/tests/test_model_config.py`, `media/movie-agent/tests/test_model_config.py`, `media/tv-agent/tests/test_model_config.py`: prove default and overridden model configuration without making network calls.
- Modify `media/README.md` and `media/CLAUDE.md`: document OpenRouter, the Nemotron model alias, rebuild commands, and fallback options.

### Task 1: Add Provider Configuration Tests

**Files:**
- Create: `media/media-agent/tests/test_model_config.py`
- Create: `media/movie-agent/tests/test_model_config.py`
- Create: `media/tv-agent/tests/test_model_config.py`

- [ ] **Step 1: Create the media-agent provider test**

```python
import importlib


def test_default_model_config(monkeypatch):
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_ID", raising=False)

    agent = importlib.reload(importlib.import_module("agent"))

    model = agent.build_model()
    config = model.get_config()

    assert config["model_id"] == "nemotron-3-free"
    assert config["params"]["max_tokens"] == 1024


def test_model_config_honors_environment(monkeypatch):
    monkeypatch.setenv("LITELLM_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-or-test")
    monkeypatch.setenv("MODEL_ID", "nvidia/nemotron-3-nano-30b-a3b:free")

    agent = importlib.reload(importlib.import_module("agent"))

    model = agent.build_model()
    config = model.get_config()

    assert config["model_id"] == "nvidia/nemotron-3-nano-30b-a3b:free"
    assert config["params"]["max_tokens"] == 1024
```

- [ ] **Step 2: Create the movie-agent provider test**

```python
import importlib


def test_default_model_config(monkeypatch):
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_ID", raising=False)

    agent = importlib.reload(importlib.import_module("agent"))

    model = agent.build_model()
    config = model.get_config()

    assert config["model_id"] == "nemotron-3-free"
    assert config["params"]["max_tokens"] == 1024


def test_model_config_honors_environment(monkeypatch):
    monkeypatch.setenv("LITELLM_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-or-test")
    monkeypatch.setenv("MODEL_ID", "nvidia/nemotron-3-nano-30b-a3b:free")

    agent = importlib.reload(importlib.import_module("agent"))

    model = agent.build_model()
    config = model.get_config()

    assert config["model_id"] == "nvidia/nemotron-3-nano-30b-a3b:free"
    assert config["params"]["max_tokens"] == 1024
```

- [ ] **Step 3: Create the tv-agent provider test**

```python
import importlib


def test_default_model_config(monkeypatch):
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_ID", raising=False)

    agent = importlib.reload(importlib.import_module("agent"))

    model = agent.build_model()
    config = model.get_config()

    assert config["model_id"] == "nemotron-3-free"
    assert config["params"]["max_tokens"] == 1024


def test_model_config_honors_environment(monkeypatch):
    monkeypatch.setenv("LITELLM_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-or-test")
    monkeypatch.setenv("MODEL_ID", "nvidia/nemotron-3-nano-30b-a3b:free")

    agent = importlib.reload(importlib.import_module("agent"))

    model = agent.build_model()
    config = model.get_config()

    assert config["model_id"] == "nvidia/nemotron-3-nano-30b-a3b:free"
    assert config["params"]["max_tokens"] == 1024
```

- [ ] **Step 4: Run the tests to verify they fail before implementation**

Run:

```bash
cd /home/barsi/projects/media/media-agent && python -m pytest tests/test_model_config.py -v
cd /home/barsi/projects/media/movie-agent && python -m pytest tests/test_model_config.py -v
cd /home/barsi/projects/media/tv-agent && python -m pytest tests/test_model_config.py -v
```

Expected: each test run fails because `agent.build_model` does not exist yet.

### Task 2: Switch Agent Runtime Code to OpenAIModel

**Files:**
- Modify: `media/media-agent/agent.py`
- Modify: `media/movie-agent/agent.py`
- Modify: `media/tv-agent/agent.py`

- [ ] **Step 1: Replace the model import in all three agent files**

Change:

```python
from strands.models.anthropic import AnthropicModel
```

To:

```python
from strands.models.openai import OpenAIModel
```

- [ ] **Step 2: Replace Anthropic-specific config in all three agent files**

Change the config block from:

```python
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
```

To:

```python
LLM_API_KEY = os.environ.get("LLM_API_KEY", "sk-local")
```

Keep each service's existing URL variable, then set:

```python
LITELLM_BASE_URL = os.environ.get("LITELLM_BASE_URL", "http://litellm:4000/v1")
MODEL_ID = os.environ.get("MODEL_ID", "nemotron-3-free")
```

- [ ] **Step 3: Add `build_model()` in each file before `lifespan`**

```python
def build_model() -> OpenAIModel:
    """Build the OpenAI-compatible model used by Strands."""
    logger.info(f"Routing LLM calls through {LITELLM_BASE_URL} using {MODEL_ID}")
    return OpenAIModel(
        client_args={
            "api_key": LLM_API_KEY,
            "base_url": LITELLM_BASE_URL,
        },
        model_id=MODEL_ID,
        params={
            "max_tokens": 1024,
        },
    )
```

- [ ] **Step 4: Use `build_model()` in each lifespan**

Replace each current block that builds `client_args` and `AnthropicModel` with:

```python
    model = build_model()
```

- [ ] **Step 5: Run the focused tests**

Run:

```bash
cd /home/barsi/projects/media/media-agent && python -m pytest tests/test_model_config.py -v
cd /home/barsi/projects/media/movie-agent && python -m pytest tests/test_model_config.py -v
cd /home/barsi/projects/media/tv-agent && python -m pytest tests/test_model_config.py -v
```

Expected: all provider configuration tests pass.

### Task 3: Update Python Dependencies

**Files:**
- Modify: `media/media-agent/requirements.txt`
- Modify: `media/movie-agent/requirements.txt`
- Modify: `media/tv-agent/requirements.txt`

- [ ] **Step 1: Replace the Strands provider extra in all three requirements files**

Change:

```text
strands-agents[anthropic,otel]
```

To:

```text
strands-agents[openai,otel]
```

- [ ] **Step 2: Verify imports in fresh-ish service environments**

Run:

```bash
cd /home/barsi/projects/media/media-agent && python -m pip install -r requirements.txt pytest
cd /home/barsi/projects/media/media-agent && python -m pytest tests/test_model_config.py -v
cd /home/barsi/projects/media/movie-agent && python -m pip install -r requirements.txt pytest
cd /home/barsi/projects/media/movie-agent && python -m pytest tests/test_model_config.py -v
cd /home/barsi/projects/media/tv-agent && python -m pip install -r requirements.txt pytest
cd /home/barsi/projects/media/tv-agent && python -m pytest tests/test_model_config.py -v
```

Expected: all tests pass and `strands.models.openai` imports successfully.

### Task 4: Configure LiteLLM for OpenRouter Nemotron 3

**Files:**
- Modify: `media/litellm/config.yaml`

- [ ] **Step 1: Add the OpenRouter alias at the top of `model_list`**

```yaml
model_list:
  - model_name: nemotron-3-free
    litellm_params:
      model: openrouter/nvidia/nemotron-3-nano-30b-a3b:free
      api_key: os.environ/OPENROUTER_API_KEY
```

Keep the existing Claude model entries only if a paid fallback is still desired.

- [ ] **Step 2: Validate LiteLLM config syntax**

Run:

```bash
cd /home/barsi/projects/media && docker compose config
```

Expected: Compose renders successfully and includes the `litellm` service.

### Task 5: Update Docker Compose Environment

**Files:**
- Modify: `media/docker-compose.yml`

- [ ] **Step 1: Update all three agent services**

For `media-agent`, `movie-agent`, and `tv-agent`, replace:

```yaml
- ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
- LITELLM_BASE_URL=http://litellm:4000
```

With:

```yaml
- LLM_API_KEY=${LITELLM_API_KEY:-sk-local}
- LITELLM_BASE_URL=http://litellm:4000/v1
- MODEL_ID=${MODEL_ID:-nemotron-3-free}
```

- [ ] **Step 2: Update the LiteLLM service environment**

Replace:

```yaml
- ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
```

With:

```yaml
- OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
```

- [ ] **Step 3: Validate rendered Compose**

Run:

```bash
cd /home/barsi/projects/media && docker compose config
```

Expected: Compose renders successfully, `OPENROUTER_API_KEY` is present only on `litellm`, and all three agents have `MODEL_ID=nemotron-3-free`.

### Task 6: Update User-Facing Configuration Docs

**Files:**
- Modify: `media/env.example`
- Modify: `media/README.md`
- Modify: `media/CLAUDE.md`

- [ ] **Step 1: Update `env.example` LLM section**

Replace the Claude API section with:

```text
# OpenRouter API
# Used by LiteLLM to route agent calls to NVIDIA Nemotron 3 Nano 30B A3B (free)
OPENROUTER_API_KEY=sk-or-v1-xxxxx

# Optional local LiteLLM client key for in-stack agent calls.
# The default docker-compose value is sk-local because this proxy is internal only.
# LITELLM_API_KEY=sk-local

# Default LiteLLM model alias used by all three agents.
MODEL_ID=nemotron-3-free
```

- [ ] **Step 2: Update `README.md` architecture and configuration**

Use:

```markdown
AI-powered media management using Strands Agents + MCP + OpenRouter.

...

                  LiteLLM → OpenRouter → NVIDIA Nemotron 3 Nano 30B A3B (free)

...

- `OPENROUTER_API_KEY` - your OpenRouter API key
- `MODEL_ID` - optional LiteLLM model alias; defaults to `nemotron-3-free`
```

- [ ] **Step 3: Update `CLAUDE.md` project overview and architecture**

Replace references to Claude Haiku/Sonnet as the default with OpenRouter via LiteLLM and `nemotron-3-free`. Keep Claude model entries only as documented fallback entries if they remain in `litellm/config.yaml`.

### Task 7: Build and Smoke Test the Stack

**Files:**
- No source edits.

- [ ] **Step 1: Build the agent images**

Run:

```bash
cd /home/barsi/projects/media && bash build.sh
```

Expected: `media-agent:latest`, `movie-agent:latest`, and `tv-agent:latest` build successfully with the OpenAI provider extra installed.

- [ ] **Step 2: Start the required services**

Run:

```bash
cd /home/barsi/projects/media && docker compose up -d litellm movie-mcp-server tv-mcp-server movie-agent tv-agent media-agent
```

Expected: all services start. If external Radarr/Sonarr/Plex variables are placeholders, MCP calls may fail later, but the agent services should still boot.

- [ ] **Step 3: Check health endpoints**

Run:

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8001/health
curl -s http://localhost:8002/health
```

Expected: each response has `"status":"ok"` and `"agent_ready":true`.

- [ ] **Step 4: Check an LLM routing request**

Run:

```bash
curl -s http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Say exactly: provider check"}'
```

Expected: a JSON response with a `response` field. In LiteLLM logs, the request routes to `openrouter/nvidia/nemotron-3-nano-30b-a3b:free`.

- [ ] **Step 5: Inspect logs for provider errors**

Run:

```bash
cd /home/barsi/projects/media && docker compose logs --tail=100 litellm media-agent movie-agent tv-agent
```

Expected: no authentication errors, no `ModuleNotFoundError: openai`, and no 404s for `/chat/completions`.

### Task 8: Commit

**Files:**
- All files changed in Tasks 1-7.

- [ ] **Step 1: Review the diff**

Run:

```bash
cd /home/barsi/projects/media && git diff
```

Expected: diff only covers provider config, tests, docs, and Compose changes for this OpenRouter migration.

- [ ] **Step 2: Commit**

Run:

```bash
cd /home/barsi/projects/media
git add media-agent movie-agent tv-agent litellm docker-compose.yml env.example README.md CLAUDE.md docs/superpowers/plans/2026-04-25-openrouter-nemotron-3.md
git commit -m "feat: route media agents through OpenRouter"
```

Expected: commit succeeds. Include smoke test output in the PR or deployment note.

## Source Notes

- OpenRouter lists `nvidia/nemotron-3-nano-30b-a3b:free` as the free Nemotron 3 Nano model with 256,000 context and zero-dollar input/output token pricing.
- OpenRouter's OpenAI SDK quickstart uses `baseURL: "https://openrouter.ai/api/v1"` and bearer auth.
- LiteLLM's OpenRouter provider docs use the `openrouter/<openrouter-model-id>` prefix and `OPENROUTER_API_KEY`.
- Strands documents `OpenAIModel` for OpenAI-compatible servers using `client_args={"api_key": ..., "base_url": ...}`.
