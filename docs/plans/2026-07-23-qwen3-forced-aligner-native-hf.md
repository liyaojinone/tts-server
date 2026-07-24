# Qwen3 Forced Aligner Native HF Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for each behavior change.

**Goal:** 将 Forced Aligner 迁移到官方 token-classification 推理路径，同时保持现有 BoboGen API 不变。

**Architecture:** ASR 和 Forced Aligner 共用服务代码但使用独立 Python 环境。模型 ID 决定加载旧 ASR
backend 或官方原生 Forced Aligner backend；Forced Aligner 不提供旧实现 fallback。

**Tech Stack:** Python, FastAPI, PyTorch, Hugging Face Transformers, pytest, YAML

---

### Task 1: 原生 Forced Aligner 行为测试

**Files:**
- Modify: `services/qwen3-asr-service/tests/test_app.py`
- Modify: `services/qwen3-asr-service/app/handler.py`

1. 添加失败测试，要求 Forced Aligner 使用 `AutoProcessor` 和
   `AutoModelForTokenClassification`，并调用官方 prepare/decode API。
2. 运行目标 pytest，确认测试因旧 loader 失败。
3. 实现最小原生 loader 和 align 调用。
4. 运行目标 pytest，确认通过。

### Task 2: 加载与推理互斥及健康状态

**Files:**
- Modify: `services/qwen3-asr-service/tests/test_app.py`
- Modify: `services/qwen3-asr-service/app/handler.py`

1. 添加失败测试，覆盖 aligner ready 状态和并发调用串行化。
2. 运行目标 pytest，确认失败。
3. 使用现有推理锁保护加载与推理，修正 health。
4. 重跑目标测试。

### Task 3: 独立运行环境和 provider 配置

**Files:**
- Modify: `services/qwen3-asr-service/pyproject.toml`
- Modify: `services/qwen3-asr-service/start.ps1`
- Modify: `services/qwen3-asr-service/start.sh`
- Modify: `bobogen-gateway/configs/providers/qwen3-forced-aligner-0_6b-windows.yaml`
- Modify: `bobogen-gateway/tests/test_config_loading.py`

1. 添加失败配置测试，要求 `-hf` checkpoint、独立目录和独立 Python。
2. 运行测试确认失败。
3. 添加 aligner 可选依赖及启动环境选择，更新 provider 配置。
4. 重跑配置测试。

### Task 4: 文档与局部验证

**Files:**
- Modify: `services/qwen3-asr-service/README.md`
- Modify: `docs/services/bobogen-api-reference.md`

1. 更新安装和运行说明。
2. 运行 qwen3 服务测试、gateway 配置测试和 `git diff --check`。
3. 安装独立环境并下载官方 checkpoint。
4. 停止旧 5112 服务，运行短音频和 150 秒真实 smoke test。
