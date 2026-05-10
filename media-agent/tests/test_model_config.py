import importlib


def test_default_model_config(monkeypatch):
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_ID", raising=False)

    agent = importlib.reload(importlib.import_module("agent"))

    model = agent.build_model()
    config = model.get_config()

    assert config["model_id"] == "nemotron-3-free"
    assert config["params"]["max_tokens"] == 4096
    assert config["params"]["extra_body"]["reasoning"] == {"effort": "none", "exclude": True}


def test_model_config_honors_environment(monkeypatch):
    monkeypatch.setenv("LITELLM_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-or-test")
    monkeypatch.setenv("MODEL_ID", "nvidia/nemotron-3-nano-30b-a3b:free")

    agent = importlib.reload(importlib.import_module("agent"))

    model = agent.build_model()
    config = model.get_config()

    assert config["model_id"] == "nvidia/nemotron-3-nano-30b-a3b:free"
    assert config["params"]["max_tokens"] == 4096
    assert config["params"]["extra_body"]["reasoning"] == {"effort": "none", "exclude": True}


def test_build_agent_returns_isolated_message_state(monkeypatch):
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_ID", raising=False)

    agent_module = importlib.reload(importlib.import_module("agent"))

    first_agent = agent_module.build_agent()
    first_agent.messages.append({"role": "user", "content": "sticky instruction"})

    second_agent = agent_module.build_agent()

    assert second_agent.messages == []
