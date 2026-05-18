"""semantic 模块输出契约 —— semantic.json

下游模块 (visual, render) 只读此结构。
"""

from dataclasses import dataclass, field, asdict
import json
from pathlib import Path


@dataclass
class SegmentRef:
    """对原始 segment 的可追溯引用。"""
    segment_id: int    # segments.json 中的 id
    ts: float          # segment.start，用于回跳
    quote: str         # 原文关键短句（≤40字），非改写


@dataclass
class InfoPoint:
    """单个信息点 —— 高密度、可追溯、白话。

    type 取值: problem | step | pitfall | conclusion | context
    章节内 type 可以缺失（无则不留空壳）。
    """
    type: str                # 信息类型
    content: str             # 白话提炼，非论文腔，非总结腔
    refs: list[SegmentRef]   # 至少 1 个，锚定原文
    confidence: float        # 0-1, LLM 自评提取可信度

    def __post_init__(self):
        if not self.refs:
            raise ValueError(f"InfoPoint 必须至少有一个 SegmentRef: {self.content[:40]}")
        valid_types = {"problem", "step", "pitfall", "conclusion", "context"}
        if self.type not in valid_types:
            raise ValueError(f"InfoPoint type 无效: {self.type}")


@dataclass
class Chapter:
    """一个逻辑章节。"""
    id: str                  # "ch01", "ch02", ...
    title: str               # 章节主题（提炼，非原文照抄）
    start_ts: float          # 章节起始时间
    end_ts: float            # 章节结束时间
    segment_ids: list[int]   # 覆盖的 segment id 范围
    points: list[InfoPoint]  # 该章节的信息点（可空）

    @property
    def point_count(self) -> int:
        return len(self.points)


@dataclass
class Semantic:
    """semantic 模块输出契约 —— semantic.json

    下游模块（visual, render）依赖此结构。
    """

    # ---- 必填 ----
    semantic_version: str    # 模块版本，用于 reproducibility
    prompt_version: str      # 使用的 prompt 版本
    video_id: str
    chapters: list[Chapter]

    # ---- 统计 ----
    stats: dict              # {chapter_count, total_points, type_distribution, ...}

    # ---- 异常标记 ----
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "Semantic":
        chapters = []
        for ch in d.get("chapters", []):
            points = []
            for p in ch.get("points", []):
                refs = [SegmentRef(**r) for r in p.get("refs", [])]
                points.append(InfoPoint(
                    type=p["type"],
                    content=p["content"],
                    refs=refs,
                    confidence=p.get("confidence", 0.5),
                ))
            chapters.append(Chapter(
                id=ch["id"],
                title=ch["title"],
                start_ts=ch["start_ts"],
                end_ts=ch["end_ts"],
                segment_ids=ch.get("segment_ids", []),
                points=points,
            ))
        return cls(
            semantic_version=d.get("semantic_version", "v1"),
            prompt_version=d.get("prompt_version", "unknown"),
            video_id=d["video_id"],
            chapters=chapters,
            stats=d.get("stats", {}),
            warnings=d.get("warnings", []),
        )

    @staticmethod
    def json_schema() -> dict:
        """导出 JSON Schema (draft-07)，供下游模块 validation。"""
        return {
            "$schema": "https://json-schema.org/draft-07/schema#",
            "title": "Semantic",
            "type": "object",
            "required": ["semantic_version", "prompt_version", "video_id", "chapters", "stats"],
            "properties": {
                "semantic_version": {"type": "string", "description": "模块版本"},
                "prompt_version":    {"type": "string", "description": "使用的 prompt 模板版本"},
                "video_id":          {"type": "string"},
                "chapters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id", "title", "start_ts", "end_ts", "segment_ids", "points"],
                        "properties": {
                            "id":          {"type": "string"},
                            "title":       {"type": "string"},
                            "start_ts":    {"type": "number"},
                            "end_ts":      {"type": "number"},
                            "segment_ids": {"type": "array", "items": {"type": "integer"}},
                            "points": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["type", "content", "refs", "confidence"],
                                    "properties": {
                                        "type":       {"type": "string", "enum": ["problem", "step", "pitfall", "conclusion", "context"]},
                                        "content":    {"type": "string"},
                                        "confidence": {"type": "number"},
                                        "refs": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "required": ["segment_id", "ts", "quote"],
                                                "properties": {
                                                    "segment_id": {"type": "integer"},
                                                    "ts":         {"type": "number"},
                                                    "quote":      {"type": "string"},
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
                "stats":    {"type": "object"},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
        }
