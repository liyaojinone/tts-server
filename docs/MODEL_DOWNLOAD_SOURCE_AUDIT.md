# 模型下载源、运行时权重与流程复盘审计（2026-09-07）

> 本文是对现有 BoboGenServer 代码、已下载的上游仓库、服务启动脚本、Provider 配置和模型管理安装器的静态审计。本文只记录事实、差异和下一步验收规则；本次不重新下载模型、不启动模型、不修改镜像行为。

## 先给结论

### 1. 这次全量模型任务没有完全按照 SOP 的“先冻结、再从零验收”执行

实际主线是：

```text
已有实现/已有目录或缓存
        ↓
通过前端触发安装、启动、预热或真实请求
        ↓
观察报错和缺失资源
        ↓
修改 BoboGenServer 自己的适配层、启动脚本、Provider 配置或安装器
        ↓
重启并再次通过前端验证
```

所以，当前结果可以准确称为：

> **修复后的实现已经按前端跑通过若干模型；但不能据此证明所有模型都已经在“最终代码冻结后、清空选中模型、从零点击安装”这个严格流程中验收通过。**

尤其不能把“最后一次请求成功”倒推为“第一次安装流程从零就是正确的”。中间发生过的修改会改变后续运行条件，已有仓库、虚拟环境、缓存和权重也会掩盖安装流程的问题。

### 2. “没有改源码”需要分清两个含义

| 说法 | 结论 | 说明 |
|---|---|---|
| 没有修改上游模型仓库源码 | **基本成立** | 没有把 `models/*/repo` 中的官方实现改成平台私有分支，也没有直接重写官方相对路径。 |
| 整个项目完全没有改代码 | **不成立** | 为了修复实际运行问题，修改过 `services/*/app`、`services/*/start.*`、`bobogen-gateway` 安装器/路由、Provider YAML 和部分服务文档。 |
| 当前所有服务仍完全走上游原生路径 | **不成立** | GPT-SoVITS、IndexTTS、VoxCPM、CosyVoice、F5-TTS、Stable Audio 等服务适配层都显式传入过本地仓库、缓存或权重路径；部分还增加了平台侧加载/兼容逻辑。 |

因此，准确表述应是：

> **上游底层仓库没有被直接改写，但平台适配代码已经改过；改动发生在若干模型首次运行失败之后，随后才重新运行验证。**

### 3. 本次结果的证据等级

当前历史记录应标记为 **“调试/修复后通过”**，而不是 **“从零验收通过”**。原因是缺少以下闭环证据：

1. 最终代码和配置冻结的时间点；
2. 只清理某一个选中模型的源码、虚拟环境和运行时缓存的记录；
3. 从前端按钮重新完成“下载仓库 → 准备环境 → 安装依赖”的完整日志；
4. 安装阶段没有下载权重的证明；
5. 再从前端启动，让官方运行时首次自行下载/定位权重的日志；
6. 失败后按同一清理范围重新开始并成功的记录。

这不是说现有修复没有价值，而是要把“修复结果”和“验收证明”分开记录。

## 一、以后必须采用的两阶段流程

### 阶段 A：探索性调试/修复（本次历史过程属于这一类）

- 可以先用现有目录、已有缓存和已有环境快速定位问题；
- 可以修改 BoboGenServer 自己的适配器、启动脚本、配置和安装器；
- 每次修改后重新通过前端启动/预热/真实请求；
- 允许得到“修复后通过”的结论；
- **不能**把这个结果称为从零安装验收，也不能证明安装器对新机器必然有效。

### 阶段 B：最终验收（以后每个模型都必须补做）

1. **冻结**：先完成代码、Provider、安装清单和源配置的评审，记录 Git diff 和版本。
2. **限定范围**：只选择一个模型；不要批量清理其他模型，不要删除用户没有授权删除的目录。
3. **清理选中模型**：清理该模型的上游仓库、专属虚拟环境、该模型的运行时缓存和本次任务产生的临时文件；权重是否删除必须有明确范围记录。
4. **前端安装**：只点击该模型的安装按钮，观察并记录“下载官方仓库 → 准备 Python 环境 → 安装官方依赖”。安装任务不应调用平台私有权重下载器。
5. **安装阶段检查**：确认只有源码和环境就绪，不把“权重已就绪”混入安装成功状态。
6. **前端启动**：再点击启动/预热/真实请求，让上游仓库及其官方 SDK 自己执行模型权重下载、缓存、路径解析和加载。
7. **源记录**：记录本次进程实际使用的 Git、PyPI、Hugging Face、ModelScope 或其他源，以及权重最终由谁、写到哪里。
8. **失败重置**：若失败，先保存日志和错误，再只清理本模型的明确范围；修复代码后重新执行第 2 步，不能把上一次残留目录当作成功依据。
9. **标记状态**：只有以上步骤全部完成，才在表格中标记“从零验收通过”；否则标记“调试通过”或“阻塞”。

可用下列状态避免混淆：

| 状态 | 含义 |
|---|---|
| `未开始` | 尚未执行该模型的流程。 |
| `调试通过` | 使用过已有状态，或在中途修复代码后通过；不能证明 clean-room 安装。 |
| `从零验收通过` | 最终代码冻结后，按本节阶段 B 从清理到前端安装、运行完整通过。 |
| `阻塞` | 已记录复现步骤和外部阻塞原因，暂时无法完成阶段 B。 |

## 二、现有安装器与 SOP 的直接矛盾

SOP 和 `docs/plans/2026-09-04-native-qwen3-asr-download-plan.md` 都规定：安装阶段只准备上游仓库和环境，权重交给运行时；但当前 `bobogen-gateway/app/services/model_installer.py` 仍会遍历 `plan["resources"]` 并主动下载/复制资源。

当前安装清单的事实如下：

| 模型 | 当前 `resources` 行为 | 当前写入位置/附加动作 | 是否符合“安装不碰权重” |
|---|---|---|---|
| CosyVoice2 | Hugging Face `snapshot_download` | 直接写入 `models/cosyvoice/repo/pretrained_models/CosyVoice2-0.5B` | **不符合** |
| F5-TTS | `resources: []` | 运行时适配器仍会使用本地 checkpoint/vocoder 或 HF cache | 安装清单符合；运行时需另审 |
| GPT-SoVITS V2Pro | PyAV FFmpeg DLL 复制、ModelScope zip、HF 文件逐个下载 | `services/gptsovits-service/ffmpeg`、`.venv/nltk_data`、`models/gpt-sovits/checkpoints/...` 等 | **不符合** |
| IndexTTS2 | Hugging Face snapshot | `models/index-tts/checkpoints` | **不符合** |
| VoxCPM2 | Hugging Face snapshot | `models/voxcpm/checkpoints` | **不符合** |
| Stable Audio 3 Small-SFX | Hugging Face snapshot cache | `models/stable-audio-3/hf-home/hub` | **不符合** |
| Stable Audio 3 Small-Music | Hugging Face snapshot cache | `models/stable-audio-3/hf-home/hub` | **不符合** |
| Stable Audio 3 Medium | Hugging Face snapshot cache | `models/stable-audio-3/hf-home/hub` | **不符合** |
| Qwen3-ASR 0.6B | `resources: []` | 运行时使用官方 Hugging Face 模型 ID | 安装清单符合 |
| Qwen3-ASR 1.7B | `resources: []` | 运行时使用官方 Hugging Face 模型 ID | 安装清单符合 |
| Qwen3 ForcedAligner 0.6B | `resources: []` | 运行时使用官方 Transformers/Hugging Face 模型 ID | 安装清单符合 |
| CAM++ Speaker Diarization | ModelScope snapshot | `models/speaker-diarization/modelscope-cache` | **不符合** |
| TIGER-DnR | Hugging Face snapshot cache | `models/tiger/TIGER-DnR` | **不符合** |

另外，当前安装器的 `mirror` 参数只在执行依赖命令时把值放到子进程的 `HF_ENDPOINT`：

```python
env = os.environ.copy()
if mirror:
    env["HF_ENDPOINT"] = mirror
```

随后 `resources` 的 `_download_hf_*`、`_download_modelscope_cache` 和 `_download_url_zip_extract` 并没有接收这个 `env`。因此当前“镜像”并不是一个覆盖整个安装流程的源配置：

- 它只影响部分依赖安装子进程；
- 它没有覆盖资源下载；
- 它没有覆盖 ModelScope 域名；
- 它没有覆盖 Git clone；
- 它没有覆盖原始 zip URL；
- 它没有覆盖运行时启动进程，除非 Provider/启动脚本另行传递。

当前 `_run_command` 对 Git、pip 和其他命令只执行一次，平台没有统一重试；原始 zip 下载使用 `urllib.request.urlopen`，失败会删除 `.part` 文件并直接报错，也没有平台重试。Hugging Face 和 ModelScope SDK 自己的重试行为属于第三方客户端内部行为，当前平台没有统一配置或验证。已安装的 ModelScope 版本源码中可见文件下载重试常量为 5 次，但这不等于所有安装步骤都有 5 次重试。

## 三、上游下载入口和本地映射审计

下表中的“当前平台”描述的是现有代码，不代表以后应该保持这种方式；“建议规则”才是要写入下一版实现的方向。

| 模型 | 上游仓库/运行时真正的下载入口 | 当前平台如何接入 | 环境变量/镜像结论 |
|---|---|---|---|
| **CosyVoice2** | `cosyvoice/cli/cosyvoice.py` 导入 ModelScope 的 `snapshot_download`；`CosyVoice2(model_dir)` 传入的参数若不是本地目录，就会被当成 ModelScope 模型 ID 下载。官方 README 同时给出 ModelScope 与 Hugging Face 两套模型 ID。 | `services/cosyvoice-service/app/handler.py` 直接把 `models/cosyvoice/repo/pretrained_models/CosyVoice2-0.5B` 作为 `model_dir`；安装器还预先把 HF snapshot 下载到该目录。 | ModelScope 官方客户端可通过 `MODELSCOPE_DOMAIN` 选择域名，`MODELSCOPE_CACHE` 选择缓存；但当前启动配置没有传域名，且当前安装器使用 HF snapshot，不能靠一个 HF 镜像变量覆盖两条路径。 |
| **F5-TTS** | `utils_infer.py` 通过 `hf_hub_download` 下载 `charactr/vocos-mel-24khz`；BigVGAN 使用 `nvidia/bigvgan_v2_24khz_100band_256x`；`socket_server.py` 默认通过 `hf_hub_download` 下载 `SWivid/F5-TTS/F5TTS_v1_Base/model_1250000.safetensors`。 | 服务适配器显式传 `hf_cache_dir`、`ckpt_file` 和本地 vocoder 路径，并优先发现项目内文件；这已经不是单纯让上游默认参数自行决定所有路径。 | Hugging Face 部分可由进程级 `HF_ENDPOINT`、`HF_HOME`/`HF_HUB_CACHE` 控制；当前 F5 启动脚本没有暴露专用 endpoint。PyTorch 的 `download.pytorch.org` 是 wheel 源，不是模型镜像。 |
| **GPT-SoVITS V2Pro** | 官方安装脚本支持 `--Source HF|HF-Mirror|ModelScope`；预训练模型、G2PW、UVR5、FunASR、Faster-Whisper 等分散在 HF/ModelScope；Windows/China 安装包和 NLTK zip 还有独立 URL。上游 `inference_webui.py` 还直接设置 `HF_ENDPOINT=https://hf-mirror.com`。 | 当前安装器绕过上游安装脚本，使用固定 GitHub clone、固定 ModelScope zip、固定 HF 文件清单，并把文件复制到 `models/gpt-sovits/checkpoints/...`；服务启动脚本再把每个 checkpoint 路径逐项传入。 | 官方安装脚本的 `--Source` 是可用的源选择入口，但当前安装器没有调用它；硬编码的 raw zip、GitHub clone 和本地 checkpoint 需要分别处理。上游强制写入 `HF_ENDPOINT` 还可能覆盖外部设置，不能只靠用户环境变量保证一致。 |
| **IndexTTS2** | README 支持 `IndexTeam/IndexTTS-2` 的 HF 或 ModelScope 下载；运行时 `infer_v2.py` 会通过 HF 下载 `facebook/w2v-bert-2.0`、`amphion/MaskGCT`、`funasr/campplus`，并按配置加载 BigVGAN；部分 Qwen 情绪模型走 ModelScope。 | 安装器把主权重 snapshot 写到 `models/index-tts/checkpoints`；服务显式传 `cfg_path` 和 `model_dir`；上游 `infer_v2.py` 在导入时硬编码 `HF_HUB_CACHE='./checkpoints/hf_cache'`，相对当前工作目录且会覆盖外部同名设置。 | 主权重可选 HF/ModelScope，但运行时还有多个固定 HF repo ID。`HF_ENDPOINT` 只能在相关模块导入前可靠设置；当前 IndexTTS 启动脚本没有暴露 endpoint，因此“用户配置一个镜像”目前不能覆盖全部下载。 |
| **VoxCPM2** | `VoxCPM.from_pretrained` 接收 HF repo ID 或本地路径；非本地路径使用 Hugging Face `snapshot_download`。可选 denoiser 默认使用 ModelScope 的 `iic/speech_zipenhancer_ans_multiloss_16k_base`。 | 当前服务把 `VOXCPM_MODEL_DIR` 当作本地 `hf_model_id`，并设置 `local_files_only=True`，同时显式检查 `config.json`、`model.safetensors`、`audiovae.pth` 和 tokenizer 路径；安装器预先把 HF snapshot 写到 checkpoint 目录。 | 若传官方 HF ID，进程级 `HF_ENDPOINT` 可以生效；当前强制本地文件时，镜像变量不会触发下载。ModelScope denoiser 需要单独的 `MODELSCOPE_DOMAIN`/cache 配置。 |
| **Stable Audio 3（三个变体）** | 上游 `model_configs.py` 使用 Hugging Face `hf_hub_download`，模型 ID 是 `stabilityai/stable-audio-3-small-sfx`、`...small-music`、`...medium`，自动编码器还使用 `stabilityai/SAME-S`/`SAME-L`。 | 当前服务的 `_resolve_model_files` 自己调用 `hf_hub_download` 获取 config、checkpoint 和 tokenizer；启动脚本固定项目内 `HF_HOME`/`HUGGINGFACE_HUB_CACHE`，Medium 还启用平台侧低内存加载适配。安装器另外预热同一 HF cache。 | 这是最接近可用 `HF_ENDPOINT` 的一类，但当前配置没有暴露 endpoint；模型 ID 仍在配置/上游代码中固定。缓存目录和源地址必须分开配置。 |
| **Qwen3-ASR 0.6B/1.7B** | 官方 `Qwen3ASRModel.from_pretrained` 最终使用 Transformers/Hugging Face `AutoModel`/`AutoProcessor.from_pretrained`；README 也给出 ModelScope 手动下载方式。 | 当前服务保持官方模型 ID（`Qwen/Qwen3-ASR-0.6B`/`1.7B`），不在安装器中预置权重；`QWEN3_ASR_HF_ENDPOINT` 由启动脚本映射成当前子进程的 `HF_ENDPOINT`。 | 这是目前源配置最清楚的一组：HF endpoint 可以进程级配置；如果改用 ModelScope，需要官方运行参数或下载入口支持，不能把 ModelScope URL 直接塞给 HF 客户端。 |
| **Qwen3 ForcedAligner 0.6B** | 官方 Transformers `AutoProcessor.from_pretrained` 与 `AutoModel.from_pretrained` 读取 `Qwen/Qwen3-ForcedAligner-0.6B-hf`；README 提供 ModelScope 手动下载方式。 | 使用独立 `.venv-aligner`，运行时仍传官方 HF repo ID；Provider 当前设置 `HF_HUB_DISABLE_XET=1`，没有设置 endpoint。 | `HF_ENDPOINT` 可作为进程级配置；`HF_HUB_DISABLE_XET` 只是传输实现开关，不是镜像地址。若要走 ModelScope，需官方支持的 ModelScope 下载或先取得本地目录。 |
| **CAM++ Speaker Diarization** | 服务直接使用 ModelScope `pipeline(task="speaker-diarization", model=..., model_revision=...)`；没有单独的 `models/*/repo` 上游仓库运行入口。 | 启动脚本只设置 `MODELSCOPE_CACHE`/`MODELSCOPE_CACHE_HOME`，安装器调用 ModelScope snapshot 写入项目缓存；Provider 当前使用 `master`，安装清单曾固定 `v1.0.0`，两者需要单独核对。 | ModelScope SDK 支持 `MODELSCOPE_DOMAIN`（域名，不要在当前版本重复写 `https://`）、`MODELSCOPE_PREFER_AI_SITE`、`MODELSCOPE_CACHE` 和 token。它是 ModelScope 的域名切换，不等于任意 HTTP 镜像。 |
| **TIGER-DnR** | `inference_dnr.py` 调用 `TIGERDNR.from_pretrained("JusperLee/TIGER-DnR", cache_dir="cache")`；模型类基于 Hugging Face Hub mixin。 | 服务显式传 `TIGER_DNR_MODEL_DIR` 作为 `cache_dir`，并固定 repo ID/revision；安装器提前 snapshot 到 `models/tiger/TIGER-DnR`。 | HF endpoint、HF cache 变量在运行时可用；当前启动脚本没有专用 endpoint，只有 repo/cache/revision 配置。 |

## 四、环境变量和地址配置：哪些能直接配，哪些不能

### A. Hugging Face 通用变量

这些变量只应该对当前安装或模型子进程生效，不应写入用户的永久系统环境：

| 变量 | 作用 | 当前注意事项 |
|---|---|---|
| `HF_ENDPOINT` | Hugging Face Hub 的服务入口 | 只对使用 `huggingface_hub`/Transformers Hub 的代码有效；必须在客户端读取配置前设置。不能用于 Git、PyPI、ModelScope 或 raw zip。 |
| `HF_HOME` | Hugging Face 总缓存根目录 | 是路径，不是镜像地址；不能拿来代替 `HF_ENDPOINT`。 |
| `HF_HUB_CACHE` / `HUGGINGFACE_HUB_CACHE` | Hub 缓存目录 | 仍然只是本地缓存位置；IndexTTS 上游会在导入时硬编码相对路径，外部设置可能被覆盖。 |
| `HF_HUB_DISABLE_XET` | 是否禁用 Xet 传输 | 只改变传输方式，不改变源，也不改变权重位置。 |

当前已经存在的模型专用包装变量只有部分覆盖：`QWEN3_ASR_HF_ENDPOINT` 会在 Qwen 启动脚本内转成进程级 `HF_ENDPOINT`；Stable Audio、F5、TIGER、IndexTTS 等没有统一的专用 endpoint 入口。

### B. ModelScope 通用变量

根据当前安装环境中 ModelScope SDK 的源码，以下变量是官方客户端认识的配置：

| 变量 | 作用 | 说明 |
|---|---|---|
| `MODELSCOPE_DOMAIN` | 指定 ModelScope 域名 | 当前 SDK 会自行补 `https://`，因此配置值应是域名/主机名，而不是带协议的完整 URL；必须确认目标站点兼容 ModelScope API。 |
| `MODELSCOPE_PREFER_AI_SITE` | 在中国站与国际站之间偏好选择 | 只影响 ModelScope 官方站点选择。 |
| `MODELSCOPE_CACHE` / `MODELSCOPE_CACHE_HOME` | ModelScope 本地缓存 | 是路径，不是镜像。 |
| `MODELSCOPE_API_TOKEN` | 私有或受限资源认证 | 不应写入仓库或普通日志。 |

ModelScope SDK 中可见文件下载重试常量为 5 次、默认超时约 60 秒；这属于 SDK 内部行为，不能推导出 Git/pip/HF/raw URL 也有同样重试次数。

### C. Python 包源

- `PIP_INDEX_URL`、`PIP_EXTRA_INDEX_URL` 可以影响 pip；但安装清单如果直接写了命令行 `--index-url https://download.pytorch.org/whl/cu128`，命令行参数会覆盖同名环境变量。
- `download.pytorch.org` 是 PyTorch wheel 源，不是 Hugging Face/ModelScope 模型源；它应单独记录。
- README 中出现的阿里云、清华 PyPI 地址只解决 Python 包下载，不会自动改变模型权重下载。
- `git+https://github.com/huggingface/transformers` 是 Git 依赖源，也不受 HF endpoint 控制。

### D. Git 仓库源

当前安装器的官方仓库 URL 直接写在 `MODEL_INSTALL_PLANS` 中，例如 CosyVoice、F5-TTS、GPT-SoVITS、IndexTTS、VoxCPM、Stable Audio、Qwen3-ASR 和 TIGER 都是 GitHub URL。当前没有一个统一的用户环境变量可以把这些 clone 地址变成镜像。

Git 源未来应通过“每个模型的官方支持参数或版本化源配置”处理，而不是修改用户的全局 Git 配置，更不能把 Git 镜像地址误当成模型权重地址。

### E. 原始 URL、OSS 和压缩包

GPT-SoVITS 安装器中的 NLTK zip 使用 `urllib.request.urlopen` 访问固定 ModelScope raw URL。这类代码不读取 `HF_ENDPOINT` 或 `MODELSCOPE_DOMAIN`，也没有统一重试。若目标镜像没有完全兼容同一 URL 结构，不能只替换域名就假设可用；应以后增加明确的、版本化的源配置并保留校验。

## 五、修改规则（本次只确认规则，不实施修改）

1. **先查官方环境变量/参数**：能用 `HF_ENDPOINT`、`MODELSCOPE_DOMAIN`、官方 `--Source` 或 SDK 的 `cache_dir`/`local_dir` 参数，就优先通过当前模型的子进程环境或官方参数传递。
2. **源和路径分离**：镜像地址回答“从哪里下载”；`HF_HOME`、`MODELSCOPE_CACHE`、`cache_dir`、`local_dir` 回答“缓存到哪里”。二者不能混成一个配置项。
3. **每条下载链独立配置**：Git、PyPI、HF Hub、ModelScope、raw URL/OSS、运行时缓存至少是六条链；不能用一个 `mirror` 字段声称全部覆盖。
4. **进程级生效**：由前端任务为子进程构造环境，任务结束后不修改用户系统环境；启动模型时也要把同一源配置明确传给该模型进程。
5. **遇到硬编码先找官方入口**：如果上游有 `--Source`、ModelScope 下载命令或参数，使用它；没有官方入口时，再考虑修改 BoboGenServer 的包装层/配置层，而不是直接编辑 `models/*/repo` 的上游文件。
6. **硬编码 URL 不等于可替换 URL**：raw URL、Git clone、安装脚本内部 URL 和代码中固定的 repo ID 必须逐项确认协议、路径、revision、鉴权和文件布局是否兼容；不能盲目字符串替换。
7. **不把镜像变成新的平台权重体系**：镜像只改变来源，不应改变官方模型 ID、官方相对路径语义或用户可 DIY 的仓库底子。
8. **安装与运行分开**：安装器以后应只做上游仓库和官方环境；运行时由上游客户端下载/缓存/加载权重。若某模型官方运行时本身必须手动下载权重，应把它记录为该模型的官方前置动作，而不是偷偷塞进通用安装器。

## 六、下一轮真正验收时要记录的字段

每个模型至少保存以下记录，才能回答“到底从哪里下载、下载到哪里、谁负责下载”：

| 字段 | 示例/要求 |
|---|---|
| 模型 ID、上游仓库 URL、源码 revision | 以安装清单和实际 `git rev-parse HEAD` 为准。 |
| 安装按钮执行的命令 | Git clone、Python/uv、pip、官方 setup 命令逐条记录。 |
| 安装阶段是否出现权重下载 | 应为“否”；若为“是”，必须说明这是官方依赖安装的必需行为还是平台误下载。 |
| 启动命令和工作目录 | 记录是否需要在上游仓库根目录运行。 |
| 子进程源变量 | `HF_ENDPOINT`、`MODELSCOPE_DOMAIN`、PyPI index、Git/raw URL 配置分别记录，不只记一个“镜像”。 |
| 上游模型 ID/参数 | 例如 `Qwen/Qwen3-ASR-0.6B`，不以平台本地目录代替。 |
| 实际缓存/权重路径 | 记录官方 SDK 最终报告的路径；不要只记录平台预设路径。 |
| 失败点和重试次数 | 区分 Git/pip/HF/ModelScope/raw URL/模型加载；注明是 SDK 内部重试还是平台重试。 |
| 清理范围和结果 | 只写选中模型的 repo、venv、runtime cache、临时文件和是否删除权重。 |
| 验收状态 | `调试通过` 或 `从零验收通过`，不能只写“已完成”。 |

## 七、本次审计后的行动边界

本次已完成的是事实梳理和规则落文档：

- 明确了历史执行顺序不是严格 clean-room SOP；
- 明确了“未改上游代码”和“改过平台适配代码”并不矛盾；
- 列出了 13 个模型的上游下载入口、当前本地路径和镜像能力；
- 区分了 HF、ModelScope、PyPI、Git、raw URL 和缓存路径；
- 找出了当前安装器 `resources` 主动下载权重、`mirror` 覆盖范围不足、无统一重试等差异；
- 定义了以后从冻结代码到前端从零验收的记录字段。

本次**没有**做以下事情：

- 没有修改模型镜像代码；
- 没有删除现有模型、仓库、虚拟环境或缓存；
- 没有重新下载权重；
- 没有启动模型服务或发起新的推理请求。

因此，下一步若要真正让“镜像可配置”和“安装阶段不碰权重”生效，应先按本文审计结果逐项评审并修改安装器、启动脚本和 Provider 配置，再对一个选中的小模型做阶段 B 的 clean-room 前端验收；不能把本次文档审计直接当成实现已完成。
