# Qwen3 Forced Aligner 原生 HF 迁移设计

## 目标

将 `qwen3_forced_aligner_0_6b` 从旧版 `qwen-asr` 全词表 logits 推理路径迁移到官方
`Qwen/Qwen3-ForcedAligner-0.6B-hf` 和 `AutoModelForTokenClassification`，解决长音频与长文本
组合导致的显存峰值过高问题。

## 架构

- 保持 BoboGen 统一生成协议、provider ID、端口和响应结构不变。
- ASR 继续使用现有 `.venv` 和 `qwen-asr`，不升级其 Transformers 依赖。
- Forced Aligner 使用独立 `.venv-aligner`，避免依赖升级影响 ASR。
- Forced Aligner 只允许官方 token-classification 路径，不保留旧实现 fallback。
- provider 配置改用 `Qwen3-ForcedAligner-0.6B-hf` 和独立模型目录。

## 数据流

1. 服务接收现有 `audio.align` 请求。
2. 官方 Processor 通过 `prepare_forced_aligner_inputs` 构建音频、文本输入。
3. `AutoModelForTokenClassification` 在推理锁内执行一次前向。
4. Processor 通过 `decode_forced_alignment` 解码时间戳。
5. 服务复用现有响应归一化逻辑返回全局时间。

## 错误与状态

- 缺少原生 Transformers 能力时明确报错，不回退旧实现。
- health 的 `ready` 同时识别 ASR `_model` 与 Forced Aligner `_aligner`。
- Forced Aligner 加载和推理均受同一把锁保护，避免重复加载和并发推理。

## 验证

- 单元测试覆盖原生 loader、processor、解码、健康状态与互斥调用。
- provider 配置测试覆盖新 checkpoint、模型目录和独立 Python 环境。
- 短音频真实 smoke test 验证协议。
- 150 秒输入验证不再发生旧版完整词表 logits OOM。
