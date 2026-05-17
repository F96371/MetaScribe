"""transcript 模块输出契约 —— segments.json

下游模块 (semantic) 只读此结构。
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
import json
from pathlib import Path


@dataclass
class Segment:
    """单个转录片段 —— Whisper 原生输出，未做 merge/split/chunk。

    semantic 模块强依赖此粒度：每个 segment 是 Whisper 产生的最小语义单元。
    """
    id: int                     # 稳定编号，供 downstream trace/debug/引用
    start: float                # 秒
    end: float                  # 秒
    text: str                   # 转录文本
    confidence: Optional[float] = None  # 来源: Whisper avg_logprob, 范围 [-∞, 0], 越接近 0 置信度越高


@dataclass
class Transcript:
    """transcript 模块输出契约 —— segments.json

    下游模块（semantic, visual, render）依赖此结构。
    """

    # ---- 必填 ----
    transcript_version: str  # 模块版本 (v1)，用于 reproducibility / QA / 模型升级追踪
    video_id: str
    model: str             # whisper model name (turbo, small.en, etc.)
    language: str          # 实际检测到的语言 (zh, en, ...)
    duration: float        # 音频时长 (ffprobe 校验)
    segments: list[Segment]
    stats: dict            # {"segment_count": N, "char_count": N}，供 semantic batching / token planning

    # ---- 异常标记 ----
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "Transcript":
        segments = [Segment(**s) for s in d.get("segments", [])]
        return cls(
            transcript_version=d.get("transcript_version", "v1"),
            video_id=d["video_id"],
            model=d["model"],
            language=d["language"],
            duration=d["duration"],
            segments=segments,
            stats=d.get("stats", {}),
            warnings=d.get("warnings", []),
        )

    @staticmethod
    def json_schema() -> dict:
        """导出 JSON Schema (draft-07)，供下游模块 validation。"""
        return {
            "$schema": "https://json-schema.org/draft-07/schema#",
            "title": "Transcript",
            "type": "object",
            "required": ["transcript_version", "video_id", "model", "language", "duration", "segments", "stats"],
            "properties": {
                "transcript_version": {"type": "string", "description": "模块版本，用于 reproducibility / QA / 模型升级追踪"},
                "video_id":  {"type": "string"},
                "model":     {"type": "string", "description": "whisper model (turbo, small.en, ...)"},
                "language":  {"type": "string", "description": "detected language (zh, en, ...)"},
                "duration":  {"type": "number", "description": "实际音频时长，ffprobe 校验值"},
                "segments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id", "start", "end", "text"],
                        "properties": {
                            "id":         {"type": "integer", "description": "稳定编号，供 downstream trace/debug/引用"},
                            "start":      {"type": "number"},
                            "end":        {"type": "number"},
                            "text":       {"type": "string"},
                            "confidence": {"type": "number", "description": "来源: Whisper avg_logprob, 范围 [-∞, 0], 越接近 0 置信度越高"},
                        },
                    },
                },
                "stats": {"type": "object", "description": "segment_count + char_count，供 semantic batching / token planning"},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
        }
