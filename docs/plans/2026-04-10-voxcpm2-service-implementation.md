# VoxCPM2 Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a protocol-compliant `voxcpm-service` and register it in the gateway so VoxCPM2 supports synthesize, clone, and design workflows through the unified local TTS stack.

**Architecture:** Implement a new FastAPI service under `services/voxcpm-service` using `local_tts_service_kit.create_service_app`, with a `VoxCPMHandler` that wraps the upstream `models/voxcpm/repo` package. Persist clone and design profiles locally so `/v1/voices` can expose reusable `voice_id`s, then register a thin gateway adapter and provider config that forwards the unified request shape to the service.

**Tech Stack:** Python 3.10+, FastAPI, pytest, pydantic, local TTS protocol/service kit, upstream VoxCPM2 package

---

### Task 1: Add failing service tests for VoxCPM2 protocol behavior

**Files:**
- Create: `services/voxcpm-service/tests/conftest.py`
- Create: `services/voxcpm-service/tests/test_app.py`

**Step 1: Write the failing test**

Add tests covering:
- health and voices endpoints
- clone creates reusable profile
- design creates reusable profile
- synthesize in test mode with direct instruction voice design
- synthesize with cloned voice profile and no explicit reference audio
- synthesize with designed voice profile and no explicit instruction
- non-test startup preload behavior

**Step 2: Run test to verify it fails**

Run: `python -m pytest services/voxcpm-service/tests/test_app.py -v`
Expected: FAIL because `services/voxcpm-service` does not exist yet.

**Step 3: Write minimal implementation**

Create the package skeleton needed for the tests to import `app.main:create_app`.

**Step 4: Run test to verify progress**

Run: `python -m pytest services/voxcpm-service/tests/test_app.py -v`
Expected: remaining FAIL cases point at missing handler behavior.

### Task 2: Implement the VoxCPM2 service handler

**Files:**
- Create: `services/voxcpm-service/app/main.py`
- Create: `services/voxcpm-service/app/handler.py`
- Create: `services/voxcpm-service/pyproject.toml`
- Create: `services/voxcpm-service/README.md`
- Create: `services/voxcpm-service/start.ps1`
- Create: `services/voxcpm-service/healthcheck.ps1`

**Step 1: Write the failing test**

Use the tests from Task 1 as the active red suite.

**Step 2: Run test to verify it fails**

Run: `python -m pytest services/voxcpm-service/tests/test_app.py -v`
Expected: FAIL for missing clone/design/synthesize behavior.

**Step 3: Write minimal implementation**

Implement:
- model discovery via env vars with repo-local defaults
- preload on startup when enabled
- profile stores for clone and design voice ids
- `/v1/health`, `/v1/voices`, `/v1/clone`, `/v1/clone/{task_id}/status`, `/v1/design`, `/v1/synthesize`
- test-mode fake audio responses with debug headers that expose selected reference/instruction paths

**Step 4: Run test to verify it passes**

Run: `python -m pytest services/voxcpm-service/tests/test_app.py -v`
Expected: PASS

### Task 3: Add failing gateway tests for the new provider

**Files:**
- Modify: `local-tts-gateway/tests/test_provider_registry.py`
- Modify: `local-tts-gateway/tests/test_config_loading.py`
- Modify: `local-tts-gateway/tests/test_adapter_mapping.py`

**Step 1: Write the failing test**

Add assertions for:
- `voxcpm-default` present in loaded provider configs
- provider type `voxcpm` present
- registry returns `voxcpm` adapter
- adapter mapping preserves instruction, reference audio/text, and `extra`

**Step 2: Run test to verify it fails**

Run: `python -m pytest local-tts-gateway/tests/test_provider_registry.py local-tts-gateway/tests/test_config_loading.py local-tts-gateway/tests/test_adapter_mapping.py -v`
Expected: FAIL because adapter/config are not registered yet.

**Step 3: Write minimal implementation**

Add the adapter, provider config, and registry mapping.

**Step 4: Run test to verify it passes**

Run: `python -m pytest local-tts-gateway/tests/test_provider_registry.py local-tts-gateway/tests/test_config_loading.py local-tts-gateway/tests/test_adapter_mapping.py -v`
Expected: PASS

### Task 4: Update shared docs for the new service

**Files:**
- Modify: `docs/services/local-tts-service-endpoints.md`

**Step 1: Write the failing test**

No automated doc test. Use the completed implementation as the source of truth.

**Step 2: Write minimal implementation**

Document the new VoxCPM2 base URL, supported endpoints, and note that `/v1/design` is implemented for this service.

**Step 3: Verify**

Manually inspect the doc for consistency with the service behavior.

### Task 5: Run focused verification

**Files:**
- No code changes

**Step 1: Run service tests**

Run: `python -m pytest services/voxcpm-service/tests/test_app.py -v`
Expected: PASS

**Step 2: Run gateway tests**

Run: `python -m pytest local-tts-gateway/tests/test_provider_registry.py local-tts-gateway/tests/test_config_loading.py local-tts-gateway/tests/test_adapter_mapping.py -v`
Expected: PASS

**Step 3: Run shared service-kit safety check**

Run: `python -m pytest local-tts-service-kit/tests/test_app_factory.py -v`
Expected: PASS
