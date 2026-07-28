"""Tests for the Capability Registry."""

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from app.capability_registry import (
    CAPABILITY_FIELDS,
    REGISTRY_PATH,
    CapabilityRegistry,
    ModelCapability,
    capability_registry,
)
from app.routing import (
    RoutingContext,
    RoutingEngine,
    get_model_context_window,
)


# ---- Fixtures ----


@pytest.fixture
def sample_yaml():
    return {
        "models": [
            {
                "provider": "test_provider",
                "model": "test-model-vision",
                "context_window": 128000,
                "supports_streaming": True,
                "supports_tools": True,
                "supports_vision": True,
                "supports_json_mode": True,
                "supports_embeddings": False,
                "supports_reasoning": False,
                "supports_thinking": False,
                "supports_image_generation": False,
                "supports_function_calling": True,
            },
            {
                "provider": "test_provider",
                "model": "test-model-basic",
                "context_window": 8192,
                "supports_streaming": True,
                "supports_tools": False,
                "supports_vision": False,
                "supports_json_mode": True,
                "supports_embeddings": False,
                "supports_reasoning": False,
                "supports_thinking": False,
                "supports_image_generation": False,
                "supports_function_calling": False,
            },
            {
                "provider": "test_provider",
                "model": "test-embed-model",
                "context_window": 2048,
                "supports_streaming": False,
                "supports_tools": False,
                "supports_vision": False,
                "supports_json_mode": False,
                "supports_embeddings": True,
                "supports_reasoning": False,
                "supports_thinking": False,
                "supports_image_generation": False,
                "supports_function_calling": False,
            },
            {
                "provider": "other_provider",
                "model": "other-model",
                "context_window": 65536,
                "supports_streaming": True,
                "supports_tools": True,
                "supports_vision": False,
                "supports_json_mode": False,
                "supports_embeddings": False,
                "supports_reasoning": False,
                "supports_thinking": False,
                "supports_image_generation": False,
                "supports_function_calling": True,
            },
        ]
    }


@pytest.fixture
def temp_registry(sample_yaml):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(sample_yaml, f)
        tmp_path = f.name
    reg = CapabilityRegistry(tmp_path)
    yield reg
    os.unlink(tmp_path)


@pytest.fixture
def empty_registry():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({"models": []}, f)
        tmp_path = f.name
    reg = CapabilityRegistry(tmp_path)
    yield reg
    os.unlink(tmp_path)


# ---- ModelCapability Tests ----


class TestModelCapability:
    def test_has_existing(self):
        mc = ModelCapability(provider="p", model="m", supports_vision=True)
        assert mc.has("vision") is True
        assert mc.has("streaming") is False

    def test_has_missing_attr(self):
        mc = ModelCapability(provider="p", model="m")
        assert mc.has("nonexistent") is False

    def test_to_dict(self):
        mc = ModelCapability(provider="p", model="m", context_window=1000, supports_streaming=True)
        d = mc.to_dict()
        assert d["provider"] == "p"
        assert d["model"] == "m"
        assert d["context_window"] == 1000
        assert d["supports_streaming"] is True
        assert d["supports_vision"] is False


# ---- CapabilityRegistry Tests ----


class TestCapabilityRegistry:
    def test_loads_from_file(self, temp_registry, sample_yaml):
        assert len(temp_registry) == len(sample_yaml["models"])

    def test_get_existing(self, temp_registry):
        cap = temp_registry.get("test_provider", "test-model-vision")
        assert cap is not None
        assert cap.model == "test-model-vision"
        assert cap.supports_vision is True

    def test_get_nonexistent(self, temp_registry):
        cap = temp_registry.get("nonexistent", "nonexistent")
        assert cap is None

    def test_get_with_prefix(self, temp_registry):
        cap = temp_registry.get("test_provider", "openai/test-model-vision")
        assert cap is not None
        assert cap.model == "test-model-vision"

    def test_get_by_model(self, temp_registry):
        cap = temp_registry.get_by_model("test-model-basic")
        assert cap is not None
        assert cap.provider == "test_provider"

    def test_get_by_model_with_prefix(self, temp_registry):
        cap = temp_registry.get_by_model("openai/test-model-basic")
        assert cap is not None
        assert cap.provider == "test_provider"

    def test_get_by_model_nonexistent(self, temp_registry):
        cap = temp_registry.get_by_model("nonexistent")
        assert cap is None

    def test_has_capability_true(self, temp_registry):
        assert temp_registry.has_capability("test_provider", "test-model-vision", "vision") is True

    def test_has_capability_false(self, temp_registry):
        assert temp_registry.has_capability("test_provider", "test-model-basic", "vision") is False

    def test_has_capability_unknown_model(self, temp_registry):
        assert temp_registry.has_capability("unknown", "unknown", "vision") is True

    def test_get_context_window(self, temp_registry):
        ctx = temp_registry.get_context_window("test_provider", "test-model-vision")
        assert ctx == 128000

    def test_get_context_window_unknown(self, temp_registry):
        ctx = temp_registry.get_context_window("unknown", "unknown")
        assert ctx is None

    def test_get_all_models(self, temp_registry, sample_yaml):
        all_models = temp_registry.get_all_models()
        assert len(all_models) == len(sample_yaml["models"])

    def test_get_providers(self, temp_registry):
        providers = temp_registry.get_providers()
        assert "test_provider" in providers
        assert "other_provider" in providers

    def test_get_models_by_provider(self, temp_registry):
        models = temp_registry.get_models_by_provider("test_provider")
        assert len(models) == 3

    def test_empty_registry(self, empty_registry):
        assert len(empty_registry) == 0
        assert empty_registry.get_all_models() == []
        assert empty_registry.get_providers() == []


# ---- Filter Tests ----


class TestFilterCandidates:
    def test_no_required_capabilities(self, temp_registry):
        candidates = [("test_provider", "test-model-basic"), ("test_provider", "test-model-vision")]
        result = temp_registry.filter_candidates(candidates, set())
        assert result == candidates

    def test_filter_vision(self, temp_registry):
        candidates = [("test_provider", "test-model-basic"), ("test_provider", "test-model-vision")]
        result = temp_registry.filter_candidates(candidates, {"vision"})
        assert len(result) == 1
        assert result[0] == ("test_provider", "test-model-vision")

    def test_filter_streaming(self, temp_registry):
        candidates = [("test_provider", "test-embed-model"), ("test_provider", "test-model-basic")]
        result = temp_registry.filter_candidates(candidates, {"streaming"})
        assert len(result) == 1
        assert result[0] == ("test_provider", "test-model-basic")

    def test_filter_multiple_caps(self, temp_registry):
        candidates = [
            ("test_provider", "test-model-basic"),
            ("test_provider", "test-model-vision"),
        ]
        result = temp_registry.filter_candidates(candidates, {"streaming", "tools"})
        assert len(result) == 1
        assert result[0] == ("test_provider", "test-model-vision")

    def test_filter_all_excluded(self, temp_registry):
        candidates = [("test_provider", "test-embed-model")]
        result = temp_registry.filter_candidates(candidates, {"streaming"})
        assert result == []

    def test_filter_with_prefix_model(self, temp_registry):
        candidates = [("test_provider", "openai/test-model-basic"), ("test_provider", "openai/test-model-vision")]
        result = temp_registry.filter_candidates(candidates, {"vision"})
        assert len(result) == 1
        assert result[0] == ("test_provider", "openai/test-model-vision")


# ---- Global Instance ----


class TestGlobalInstance:
    def test_capability_registry_global(self):
        assert capability_registry is not None
        assert isinstance(capability_registry, CapabilityRegistry)

    def test_registry_path_exists(self):
        assert REGISTRY_PATH.exists()
        assert len(capability_registry) > 0


# ---- Routing Integration Tests ----


class TestGetModelContextWindow:
    def test_known_model(self):
        ctx = get_model_context_window("gpt-4o")
        assert ctx == 128000

    def test_known_model_with_prefix(self):
        ctx = get_model_context_window("openai/gpt-4o")
        assert ctx == 128000

    def test_known_model_with_provider(self):
        ctx = get_model_context_window("gpt-4o", provider="openai")
        assert ctx == 128000

    def test_unknown_model(self):
        ctx = get_model_context_window("fictional-model-v99")
        assert ctx is None


class TestRoutingContextCapabilities:
    def test_default_empty(self):
        ctx = RoutingContext()
        assert ctx.required_capabilities == set()

    def test_set_capabilities(self):
        ctx = RoutingContext(required_capabilities={"vision", "tools"})
        assert ctx.required_capabilities == {"vision", "tools"}


class TestScoreProviderCapabilityPenalty:
    def test_vision_capability_penalty(self):
        from app.models import HealthCheckResponse, ProviderStatus
        from app.routing import ProviderReputation

        engine = RoutingEngine()
        ctx = RoutingContext(required_capabilities={"vision"})
        rep = ProviderReputation()
        health = HealthCheckResponse(status=ProviderStatus.HEALTHY, provider="openai")

        score_vision = engine.score_provider("openai", "gpt-4o", rep, health, 0, ctx)
        score_no_vision = engine.score_provider("openai", "gpt-3.5-turbo", rep, health, 0, ctx)
        assert score_vision > score_no_vision

    def test_no_penalty_without_required(self):
        from app.models import HealthCheckResponse, ProviderStatus
        from app.routing import ProviderReputation

        engine = RoutingEngine()
        ctx = RoutingContext()
        rep = ProviderReputation()
        health = HealthCheckResponse(status=ProviderStatus.HEALTHY, provider="openai")

        score_vision = engine.score_provider("openai", "gpt-4o", rep, health, 0, ctx)
        score_no_vision = engine.score_provider("openai", "gpt-3.5-turbo", rep, health, 0, ctx)
        assert score_no_vision >= score_vision - 10.0  # similar scores without capability req


# ---- Hot Reload Tests ----


class TestHotReload:
    def test_reload(self, sample_yaml):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(sample_yaml, f)
            tmp_path = f.name

        reg = CapabilityRegistry(tmp_path)
        assert len(reg) == 4

        # Modify file
        data = dict(sample_yaml)
        data["models"] = data["models"][:1]
        with open(tmp_path, "w") as f:
            yaml.dump(data, f)

        assert reg.reload() is True
        assert len(reg) == 1

        os.unlink(tmp_path)

    def test_reload_on_missing_file(self):
        reg = CapabilityRegistry("/tmp/nonexistent_file_xyz.yaml")
        assert reg.reload() is True
        assert len(reg) == 0

    def test_watcher_enable_disable(self, sample_yaml):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(sample_yaml, f)
            tmp_path = f.name

        reg = CapabilityRegistry(tmp_path)
        reg.enable_watcher()
        assert reg._watch_active is True
        reg.disable_watcher()
        assert reg._watch_active is False

        os.unlink(tmp_path)


# ---- API Tests ----


class TestCapabilityAPI:
    def test_list_capabilities(self):
        from app.api import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/capabilities")
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert "total_models" in data
        assert "providers" in data
        assert data["total_models"] > 0

    def test_provider_capabilities(self):
        from app.api import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/capabilities/openai")
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "openai"
        assert len(data["models"]) > 0

    def test_nonexistent_provider_capabilities(self):
        from app.api import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/capabilities/nonexistent_provider_xyz")
        assert response.status_code == 404

    def test_model_capability(self):
        from app.api import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/capabilities/openai/gpt-4o")
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "openai"
        assert data["model"] == "gpt-4o"
        assert data["supports_vision"] is True
        assert data["context_window"] == 128000

    def test_nonexistent_model_capability(self):
        from app.api import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/capabilities/openai/nonexistent_v99")
        assert response.status_code == 404


# ---- Router Integration Tests ----


class TestRouterCapabilityDetection:
    def test_detect_vision(self):
        from app.models import ChatRequest, Message, MessageRole
        from app.router import _detect_required_capabilities

        req = ChatRequest(
            model="test",
            messages=[Message(role=MessageRole.USER, content="What is in this image? data:image/png;base64,abc123")],
        )
        caps = _detect_required_capabilities(req)
        assert "vision" in caps

    def test_detect_tools(self):
        from app.models import ChatRequest, Message, MessageRole
        from app.router import _detect_required_capabilities

        req = ChatRequest(
            model="test",
            messages=[
                Message(role=MessageRole.ASSISTANT, content="", tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}}]),
            ],
        )
        caps = _detect_required_capabilities(req)
        assert "tools" in caps
        assert "function_calling" in caps

    def test_detect_streaming(self):
        from app.models import ChatRequest, Message, MessageRole
        from app.router import _detect_required_capabilities

        req = ChatRequest(
            model="test",
            messages=[Message(role=MessageRole.USER, content="hello")],
            stream=True,
        )
        caps = _detect_required_capabilities(req)
        assert "streaming" in caps

    def test_no_detection_for_plain(self):
        from app.models import ChatRequest, Message, MessageRole
        from app.router import _detect_required_capabilities

        req = ChatRequest(
            model="test",
            messages=[Message(role=MessageRole.USER, content="hello")],
            stream=False,
        )
        caps = _detect_required_capabilities(req)
        assert caps == set()

    def test_metadata_overrides(self):
        from app.models import ChatRequest, Message, MessageRole

        req = ChatRequest(
            model="test",
            messages=[Message(role=MessageRole.USER, content="hello")],
            metadata={"required_capabilities": ["vision"]},
        )
        required_caps = set()
        if req.metadata:
            required_caps.update(req.metadata.get("required_capabilities", []))
        assert "vision" in required_caps


class TestRegistryInRouter:
    def test_capability_registry_imported_in_router(self):
        from app.router import AIRouter
        router = AIRouter()
        assert router is not None

    def test_capability_detection_in_chat_flow(self):
        from app.models import ChatRequest, Message, MessageRole
        from app.router import _detect_required_capabilities

        req = ChatRequest(
            model="test",
            messages=[Message(role=MessageRole.USER, content="Describe this image: data:image/jpeg;base64,/9j/4AAQ")],
        )
        caps = _detect_required_capabilities(req)
        assert "vision" in caps


# ---- Edge Cases ----


class TestEdgeCases:
    def test_empty_yaml_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            tmp_path = f.name
        reg = CapabilityRegistry(tmp_path)
        assert len(reg) == 0
        os.unlink(tmp_path)

    def test_yaml_without_models_key(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"not_models": []}, f)
            tmp_path = f.name
        reg = CapabilityRegistry(tmp_path)
        assert len(reg) == 0
        os.unlink(tmp_path)

    def test_missing_provider_or_model_in_entry(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({
                "models": [
                    {"provider": "", "model": "m", "context_window": 100},
                    {"provider": "p", "model": "", "context_window": 100},
                ]
            }, f)
            tmp_path = f.name
        reg = CapabilityRegistry(tmp_path)
        assert len(reg) == 0
        os.unlink(tmp_path)

    def test_global_registry_has_real_data(self):
        assert len(capability_registry) > 0
        gpt4 = capability_registry.get("openai", "gpt-4o")
        assert gpt4 is not None
        assert gpt4.supports_vision is True
        assert gpt4.supports_streaming is True
