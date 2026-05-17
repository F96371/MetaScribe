# Prompt Changelog

## ingest-v1 → ingest-v2

日期：2026-05-17

v2 新增：
- video_id 字段（yt-dlp id / BV号）
- 封面统一转换 cover.jpg（ffmpeg webp→jpg）
- B站支持测试（需国内网络）

v1 特点（2026-05-16）：
- yt-dlp 提取完整 metadata
- ffprobe 校验时长
- 结构化 schema 输出
- 异常标记（warnings 字段）

注意：
- ingest 模块不使用 LLM prompt，纯 CLI 工具链

---

## transcript-v1 (FROZEN)

日期：2026-05-17

contract 终版：
- transcript_version: "v1"（reproducibility / QA / 模型升级追踪）
- video_id, model, language, duration（必填）
- segments[] — Whisper 原生输出，未做 merge/split/chunk
  - id: int（稳定编号，供 downstream trace/debug/引用）
  - start, end（float）
  - text（str）
  - confidence: Whisper avg_logprob, 范围 [-∞, 0], 越接近 0 置信度越高
- stats: {"segment_count": N, "char_count": N}（供 semantic batching / token planning）
- warnings[] — 5 项校验：顺序/重叠(10ms tol)/时长偏差(>5s)/空文本/低置信度(avg_logprob < -1.0)
- 输出目录固定: outputs/{video_id}/segments.json
- JSON Schema 导出 (draft-07)

技术：
- openai-whisper 转录
- zh/ja/ko/auto → turbo, en → small.en 模型路由
- 短(19s) / 中(8min) / 长(53min) 三级测试通过

注意：
- transcript 模块不使用 LLM prompt，纯 Whisper 模型推理
- FP16 not supported on CPU → 使用 FP32
