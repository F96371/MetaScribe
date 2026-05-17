"""ingest 模块输出契约 —— metadata.json

所有下游模块只能依赖这个 schema，不能依赖 ingest 内部实现。
修改这个文件意味着系统级 breaking change。
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
import json
from pathlib import Path

# 输出根目录（相对于项目根）
OUTPUT_ROOT = "outputs"


@dataclass
class Chapter:
    start: float
    end: float
    title: str = ""
    is_generated: bool = False  # true = ingest fallback 生成, false = 平台原生


@dataclass
class MediaFile:
    """单个媒体文件的描述。

    path: 相对于项目根目录的路径，如 outputs/jNQXAC9IVRw/audio.mp3
    """
    path: str
    format: str        # mp3, jpg
    size_bytes: int
    duration_seconds: Optional[float] = None  # 仅音频文件


@dataclass
class Metadata:
    """ingest 模块输出契约 —— metadata.json

    下游模块（transcript, semantic, visual, render）必须只读此结构。
    """

    # ---- 必填 ----
    video_id: str       # yt-dlp id / BV号
    title: str
    duration: float     # 秒 (ffprobe 校验后)
    uploader: str
    source_url: str
    extracted_at: str   # ISO 8601 — [[non-deterministic]] 每次运行不同

    # ---- 可选 ----
    description: str = ""
    chapters: list[Chapter] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    view_count: int = 0
    like_count: int = 0
    upload_date: str = ""

    # ---- 产出文件 ----
    files: list[MediaFile] = field(default_factory=list)

    # ---- 异常标记 (非空时下游应判断可靠性) ----
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "Metadata":
        chapters = [Chapter(**c) for c in d.get("chapters", [])]
        files = [MediaFile(**f) for f in d.get("files", [])]
        return cls(
            video_id=d.get("video_id", ""),
            title=d["title"],
            duration=d["duration"],
            uploader=d["uploader"],
            source_url=d["source_url"],
            extracted_at=d["extracted_at"],
            description=d.get("description", ""),
            chapters=chapters,
            tags=d.get("tags", []),
            view_count=d.get("view_count", 0),
            like_count=d.get("like_count", 0),
            upload_date=d.get("upload_date", ""),
            files=files,
            warnings=d.get("warnings", []),
        )

    @staticmethod
    def json_schema() -> dict:
        """导出 JSON Schema (draft-07)，供下游模块 validation 使用。"""
        return {
            "$schema": "https://json-schema.org/draft-07/schema#",
            "title": "Metadata",
            "type": "object",
            "required": ["video_id", "title", "duration", "uploader", "source_url", "extracted_at"],
            "properties": {
                "video_id":       {"type": "string"},
                "title":          {"type": "string"},
                "duration":       {"type": "number", "minimum": 0},
                "uploader":       {"type": "string"},
                "source_url":     {"type": "string", "format": "uri"},
                "extracted_at":   {"type": "string", "format": "date-time",
                                   "description": "non-deterministic — 每次运行不同，不可用于 snapshot 比对"},
                "description":    {"type": "string"},
                "chapters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["start", "end"],
                        "properties": {
                            "start":        {"type": "number"},
                            "end":          {"type": "number"},
                            "title":        {"type": "string"},
                            "is_generated": {"type": "boolean",
                                             "description": "true=ingest 自动生成, false=平台原生章节"},
                        },
                    },
                },
                "tags":           {"type": "array", "items": {"type": "string"}},
                "view_count":     {"type": "integer"},
                "like_count":     {"type": "integer"},
                "upload_date":    {"type": "string"},
                "files": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["path", "format", "size_bytes"],
                        "properties": {
                            "path":             {"type": "string",
                                                 "description": "相对项目根路径，如 outputs/{video_id}/audio.mp3"},
                            "format":           {"type": "string"},
                            "size_bytes":       {"type": "integer"},
                            "duration_seconds": {"type": "number"},
                        },
                    },
                },
                "warnings":       {"type": "array", "items": {"type": "string"}},
            },
        }
