"""visual 模块输出契约 —— visual_plan.json

下游模块 (render) 只读此结构。
visual 模块只负责「可视化决策与规划」，不负责 render。
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
import json
from pathlib import Path


# ---------------------------------------------------------------------------
# SegmentRef — 对原始 segment 的可追溯引用（与 semantic 共用定义）
# ---------------------------------------------------------------------------

@dataclass
class SegmentRef:
    segment_id: int
    ts: float
    quote: str


# ---------------------------------------------------------------------------
# VisualSpec — 单个可视化规划
# ---------------------------------------------------------------------------

@dataclass
class VisualSpec:
    """单个可视化决策。

    描述: 对某个章节，是否需要 SVG，什么类型，数据如何组织。
    """
    id: str                    # "vis01", "vis02", ...
    chapter_id: str            # 对应 semantic chapter id
    svg_type: str              # SVG 类型（见 taxonomy）
    title: str                 # 图表标题（≤20字，具体非空洞）
    rationale: str             # 为何触发此图（简短理由，基于具体内容）
    trigger_points: list[str]  # 触发的 semantic point type 组合

    # 结构化的渲染数据（由 render 模块消费）
    data: dict                 # SVG 类型决定其结构

    # 可追溯性
    semantic_refs: list[SegmentRef]  # 引用的关键 segment

    # 布局提示
    layout_hint: str = "vertical"  # "horizontal" | "vertical" | "grid"

    confidence: float = 0.5    # 0-1，可视化必要性置信度


# ---------------------------------------------------------------------------
# VisualPlan — 模块输出
# ---------------------------------------------------------------------------

@dataclass
class VisualPlan:
    """visual 模块输出契约 —— visual_plan.json

    下游模块（render）依赖此结构。
    """

    # ---- 必填 ----
    visual_version: str       # 模块版本
    video_id: str
    visuals: list[VisualSpec] # 所有可视化规划

    # ---- 跳过记录 ----
    skipped: list[dict]       # [{chapter_id, reason}]  未触发的章节及原因

    # ---- 统计 ----
    stats: dict               # {total_visuals, type_distribution, coverage}

    # ---- 异常标记 ----
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "VisualPlan":
        visuals = []
        for v in d.get("visuals", []):
            refs = [SegmentRef(**r) for r in v.get("semantic_refs", [])]
            visuals.append(VisualSpec(
                id=v["id"],
                chapter_id=v["chapter_id"],
                svg_type=v["svg_type"],
                title=v["title"],
                rationale=v["rationale"],
                trigger_points=v.get("trigger_points", []),
                data=v.get("data", {}),
                semantic_refs=refs,
                layout_hint=v.get("layout_hint", "vertical"),
                confidence=v.get("confidence", 0.5),
            ))
        return cls(
            visual_version=d["visual_version"],
            video_id=d["video_id"],
            visuals=visuals,
            skipped=d.get("skipped", []),
            stats=d.get("stats", {}),
            warnings=d.get("warnings", []),
        )

    @staticmethod
    def json_schema() -> dict:
        """导出 JSON Schema (draft-07)。"""
        return {
            "$schema": "https://json-schema.org/draft-07/schema#",
            "title": "VisualPlan",
            "type": "object",
            "required": ["visual_version", "video_id", "visuals", "skipped", "stats"],
            "properties": {
                "visual_version": {"type": "string"},
                "video_id":       {"type": "string"},
                "visuals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id", "chapter_id", "svg_type", "title", "rationale", "data"],
                        "properties": {
                            "id":             {"type": "string"},
                            "chapter_id":     {"type": "string"},
                            "svg_type":       {"type": "string", "enum": ["flowchart", "matrix", "timeline", "chain", "layered", "decision_tree", "checklist", "none"]},
                            "title":          {"type": "string"},
                            "rationale":      {"type": "string"},
                            "trigger_points": {"type": "array", "items": {"type": "string"}},
                            "data":           {"type": "object"},
                            "layout_hint":    {"type": "string"},
                            "confidence":     {"type": "number"},
                            "semantic_refs": {
                                "type": "array",
                                "items": {
                                    "type": "object",
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
                "skipped": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "chapter_id": {"type": "string"},
                            "reason":     {"type": "string"},
                        },
                    },
                },
                "stats":    {"type": "object"},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
        }
