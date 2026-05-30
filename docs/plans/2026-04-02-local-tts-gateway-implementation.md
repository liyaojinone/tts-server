# Local TTS Gateway Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a first usable `local-tts-gateway` service that exposes a unified HTTP API for `CosyVoice`, `F5-TTS`, and `GPT-SoVITS`, with config-driven provider registration and lazy process startup.

**Architecture:** The gateway runs as an independent FastAPI app. It loads provider definitions from YAML, starts model services on demand through a process manager, translates the unified request into provider-native HTTP requests through adapters, and returns normalized audio/error responses.

**Tech Stack:** Python 3.10, FastAPI, Pydantic, PyYAML, httpx, pytest, uvicorn

---

### Task 1: Scaffold gateway project and configuration loader

**Files:**
- Create: `local-tts-gateway/pyproject.toml`
- Create: `local-tts-gateway/app/__init__.py`
- Create: `local-tts-gateway/app/main.py`
- Create: `local-tts-gateway/app/config.py`
- Create: `local-tts-gateway/app/schemas/provider.py`
- Create: `local-tts-gateway/configs/gateway.yaml`
- Create: `local-tts-gateway/configs/providers/cosyvoice-default.yaml`
- Create: `local-tts-gateway/configs/providers/f5tts-default.yaml`
- Create: `local-tts-gateway/configs/providers/gptsovits-default.yaml`
- Test: `local-tts-gateway/tests/test_config_loading.py`

**Step 1: Write the failing test**

Write a test that loads the provider directory and asserts the three providers are parsed with expected ids and provider types.

**Step 2: Run test to verify it fails**

Run: `pytest local-tts-gateway/tests/test_config_loading.py -v`
Expected: FAIL because config loader does not exist yet.

**Step 3: Write minimal implementation**

Implement provider config schemas and YAML loading helpers.

**Step 4: Run test to verify it passes**

Run: `pytest local-tts-gateway/tests/test_config_loading.py -v`
Expected: PASS

### Task 2: Add process manager state model and lazy-start flow

**Files:**
- Create: `local-tts-gateway/app/core/state.py`
- Create: `local-tts-gateway/app/core/exceptions.py`
- Create: `local-tts-gateway/app/services/process_manager.py`
- Test: `local-tts-gateway/tests/test_process_manager.py`

**Step 1: Write the failing test**

Write tests for:
- returning existing healthy state without restart
- refusing unknown provider
- starting a stopped provider through an injected process launcher

**Step 2: Run test to verify it fails**

Run: `pytest local-tts-gateway/tests/test_process_manager.py -v`
Expected: FAIL because process manager does not exist yet.

**Step 3: Write minimal implementation**

Implement in-memory runtime state, provider locks, and a basic `ensure_started`.

**Step 4: Run test to verify it passes**

Run: `pytest local-tts-gateway/tests/test_process_manager.py -v`
Expected: PASS

### Task 3: Add provider registry and adapter resolution

**Files:**
- Create: `local-tts-gateway/app/adapters/base.py`
- Create: `local-tts-gateway/app/adapters/cosyvoice.py`
- Create: `local-tts-gateway/app/adapters/f5tts.py`
- Create: `local-tts-gateway/app/adapters/gptsovits.py`
- Create: `local-tts-gateway/app/services/provider_registry.py`
- Test: `local-tts-gateway/tests/test_provider_registry.py`

**Step 1: Write the failing test**

Write a test that asserts the registry returns the correct adapter class for each provider type.

**Step 2: Run test to verify it fails**

Run: `pytest local-tts-gateway/tests/test_provider_registry.py -v`
Expected: FAIL because registry and adapters do not exist yet.

**Step 3: Write minimal implementation**

Implement static adapter mapping and provider lookup.

**Step 4: Run test to verify it passes**

Run: `pytest local-tts-gateway/tests/test_provider_registry.py -v`
Expected: PASS

### Task 4: Add unified synthesize schemas and adapter request mapping

**Files:**
- Create: `local-tts-gateway/app/schemas/synthesize.py`
- Create: `local-tts-gateway/app/schemas/voice.py`
- Create: `local-tts-gateway/app/schemas/error.py`
- Modify: `local-tts-gateway/app/adapters/cosyvoice.py`
- Modify: `local-tts-gateway/app/adapters/f5tts.py`
- Modify: `local-tts-gateway/app/adapters/gptsovits.py`
- Test: `local-tts-gateway/tests/test_adapter_mapping.py`

**Step 1: Write the failing test**

Write tests that verify each adapter maps a unified synthesize request into the correct provider-native path, payload, and content type.

**Step 2: Run test to verify it fails**

Run: `pytest local-tts-gateway/tests/test_adapter_mapping.py -v`
Expected: FAIL because mapping logic does not exist yet.

**Step 3: Write minimal implementation**

Implement provider-native mapping for:
- `CosyVoice -> /v1/audio/speech`
- `F5-TTS -> /tts`
- `GPT-SoVITS -> /tts`

**Step 4: Run test to verify it passes**

Run: `pytest local-tts-gateway/tests/test_adapter_mapping.py -v`
Expected: PASS

### Task 5: Add FastAPI routes for health, providers, voices, and synthesize

**Files:**
- Create: `local-tts-gateway/app/dependencies.py`
- Create: `local-tts-gateway/app/routers/health.py`
- Create: `local-tts-gateway/app/routers/providers.py`
- Create: `local-tts-gateway/app/routers/synthesize.py`
- Create: `local-tts-gateway/app/routers/internal.py`
- Modify: `local-tts-gateway/app/main.py`
- Test: `local-tts-gateway/tests/test_api_routes.py`

**Step 1: Write the failing test**

Write route tests for:
- `GET /v1/health`
- `GET /v1/providers`
- `GET /v1/providers/{provider_id}/health`
- `GET /internal/providers/status`

Use stub services instead of real model processes.

**Step 2: Run test to verify it fails**

Run: `pytest local-tts-gateway/tests/test_api_routes.py -v`
Expected: FAIL because routes do not exist yet.

**Step 3: Write minimal implementation**

Implement the routes and dependency wiring.

**Step 4: Run test to verify it passes**

Run: `pytest local-tts-gateway/tests/test_api_routes.py -v`
Expected: PASS

### Task 6: Add synthesize endpoint end-to-end with mocked adapter I/O

**Files:**
- Create: `local-tts-gateway/app/services/audio_service.py`
- Modify: `local-tts-gateway/app/routers/synthesize.py`
- Test: `local-tts-gateway/tests/test_synthesize_endpoint.py`

**Step 1: Write the failing test**

Write a test that posts a unified synthesize request and asserts:
- the process manager is asked to ensure startup
- the correct adapter is called
- the response media type and headers are normalized

**Step 2: Run test to verify it fails**

Run: `pytest local-tts-gateway/tests/test_synthesize_endpoint.py -v`
Expected: FAIL because synthesize orchestration does not exist yet.

**Step 3: Write minimal implementation**

Implement the endpoint orchestration and audio response wrapping.

**Step 4: Run test to verify it passes**

Run: `pytest local-tts-gateway/tests/test_synthesize_endpoint.py -v`
Expected: PASS

### Task 7: Run focused verification and document startup usage

**Files:**
- Modify: `local-tts-gateway/README.md`

**Step 1: Run test suite**

Run: `pytest local-tts-gateway/tests -v`
Expected: PASS

**Step 2: Add usage docs**

Document:
- how to install dependencies
- how to run the gateway
- where provider configs live
- which underlying model endpoints are currently expected

**Step 3: Re-run tests**

Run: `pytest local-tts-gateway/tests -v`
Expected: PASS
