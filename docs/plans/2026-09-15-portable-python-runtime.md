# Portable Python Runtime Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让完整离线运行包在 Windows x64 上携带一个可重定位的 CPython 3.11 解释器，解压到任意目录后无需系统 Python 即可启动已验证的本地模型服务。

**Architecture:** 当前各服务都使用 Python 3.11.9，但它们的 `.venv` 启动器依赖目录外的 `D:\app\python\Python-3.11`，因而不能作为可搬运发布物。完整运行包改为一个目录内的 `runtime/python/cp311/python.exe` 加上每服务独立的依赖目录；启动器只把目标服务的 `site-packages` 和仓库内相对源码目录加入 `sys.path`，不处理遗留 `.pth` 中的绝对 editable 路径。传统 `.venv` 安装保留为运行中心的高级/手动维护模式，而不是完整运行包的解释器来源。

**Tech Stack:** Windows PowerShell、可重定位 CPython 3.11、Python 标准库、pytest、现有 FastAPI/Uvicorn 服务。

---

## 边界与验收标准

- 本计划只处理 Python 运行时和依赖加载；FFmpeg、模型缓存位置、模型权重下载授权、Electron 数据库路径均不在本轮修改范围。
- 当前已验证模型全部处于 CPython 3.11.9 环境，因此首发完整包只提供 `cp311` 一个解释器组；只有未来出现 ABI 不兼容的模型时，才新增 `cp310` 或 `cp312` 组，绝不为每个服务复制一份解释器。
- 首阶段不移动、不删除、不重装现有 `.venv` 和模型权重，避免额外占用磁盘。其 `Lib/site-packages` 先作为只读依赖来源；后续发布打包阶段可将它改名为稳定的包目录。
- 完整包模式不得依赖系统 `python`、用户的 `PATH`、`pyvenv.cfg` 中的外部 `home`，或外部 editable `.pth` 路径。
- 每个完成且可验证的阶段直接在 `E:\AiModel\projects\bobovox\BoboVoxClient\.data\services\BoboGenServer` 提交并推送；不建立第二个工作副本。推送后用同一目录 `git pull --ff-only` 确认远端一致。

### Task 1: 定义可搬运 Python 运行时布局

**Files:**
- Create: `bobogen-gateway/app/services/runtime_layout.py`
- Create: `bobogen-gateway/tests/test_runtime_layout.py`
- Modify: `docs/services/portable-runtime.md`

**Step 1: Write the failing test**

写入临时仓库根目录测试，断言 `PortableRuntimeLayout`：

- 以仓库根作为唯一根路径；
- 将解释器解析为 `runtime/python/cp311/python.exe`；
- 将网关和指定服务的包目录解析为仓库内相对路径；
- 拒绝仓库外路径，不接受旧 `pyvenv.cfg` 的 `home`。

**Step 2: Run test to verify it fails**

Run: `runtime/gateway/.venv/Scripts/python.exe -m pytest bobogen-gateway/tests/test_runtime_layout.py -v`

Expected: FAIL，因为模块尚不存在。

**Step 3: Write minimal implementation**

实现纯路径模型，不探测或下载二进制，不改现有启动行为。所有路径由当前仓库根推导，服务名称使用现有安装器登记的目录名；任何越过根目录的输入抛出明确错误。

**Step 4: Run test to verify it passes**

Run: `runtime/gateway/.venv/Scripts/python.exe -m pytest bobogen-gateway/tests/test_runtime_layout.py -v`

Expected: PASS。

**Step 5: Commit and push**

Run: `git add bobogen-gateway/app/services/runtime_layout.py bobogen-gateway/tests/test_runtime_layout.py docs/services/portable-runtime.md && git commit -m "feat: define portable Python runtime layout" && git push origin main && git pull --ff-only`

### Task 2: 实现不读取 editable `.pth` 的进程启动引导器

**Files:**
- Create: `runtime/portable_python_launcher.py`
- Create: `bobogen-gateway/tests/test_portable_python_launcher.py`
- Modify: `docs/services/portable-runtime.md`

**Step 1: Write the failing test**

用临时目录创建一个包目录、一个包含绝对路径的 `.pth` 文件和一个可执行测试模块。断言引导器把明确给出的包目录和源码目录放入 `sys.path`，但不读取 `.pth`、不把其中路径加入 `sys.path`。

**Step 2: Run test to verify it fails**

Run: `runtime/gateway/.venv/Scripts/python.exe -m pytest bobogen-gateway/tests/test_portable_python_launcher.py -v`

Expected: FAIL，因为引导器尚不存在。

**Step 3: Write minimal implementation**

启动器仅用标准库：解析 `--packages`、`--source` 和 `--module`，规范化并验证所有目录在服务根以内，以 `sys.path.insert` 显式添加路径，然后用 `runpy.run_module(..., run_name="__main__")` 运行模块。禁止调用 `site.addsitedir`，因为它会处理 `.pth`。

**Step 4: Run test to verify it passes**

Run: `runtime/gateway/.venv/Scripts/python.exe -m pytest bobogen-gateway/tests/test_portable_python_launcher.py -v`

Expected: PASS。

**Step 5: Commit and push**

Run: `git add runtime/portable_python_launcher.py bobogen-gateway/tests/test_portable_python_launcher.py docs/services/portable-runtime.md && git commit -m "feat: add portable Python launcher" && git push origin main && git pull --ff-only`

### Task 3: 切换网关到显式完整包运行时，同时保留高级安装模式

**Files:**
- Modify: `start.ps1`
- Modify: `install.ps1`
- Modify: `bobogen-gateway/app/services/model_installer.py`
- Modify: `bobogen-gateway/tests/test_entrypoint_scripts.py`
- Modify: `bobogen-gateway/tests/test_install_script.py`
- Modify: `bobogen-gateway/tests/test_model_installer.py`
- Modify: `docs/services/portable-runtime.md`

**Step 1: Write the failing tests**

断言完整包模式只接受 `runtime/python/cp311/python.exe` 配合启动引导器，缺失时给出“完整运行包不完整”的可操作错误；断言 `install.ps1` 仍可使用系统 Python 建立传统 `.venv`，并明确标注为高级维护流程。

**Step 2: Run tests to verify they fail**

Run: `runtime/gateway/.venv/Scripts/python.exe -m pytest bobogen-gateway/tests/test_entrypoint_scripts.py bobogen-gateway/tests/test_install_script.py bobogen-gateway/tests/test_model_installer.py -v`

Expected: FAIL，因为脚本仍直接执行旧 `.venv/Scripts/python.exe`。

**Step 3: Implement minimal behavior**

`start.ps1` 先验证目录内 CPython、网关依赖目录和引导器，再由该解释器启动网关。`install.ps1` 不被删改为安装发布包；它保留系统 Python/venv 的维护用途。模型安装器显式区分完整包“已随包提供”与高级维护“创建/更新 venv”，避免安装操作意外覆盖完整包依赖。

**Step 4: Run tests to verify they pass**

Run: `runtime/gateway/.venv/Scripts/python.exe -m pytest bobogen-gateway/tests/test_entrypoint_scripts.py bobogen-gateway/tests/test_install_script.py bobogen-gateway/tests/test_model_installer.py -v`

Expected: PASS。

**Step 5: Commit and push**

Run: `git add start.ps1 install.ps1 bobogen-gateway/app/services/model_installer.py bobogen-gateway/tests/test_entrypoint_scripts.py bobogen-gateway/tests/test_install_script.py bobogen-gateway/tests/test_model_installer.py docs/services/portable-runtime.md && git commit -m "feat: start gateway with portable Python" && git push origin main && git pull --ff-only`

### Task 4: 让服务启动配置使用同一解释器与各自依赖组

**Files:**
- Modify: `configs/providers/*-windows.yaml`
- Modify: `services/*/start.ps1`
- Modify: `bobogen-gateway/app/services/installation_registry.py`（如现有目录结构实际使用此模块则更新，否则使用实际登记模块）
- Modify: corresponding tests under `bobogen-gateway/tests/`
- Modify: `docs/services/portable-runtime.md`

**Step 1: Write failing tests**

对所有已支持 Windows 本地服务断言：启动命令指向同一个 `runtime/python/cp311/python.exe` 与引导器；每个服务仅声明自己的包目录和仓库内源码目录；配置中不再把旧 `.venv/Scripts/python.exe` 作为完整包路径。

**Step 2: Run tests to verify they fail**

Run: `runtime/gateway/.venv/Scripts/python.exe -m pytest bobogen-gateway/tests/test_config_loading.py bobogen-gateway/tests/test_process_manager.py bobogen-gateway/tests/test_management_routes.py -v`

Expected: FAIL，因为当前配置仍指向多个 venv 启动器。

**Step 3: Implement minimal behavior**

为现有每个服务写相对路径启动参数。服务脚本保留人为指定 Python 的高级入口，但完整包配置不使用该入口。绝不复制解释器；所有 cp311 服务共用一个目录内 Python，隔离只来自单独的依赖路径。

**Step 4: Run tests to verify they pass**

Run: `runtime/gateway/.venv/Scripts/python.exe -m pytest bobogen-gateway/tests/test_config_loading.py bobogen-gateway/tests/test_process_manager.py bobogen-gateway/tests/test_management_routes.py -v`

Expected: PASS。

**Step 5: Commit and push**

Run: `git add configs/providers services bobogen-gateway/tests docs/services/portable-runtime.md && git commit -m "feat: launch local services with shared portable Python" && git push origin main && git pull --ff-only`

### Task 5: 固定真实可重定位 CPython 工件并实施目录内验证

**Files:**
- Create: `runtime/python/cp311/`（由固定版本、SHA-256 的发布工件解压生成；二进制不提交 Git）
- Create: `runtime/python/cp311/manifest.json`
- Create: `scripts/verify-portable-python.ps1`
- Create: `bobogen-gateway/tests/test_portable_python_manifest.py`
- Modify: `.gitignore`
- Modify: `docs/services/portable-runtime.md`

**Step 1: Write failing tests**

断言清单固定解释器版本、架构、来源、SHA-256 和相对入口；验证脚本检查实际 `python.exe -c` 的版本、架构以及绝对路径不逃出服务根。

**Step 2: Run test to verify it fails**

Run: `runtime/gateway/.venv/Scripts/python.exe -m pytest bobogen-gateway/tests/test_portable_python_manifest.py -v`

Expected: FAIL，因为清单和验证脚本尚不存在。

**Step 3: Implement and populate artifact**

选择经实际重定位验证的 CPython 3.11 Windows x86-64 分发版，记录不可变版本与校验和。仅在当前服务根 `runtime/python/cp311` 解压，绝不创建第二份模型目录或复制现有 venv。若可用空间不足，停止并报告实际所需空间，不删除已验证资产。

**Step 4: Verify in the real service directory**

Run: `powershell -ExecutionPolicy Bypass -File scripts/verify-portable-python.ps1`

Expected: 解释器为 CPython 3.11 x64，且入口与所有检查路径都位于当前 `BoboGenServer` 根目录。

**Step 5: Commit and push**

Run: `git add scripts/verify-portable-python.ps1 bobogen-gateway/tests/test_portable_python_manifest.py .gitignore docs/services/portable-runtime.md runtime/python/cp311/manifest.json && git commit -m "build: verify bundled portable Python runtime" && git push origin main && git pull --ff-only`

### Task 6: 在不同根路径完成真实启动与回归验证

**Files:**
- Modify only files needed to fix verified relocation defects from Tasks 1–5.

**Step 1: Validate without external interpreter dependency**

在当前唯一服务目录中临时把 `D:\app\python\Python-3.11` 从启动环境中排除（不改、不删该目录），执行完整包入口及至少一个轻量本地服务健康检查。验证 `sys.executable` 是目录内 `runtime/python/cp311/python.exe`。

**Step 2: Validate path relocation safely**

使用同一目录的已安装包在可逆测试方式下更改启动根路径（只建立目录联接或由测试传入替代根，绝不复制 70+ GB 模型），确认路径解析、网关、一个服务进程不引用旧绝对路径。若 Windows 文件锁或磁盘容量阻止该验证，报告原因并保留自动化路径单测。

**Step 3: Run focused regression tests**

Run: `runtime/python/cp311/python.exe runtime/portable_python_launcher.py --packages runtime/gateway/.venv/Lib/site-packages --source bobogen-gateway --module pytest -- bobogen-gateway/tests/test_runtime_layout.py bobogen-gateway/tests/test_portable_python_launcher.py bobogen-gateway/tests/test_entrypoint_scripts.py bobogen-gateway/tests/test_config_loading.py -v`

Expected: PASS。

**Step 4: Commit and push any relocation fixes**

Run: `git add <verified-fix-files> && git commit -m "fix: make portable runtime relocation-safe" && git push origin main && git pull --ff-only`

## 发布后的两种用户路径

1. **完整运行包（默认，面向普通用户）**：下载、解压、由客户端导入或放入约定数据目录；客户端只使用包内 `cp311`。用户无需安装 Python，也无需接触 `.venv`。
2. **运行中心维护（高级/兼容路径）**：使用现有 `install.ps1` 和模型安装能力，在特殊系统或新增模型时由技术用户维护传统环境。该路径不能反向成为完整包的隐性外部依赖。

