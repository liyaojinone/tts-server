# Hugging Face Token Management Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let a local user authorize Hugging Face gated models from the management page without storing their token in plaintext or altering upstream repositories and cache behavior.

**Architecture:** Add a project-local credential store whose payload is encrypted with Windows DPAPI for the current Windows account.  The API exposes only configuration state and a masked suffix; the raw token is passed explicitly to gateway-owned Hugging Face download calls and injected only into a model process that needs it.  The existing source/mirror switch remains separate from credentials.

**Tech Stack:** FastAPI, pytest/TestClient, Python standard library `ctypes` Windows DPAPI bindings, existing vanilla HTML/JavaScript UI, `huggingface_hub`.

---

### Task 1: Add an encrypted Hugging Face credential store

**Files:**
- Create: `bobogen-gateway/app/services/huggingface_token.py`
- Test: `bobogen-gateway/tests/test_huggingface_token.py`

**Step 1: Write failing tests** for save/read metadata/delete and invalid token input, using an injectable protector so tests do not depend on Windows DPAPI.

**Step 2: Run the focused test** and confirm it fails because the store is absent.

**Step 3: Implement the minimal store.**  On Windows it encrypts one token with `CryptProtectData` and persists only the encrypted bytes at `runtime/secrets/huggingface-token.bin`; it never writes the plaintext token to JSON.  The metadata response contains only `configured` and a final-four-character suffix.

**Step 4: Re-run the focused test** and confirm it passes.

### Task 2: Expose the credential lifecycle through the gateway

**Files:**
- Modify: `bobogen-gateway/app/main.py`
- Modify: `bobogen-gateway/app/routers/management.py`
- Test: `bobogen-gateway/tests/test_management_routes.py`

**Step 1: Write failing route tests** for GET state, PUT token, and DELETE token; assert PUT/GET responses never contain the token.

**Step 2: Run the focused route test** and confirm it fails because the routes are absent.

**Step 3: Implement routes** under `/api/model-credentials/huggingface`, wiring a single store into application state. Convert expected store validation failures into HTTP 400, and do not log tokens.

**Step 4: Re-run the focused route test** and confirm it passes.

### Task 3: Use the token only where Hugging Face needs it

**Files:**
- Modify: `bobogen-gateway/app/services/model_installer.py`
- Modify: `bobogen-gateway/app/services/process_manager.py`
- Modify: `bobogen-gateway/app/main.py`
- Test: `bobogen-gateway/tests/test_model_installer.py`
- Test: `bobogen-gateway/tests/test_process_manager.py` (or the existing process-manager test module)

**Step 1: Write failing tests** showing a stored token becomes the explicit `token=` argument for gateway download calls, and `HF_TOKEN` is added only to a launched Hugging Face model process.

**Step 2: Run the focused tests** and confirm they fail because no credential is wired through.

**Step 3: Implement the minimum integration.**  The installer snapshots the current credential for a job and passes it to `snapshot_download`/`hf_hub_download`; the process manager injects it into model child environments only.  No machine environment variable, provider YAML, source config, job response, or log receives the secret.

**Step 4: Re-run focused tests** and confirm they pass.

### Task 4: Add the front-end gated-model authorization flow

**Files:**
- Modify: `bobogen-gateway/app/web/index.html`
- Test: `bobogen-gateway/tests/test_management_routes.py`

**Step 1: Write a failing page-contract test** for authorization UI copy, endpoint references, and the official terms link.

**Step 2: Run the test** and confirm it fails.

**Step 3: Implement the modal/inline credential card.**  It opens the model’s official Hugging Face page for terms, accepts a read/fine-grained read token, saves it to the new API, only displays configured state/masked suffix, and allows replace/delete.  A gated model’s download button opens this flow before starting a download if no token is configured.

**Step 4: Re-run focused UI-contract tests** and confirm they pass.

### Task 5: Verify the scoped change

**Files:**
- Verify: `bobogen-gateway/tests/test_huggingface_token.py`
- Verify: `bobogen-gateway/tests/test_management_routes.py`
- Verify: `bobogen-gateway/tests/test_model_installer.py`
- Verify: process-manager focused tests

**Step 1:** Run the focused gateway test set.

**Step 2:** Run `python -m compileall app` from `bobogen-gateway`.

**Step 3:** Inspect `git diff --check` and the final diff.  Do not commit because the user has not requested a commit.
