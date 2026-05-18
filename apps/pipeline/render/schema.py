"""render 模块输入契约 —— 三个上游 JSON 文件的数据模型。

独立定义，不从兄弟模块 import，保持模块间松耦合。
"""

from dataclasses import dataclass, field
from typing import Optional
import json
from pathlib import Path


# ---------------------------------------------------------------------------
# metadata.json
# ---------------------------------------------------------------------------

@dataclass
class MediaFile:
    path: str
    format: str
    size_bytes: int
    duration_seconds: Optional[float] = None

    @classmethod
    def from_dict(cls, d: dict) -> "MediaFile":
        return cls(
            path=d["path"],
            format=d["format"],
            size_bytes=d["size_bytes"],
            duration_seconds=d.get("duration_seconds"),
        )


@dataclass
class MediaMetadata:
    video_id: str
    title: str
    duration: float
    uploader: str
    source_url: str
    extracted_at: str
    description: str = ""
    chapters: list[dict] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    view_count: int = 0
    like_count: int = 0
    upload_date: str = ""
    files: list[MediaFile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "MediaMetadata":
        return cls(
            video_id=d["video_id"],
            title=d["title"],
            duration=d["duration"],
            uploader=d["uploader"],
            source_url=d.get("source_url", ""),
            extracted_at=d.get("extracted_at", ""),
            description=d.get("description", ""),
            chapters=d.get("chapters", []),
            tags=d.get("tags", []),
            view_count=d.get("view_count", 0),
            like_count=d.get("like_count", 0),
            upload_date=d.get("upload_date", ""),
            files=[MediaFile.from_dict(f) for f in d.get("files", [])],
            warnings=d.get("warnings", []),
        )


# ---------------------------------------------------------------------------
# semantic.json
# ---------------------------------------------------------------------------

@dataclass
class SegmentRef:
    segment_id: int
    ts: float
    quote: str

    @classmethod
    def from_dict(cls, d: dict) -> "SegmentRef":
        return cls(
            segment_id=d["segment_id"],
            ts=d.get("ts", 0.0),
            quote=d.get("quote", "")[:40],
        )


@dataclass
class InfoPoint:
    type: str
    content: str
    confidence: float = 0.5
    refs: list[SegmentRef] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "InfoPoint":
        return cls(
            type=d["type"],
            content=d["content"],
            confidence=d.get("confidence", 0.5),
            refs=[SegmentRef.from_dict(r) for r in d.get("refs", [])],
        )


@dataclass
class SemanticChapter:
    id: str
    title: str
    start_ts: float
    end_ts: float
    segment_ids: list[int] = field(default_factory=list)
    points: list[InfoPoint] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "SemanticChapter":
        return cls(
            id=d["id"],
            title=d["title"],
            start_ts=d.get("start_ts", 0.0),
            end_ts=d.get("end_ts", 0.0),
            segment_ids=d.get("segment_ids", []),
            points=[InfoPoint.from_dict(p) for p in d.get("points", [])],
        )


@dataclass
class SemanticData:
    semantic_version: str
    prompt_version: str
    video_id: str
    chapters: list[SemanticChapter] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "SemanticData":
        return cls(
            semantic_version=d["semantic_version"],
            prompt_version=d.get("prompt_version", "v1"),
            video_id=d["video_id"],
            chapters=[SemanticChapter.from_dict(ch) for ch in d.get("chapters", [])],
        )


# ---------------------------------------------------------------------------
# visual_plan.json
# ---------------------------------------------------------------------------

@dataclass
class VisualRef:
    segment_id: int
    ts: float = 0.0
    quote: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "VisualRef":
        return cls(
            segment_id=d["segment_id"],
            ts=d.get("ts", 0.0),
            quote=d.get("quote", "")[:40],
        )


@dataclass
class VisualSpec:
    id: str
    chapter_id: str
    svg_type: str
    title: str
    rationale: str
    trigger_points: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    semantic_refs: list[VisualRef] = field(default_factory=list)
    layout_hint: str = "vertical"
    confidence: float = 0.5

    @classmethod
    def from_dict(cls, d: dict) -> "VisualSpec":
        return cls(
            id=d["id"],
            chapter_id=d["chapter_id"],
            svg_type=d["svg_type"],
            title=d["title"],
            rationale=d.get("rationale", ""),
            trigger_points=d.get("trigger_points", []),
            data=d.get("data", {}),
            semantic_refs=[VisualRef.from_dict(r) for r in d.get("semantic_refs", [])],
            layout_hint=d.get("layout_hint", "vertical"),
            confidence=d.get("confidence", 0.5),
        )


@dataclass
class VisualPlanData:
    visual_version: str
    video_id: str
    visuals: list[VisualSpec] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "VisualPlanData":
        return cls(
            visual_version=d["visual_version"],
            video_id=d["video_id"],
            visuals=[VisualSpec.from_dict(v) for v in d.get("visuals", [])],
            skipped=d.get("skipped", []),
            stats=d.get("stats", {}),
            warnings=d.get("warnings", []),
        )


# ---------------------------------------------------------------------------
# segments.json
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    start: float
    end: float
    text: str
    confidence: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "Segment":
        return cls(
            start=d["start"],
            end=d["end"],
            text=d["text"],
            confidence=d.get("confidence", 0.0),
        )


# ---------------------------------------------------------------------------
# RenderInputs — 统一容器
# ---------------------------------------------------------------------------

@dataclass
class RenderInputs:
    meta: MediaMetadata
    semantic: SemanticData
    visual: VisualPlanData
    segments: dict[int, Segment]

    @classmethod
    def load(cls, output_dir: Path) -> "RenderInputs":
        with open(output_dir / "metadata.json", encoding="utf-8") as f:
            meta = MediaMetadata.from_dict(json.load(f))
        with open(output_dir / "semantic.json", encoding="utf-8") as f:
            semantic = SemanticData.from_dict(json.load(f))
        with open(output_dir / "visual_plan.json", encoding="utf-8") as f:
            visual = VisualPlanData.from_dict(json.load(f))
        with open(output_dir / "segments.json", encoding="utf-8") as f:
            segs_raw = json.load(f)
            segments = {
                i: Segment.from_dict(s)
                for i, s in enumerate(segs_raw.get("segments", []))
            }
        return cls(meta=meta, semantic=semantic, visual=visual, segments=segments)
