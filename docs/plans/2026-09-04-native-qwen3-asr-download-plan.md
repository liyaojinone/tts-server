# Native Qwen3-ASR 0.6B Download Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement the plan task-by-task.

## 执行总标准（最高优先级）

本标准适用于本计划的 Qwen3-ASR 0.6B 样本，也适用于后续接入的所有模型。下方任何任务、代码和界面行为都不得与本标准冲突。

1. **只安装用户选中的模型。** 一键安装的作用域是当前选中的单个模型，不批量安装全部模型。
2. **平台只负责官方仓库和官方环境。** 安装阶段只下载该模型的官方 GitHub 仓库代码，按官方文档准备 Python 环境、CUDA/PyTorch 和其他官方依赖，并记录日志和状态。
3. **权重完全由官方运行时负责。** 安装阶段不下载、复制、搬运、重命名、校验或指定权重文件路径。正式启动后，由官方仓库/官方 SDK 按原生机制自动下载、缓存、定位和加载权重。
4. **不改上游代码，不做路径映射。** 不修改官方仓库源码，不把官方相对路径改写成平台路径，不建立平台自己的模型权重目录，也不把权重迁移到另一个目录。
5. **保持官方可 DIY 的底子。** 服务使用官方仓库代码和与官方一致的依赖环境，使用户可以在这个仓库上继续调试、训练或做其他 DIY；平台适配层不得改变官方安装、下载和加载逻辑。
6. **代码更新与权重管理分离。** 更新按钮只更新官方仓库代码并按官方要求同步依赖，不删除、移动或覆盖已有权重和用户在仓库中的改动；清理或重置必须是另行确认的操作。
7. **下载源可以配置，但只作为官方工具的输入。** Hugging Face、ModelScope 以及用户配置的镜像地址通过官方客户端支持的环境变量或参数传入，且只对当前进程生效；镜像配置不得变成新的权重路径或平台下载逻辑。
8. **状态如实区分两个阶段。** 安装完成只表示“官方仓库和官方环境已就绪”，不宣称权重已就绪；权重是否可用要在正式启动、由官方代码完成其原生下载/加载后再判断。

---

**Goal:** Make one-click installation for the selected Qwen3-ASR 0.6B model download its official repository and prepare its official-compatible environment, while leaving runtime weight download, cache, path resolution, and loading entirely to the upstream code.

**Architecture:** The Gateway is an orchestrator for the selected model only: it checks out the official GitHub repository, prepares the repository's Python environment, runs the repository's documented dependency commands, and reports logs and stage status. At runtime, the unchanged upstream code receives its official model ID/configuration and owns all weight download and cache decisions; the platform does not set a model directory or translate paths. Repository updates are a separate operation from runtime weight handling.

**Tech Stack:** Python 3.10+, FastAPI, pytest, PowerShell, Bash, Qwen `qwen-asr`, Hugging Face / ModelScope official clients.

---

### Task 1: Define the selected-model official installation contract

**Files:**
- Modify: `bobogen-gateway/app/services/model_installer.py`
- Modify: `bobogen-gateway/app/routers/management.py`
- Modify: `bobogen-gateway/configs/providers/qwen3-asr-0_6b-windows.yaml`
- Review: `services/qwen3-asr-service/README.md`

**Steps:**
1. Represent the selected model with its official Git repository URL, pinned revision policy, official setup command, environment requirements, and runtime entrypoint metadata.
2. Make the install job execute only the selected model's official repository checkout and documented environment/dependency commands; do not include a weight-download resource in this job.
3. Keep the repository working directory and Python executable explicit for the service process, while leaving the model identifier and upstream path behavior unchanged.
4. Pass an optional user-selected Hugging Face/ModelScope mirror only as a process-scoped value understood by the official client; never turn it into a platform cache or model path.
5. Preserve explicit development overrides only when they are forwarded unchanged to the official command or runtime; do not normalize them into a platform-owned directory.

### Task 2: Keep runtime loading native to the upstream repository

**Files:**
- Modify: `services/qwen3-asr-service/app/handler.py`
- Modify: `services/qwen3-asr-service/start.ps1`
- Modify: `services/qwen3-asr-service/start.sh`
- Modify: `bobogen-gateway/configs/providers/qwen3-asr-0_6b-windows.yaml`

**Steps:**
1. Default the service to the official Qwen model ID (for example, `Qwen/Qwen3-ASR-0.6B`) instead of a platform-created local model directory.
2. Remove default `QWEN3_ASR_MODEL_DIR`, `HF_HOME`, `HUGGINGFACE_HUB_CACHE`, `TORCH_HOME`, or equivalent path rewriting from the platform start scripts; only an explicit developer override may be forwarded unchanged.
3. Start from the official repository root when the upstream runtime requires that working directory, without editing the upstream files or changing their relative-path semantics.
4. Keep mirror selection process-scoped and let the official Qwen/Hugging Face/ModelScope client decide download, retry, cache, and loading behavior at runtime.
5. Do not add platform cleanup, weight download, retry, copy, or fallback behavior in this phase.

### Task 3: Report installation and runtime status separately

**Files:**
- Modify: `bobogen-gateway/app/routers/management.py`
- Modify: the model-management web UI under `bobogen-gateway/app/web/`

**Steps:**
1. Make the selected-model install button report the stages “下载官方仓库 → 准备 Python 环境 → 安装官方依赖 → 安装完成”.
2. Remove checks that require a platform-specific or repository-relative weight directory to exist before installation can be marked complete.
3. Add a separate runtime state for “官方代码启动后正在下载/加载权重”; installation success must not imply weight readiness.
4. Show the configured source endpoint and the exact official repository/revision used, while making clear that weight paths remain controlled by the upstream runtime.

### Task 4: Add focused regression tests

**Files:**
- Modify: `services/qwen3-asr-service/tests/test_app.py`
- Modify: `bobogen-gateway/tests/test_management_routes.py`
- Modify: `bobogen-gateway/tests/test_entrypoint_scripts.py`
- Modify: `bobogen-gateway/tests/test_model_installer.py`

**Steps:**
1. Test that an install request operates on only the selected model and invokes the official checkout/setup steps.
2. Test that no Qwen weight-download resource or platform model-directory environment variable is added to the install job by default.
3. Test that the runtime receives the official model ID and that an explicit developer override is forwarded unchanged.
4. Test that status distinguishes repository/environment readiness from runtime weight readiness.
5. Test that mirror settings are process-scoped and do not mutate persistent user environment or cache paths.
6. Run the focused service and Gateway tests, then `git diff --check`.

### Task 5: Review before any destructive or network action

**Steps:**
1. Inspect the final diff for accidental path rewriting, upstream-source edits, or unrelated changes.
2. Report the exact existing Qwen resources separately; do not delete or migrate them in this implementation pass.
3. Only after explicit confirmation, clean the selected Qwen3-ASR 0.6B resources if requested and then launch the official runtime so that it—not the installer—performs the first weight download.

---

## 通用模型检验规范对齐（Agent 必读）

本计划落地并严格遵循平台通用规范：[docs/MODEL_VERIFICATION_SOP.md](../MODEL_VERIFICATION_SOP.md)。
后续任何 Agent 在接入新模型、测试链路或进行环境清理时，必须统一以该规范中的 **两阶段解耦**、**五步标准作业流** 及 **排错矩阵** 作为最高指导准则。
