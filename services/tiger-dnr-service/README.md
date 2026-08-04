# TIGER-DnR Separation Service

该服务将影视混音异步拆分为两个公开产物：

- `dialogue`：TIGER-DnR 估计的对白。
- `background`：按 `decoded_original - dialogue` 计算的全部非对白声音。

输出固定为源采样率、源声道数和源 frame count 的 32-bit float WAV。服务采用
6 秒分块、50% overlap 和单 GPU worker，任务支持进度、取消、产物下载与清理。
长音频不会整段载入内存：输入按固定块读取，overlap-add 累积区使用磁盘 memmap，
对白和残差背景声按固定块写入并再次流式校验。内存占用主要由单个推理块决定，
而不是随视频时长线性增长。

本地目录：

```text
models/tiger/repo             # 官方 MIT 代码
models/tiger/TIGER-DnR        # Apache-2.0 权重缓存
services/tiger-dnr-service/.venv
```

当前已验证版本：

- 官方源码：`JusperLee/TIGER`，commit
  `9f18d4a10a7137e1ce8052cfb62215179f1287b6`，仓库 `LICENSE` 为 MIT。
- 模型权重：`JusperLee/TIGER-DnR`，revision
  `b7a59560bbca10febbcd46fb01600f868e587f57`，模型页标注 Apache-2.0。
- 运行环境：Python 3.11.9、PyTorch/Torchaudio 2.11.0+cu128。

Windows + NVIDIA CUDA 安装：

```powershell
git clone https://github.com/JusperLee/TIGER.git models/tiger/repo
git -C models/tiger/repo checkout 9f18d4a10a7137e1ce8052cfb62215179f1287b6

py -3.11 -m venv services/tiger-dnr-service/.venv
services/tiger-dnr-service/.venv/Scripts/python.exe -m pip install `
  --index-url https://download.pytorch.org/whl/cu128 `
  torch==2.11.0+cu128 torchaudio==2.11.0+cu128
services/tiger-dnr-service/.venv/Scripts/python.exe -m pip install `
  -e "services/tiger-dnr-service[model,test]"
```

首次真实任务会把固定 revision 的权重下载到
`models/tiger/TIGER-DnR`。FFmpeg 需位于 `PATH` 中，用于解码 M4A 等
libsndfile 不能直接读取的格式。

启动：

```powershell
.\start.ps1
```

环境变量：

- `TIGER_DNR_DEVICE`：默认 `cuda:0`。
- `TIGER_DNR_MODEL_DIR`：Hugging Face 权重缓存目录。
- `TIGER_DNR_HF_REVISION`：默认固定为上述已验证权重 revision。
- `TIGER_DNR_JOB_ROOT`：任务和产物目录。
- `TIGER_DNR_TEST_MODE=true`：不加载真实模型，用于本地协议测试。

任务输入由服务复制到自己的 job 目录，避免 Gateway 清理上传缓存时中断
运行中的任务。客户端可以先调用 cancel，再立即 DELETE；运行中的 worker 会在
安全停止后自动删除私有输入、manifest、临时文件和产物。
