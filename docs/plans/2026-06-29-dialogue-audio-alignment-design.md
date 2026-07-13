# Dialogue Audio Alignment Design

## Context

BoboVox 的广播剧和视频编辑场景经常已经具备三类可信输入：

- 干音：角色对白音频已经生成或录制完成。
- 文本：剧本、对白或字幕文本已经存在。
- 时间线：音频片段在工程中的开始时间已经确定。

在这种场景下，普通 ASR 不是唯一核心能力。更关键的是把已有文本精确对齐到已有音频，得到字、词或短语级时间戳。`Qwen/Qwen3-ForcedAligner-0.6B` 适合承担这个强制对齐任务；`Qwen3-ASR` 仍用于没有可信文本时的兜底识别。

## Goal

提供一个独立的 `audio.align` 能力，用于把文本和音频对齐，生成可直接映射到编辑时间线的局部和全局时间戳。

## Proposed API

```json
{
  "model": "qwen3_forced_aligner_0_6b",
  "task": "audio.align",
  "input": {
    "audio": {"kind": "path", "path": "character_line.wav"},
    "text": "你终于来了。",
    "language": "Chinese",
    "clip_start": 120.0
  },
  "parameters": {
    "granularity": "word"
  },
  "output": {
    "format": "json"
  }
}
```

Expected response:

```json
{
  "text": "你终于来了。",
  "language": "Chinese",
  "clip_start": 120.0,
  "segments": [
    {
      "text": "你",
      "start": 0.1,
      "end": 0.22,
      "global_start": 120.1,
      "global_end": 120.22
    }
  ]
}
```

## Editing Value

- 精确字幕：逐字或逐词高亮不再依赖手工拖拽。
- 音效卡点：脚步、开门、武器、环境声可贴近具体台词词点。
- 音乐 ducking：角色开口时压低 BGM，停顿或句尾恢复。
- 口头禅/语气词处理：定位“嗯”“啊”“那个”“就是”“然后”等片段。
- 重录替换：某句对白重录后，只需重新对齐该片段。
- 多角色广播剧：每个角色干音都能对齐到剧本文本，再组合到总时间线。

## Suggested Stages

### Stage 1: Gateway Protocol

新增 `audio.align` 动态 schema 和 JSON 返回结构，不影响现有 `asr.transcribe`。

### Stage 2: Forced Aligner Service

在现有 Qwen3-ASR 服务中增加 forced aligner 加载路径，或独立拆分 `qwen3-aligner-service`。优先使用本地模型目录 `models/qwen3-asr/Qwen3-ForcedAligner-0.6B`。

### Stage 3: Timeline Integration

客户端把 `segments.start/end` 视为片段内时间，把 `global_start/global_end` 映射到工程时间线，用于标记、跳转和可视化。

### Stage 4: Filler Detection

在对齐结果之上增加规则和词表，输出可人工确认的候选项。第一版只标记，不自动删除。

### Stage 5: Editing Actions

支持静音、删除并吸附、删除但保留空隙、替换为底噪或后续重配音等操作。

## Notes

- Forced aligner 不负责识别“说了什么”，它负责把已知文本贴回音频时间轴。
- 对已有剧本/干音的广播剧工作流，强对齐优先级高于 ASR。
- 自动删除口头禅需要人工确认步骤，避免误伤正常语义词。
- 服务端只负责 `Qwen3-ForcedAligner` 精确对齐；FFmpeg 静音检测、VAD 粗切、字幕 cue 规则拆分和编辑操作由客户端负责。
- 统一对外协议仍保持 `model/task/input/parameters/output`，新增任务名为 `audio.align`，不改变 `asr.transcribe`、`tts.speech` 或 `audio.generate`。
