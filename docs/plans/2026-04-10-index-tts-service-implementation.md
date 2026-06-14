# IndexTTS Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an `index-tts` protocol service plus gateway provider config that can launch the locally verified IndexTTS2 model from `models/index-tts`.

**Architecture:** Reuse the existing `bobogen_service_kit` service wrapper pattern. Add a new `services/index-tts-service` package that loads `models/index-tts/repo` and `models/index-tts/checkpoints`, supports protocol `health`, `voices`, `clone`, and `synthesize`, then expose it through a new gateway adapter and provider YAML.

**Tech Stack:** Python, FastAPI, pytest, local TTS protocol/service kit, IndexTTS2

---

### Task 1: Add failing service tests

**Files:**
- Create: `services/index-tts-service/tests/test_app.py`
- Create: `services/index-tts-service/tests/conftest.py`

**Step 1: Write the failing tests**

Cover:
- protocol health and voices routes exist
- clone creates reusable voice profile
- synthesize succeeds in `test_mode`
- synthesize can reuse cloned profile when request omits reference fields

**Step 2: Run test to verify it fails**

Run: `python -m pytest services/index-tts-service/tests/test_app.py -v`
Expected: FAIL because `services/index-tts-service` does not exist yet

### Task 2: Implement the new protocol service

**Files:**
- Create: `services/index-tts-service/app/main.py`
- Create: `services/index-tts-service/app/handler.py`
- Create: `services/index-tts-service/app/__init__.py`
- Create: `services/index-tts-service/pyproject.toml`

**Step 1: Write minimal implementation**

Implement:
- environment-driven paths for repo/checkpoints/profiles/outputs
- lazy `IndexTTS2` loading
- `clone` backed by `ProfileStore`
- default voice metadata and cloned voices
- synthesize using request or cloned reference audio/text

**Step 2: Run targeted tests**

Run: `python -m pytest services/index-tts-service/tests/test_app.py -v`
Expected: PASS

### Task 3: Expose IndexTTS through gateway config

**Files:**
- Create: `bobogen-gateway/app/adapters/indextts.py`
- Modify: `bobogen-gateway/app/services/provider_registry.py`
- Create: `bobogen-gateway/configs/providers/indextts-default.yaml`

**Step 1: Add adapter and provider mapping**

Map unified synthesize requests to the protocol service `/v1/synthesize` request shape and register provider type `indextts`.

**Step 2: Verify gateway config loads**

Run: `python -m pytest bobogen-gateway/tests/test_config_loading.py -v`
Expected: PASS with the new provider file present

### Task 4: Verify end-to-end pieces

**Files:**
- Reuse files above

**Step 1: Run focused tests**

Run:
- `python -m pytest services/index-tts-service/tests/test_app.py -v`
- `python -m pytest bobogen-gateway/tests -v`

**Step 2: Smoke-check service startup**

Run the service with the verified local model paths and confirm `/v1/health` responds.
