"""MetaScribe 测试工具集 —— 指纹提取、归一化、diff、指标计算。"""

import json
import re
import hashlib
import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_ROOT = PROJECT_ROOT / "golden"
OUTPUT_ROOT = PROJECT_ROOT / "outputs"
GOLDEN_VIDEOS = ["jNQXAC9IVRw", "BV1Js596dEnT", "HtSuA80QTyo"]

DIFF_HARD_FAIL = "HARD_FAIL"
DIFF_SOFT_DRIFT = "SOFT_DRIFT"
DIFF_INFO = "INFO"
DIFF_MATCH = "MATCH"


# ======================================================================
# 环境检测
# ======================================================================

def check_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_AUTH_TOKEN"))


# ======================================================================
# 归一化
# ======================================================================

def normalize_metadata(data: dict) -> dict:
    d = json.loads(json.dumps(data))
    d["extracted_at"] = "<STRIPPED>"
    return d


def normalize_html(text: str) -> str:
    text = re.sub(
        r'<meta name="rendered-at" content="[^"]*">',
        '<meta name="rendered-at" content="<STRIPPED>">',
        text,
    )
    text = re.sub(
        r'MetaScribe Render v1 · [^<\n]+',
        'MetaScribe Render v1 · <STRIPPED>',
        text,
    )
    return text


# ======================================================================
# 结构指纹提取
# ======================================================================

def extract_semantic_fingerprint(data: dict) -> dict:
    chapters = data.get("chapters", [])
    chapter_fps = []
    for ch in sorted(chapters, key=lambda c: c.get("id", "")):
        points = ch.get("points", [])
        point_types = sorted(set(p.get("type", "") for p in points))
        point_type_counts = {}
        for t in ["problem", "step", "pitfall", "conclusion", "context"]:
            n = sum(1 for p in points if p.get("type") == t)
            if n > 0:
                point_type_counts[t] = n

        seg_ids = ch.get("segment_ids", [])
        ref_ids = sorted(set(
            r.get("segment_id", -1) for p in points
            for r in p.get("refs", [])
        ))

        chapter_fps.append({
            "id": ch.get("id", ""),
            "title": ch.get("title", ""),
            "start_ts": ch.get("start_ts", 0.0),
            "end_ts": ch.get("end_ts", 0.0),
            "segment_ids_count": len(seg_ids),
            "segment_ids_range": [min(seg_ids), max(seg_ids)] if seg_ids else [],
            "point_count": len(points),
            "point_types": point_types,
            "point_type_counts": point_type_counts,
            "ref_segment_ids": ref_ids,
            "all_refs_valid": all(
                (r.get("segment_id") in seg_ids)
                for p in points for r in p.get("refs", [])
            ) if points else True,
        })

    return {
        "semantic_version": data.get("semantic_version", "v1"),
        "prompt_version": data.get("prompt_version", ""),
        "video_id": data.get("video_id", ""),
        "chapter_count": len(chapters),
        "chapters": chapter_fps,
        "total_points": sum(ch["point_count"] for ch in chapter_fps),
        "warning_count": len(data.get("warnings", [])),
    }


def extract_visual_fingerprint(data: dict) -> dict:
    visuals = data.get("visuals", [])

    def spec_fp(v: dict) -> dict:
        refs = v.get("semantic_refs", [])
        return {
            "id": v.get("id", ""),
            "chapter_id": v.get("chapter_id", ""),
            "svg_type": v.get("svg_type", ""),
            "title": v.get("title", ""),
            "trigger_points": sorted(v.get("trigger_points", [])),
            "layout_hint": v.get("layout_hint", "vertical"),
            "data_keys": sorted(v.get("data", {}).keys()),
            "ref_count": len(refs),
            "ref_segment_ids": sorted(r.get("segment_id", -1) for r in refs),
            "confidence": v.get("confidence"),
        }

    return {
        "visual_version": data.get("visual_version", "v1"),
        "video_id": data.get("video_id", ""),
        "visual_count": len(visuals),
        "skipped_count": len(data.get("skipped", [])),
        "visuals": [spec_fp(v) for v in sorted(visuals, key=lambda v: v.get("id", ""))],
        "skipped_chapter_ids": sorted(
            s.get("chapter_id", "") for s in data.get("skipped", [])
        ),
        "type_distribution": data.get("stats", {}).get("type_distribution", {}),
        "coverage": data.get("stats", {}).get("coverage", 0),
        "warning_count": len(data.get("warnings", [])),
    }


# ======================================================================
# 三级 diff
# ======================================================================

def _diff_dicts(golden: dict, current: dict, path: str = "") -> list[dict]:
    """递归比较两个 dict，返回差异列表。每个差异含 path / golden / current / severity。"""
    diffs: list[dict] = []

    for key in set(golden.keys()) | set(current.keys()):
        fp = f"{path}.{key}" if path else key

        if key not in current:
            diffs.append({"path": fp, "golden": golden[key], "current": None,
                          "severity": DIFF_HARD_FAIL, "reason": "字段缺失"})
            continue
        if key not in golden:
            diffs.append({"path": fp, "golden": None, "current": current[key],
                          "severity": DIFF_INFO, "reason": "新增字段"})
            continue

        gv, cv = golden[key], current[key]

        if isinstance(gv, dict) and isinstance(cv, dict):
            diffs.extend(_diff_dicts(gv, cv, fp))
        elif isinstance(gv, list) and isinstance(cv, list):
            if len(gv) != len(cv):
                diffs.append({"path": fp, "golden": len(gv), "current": len(cv),
                              "severity": DIFF_SOFT_DRIFT,
                              "reason": f"数组长度变化 ({len(gv)}→{len(cv)})",
                              "delta_pct": round((len(cv) - len(gv)) / max(len(gv), 1) * 100, 1)})
            else:
                for i, (gi, ci) in enumerate(zip(gv, cv)):
                    if isinstance(gi, dict) and isinstance(ci, dict):
                        diffs.extend(_diff_dicts(gi, ci, f"{fp}[{i}]"))
                    elif gi != ci:
                        diffs.append({"path": f"{fp}[{i}]", "golden": gi, "current": ci,
                                      "severity": DIFF_SOFT_DRIFT, "reason": "值变化"})
        elif gv != cv:
            severity = DIFF_SOFT_DRIFT
            if key in ("id", "chapter_id", "svg_type", "visual_version", "semantic_version",
                        "all_refs_valid", "segment_ids_range"):
                severity = DIFF_HARD_FAIL
            elif key in ("warning_count", "prompt_version"):
                severity = DIFF_INFO
            diffs.append({"path": fp, "golden": gv, "current": cv,
                          "severity": severity, "reason": f"值变化 ({gv}→{cv})"})

    return diffs


def classify_diff(diffs: list[dict]) -> str:
    """返回最严重的差异级别。"""
    if not diffs:
        return DIFF_MATCH
    for d in diffs:
        if d["severity"] == DIFF_HARD_FAIL:
            return DIFF_HARD_FAIL
    for d in diffs:
        if d["severity"] == DIFF_SOFT_DRIFT:
            return DIFF_SOFT_DRIFT
    return DIFF_INFO


# ======================================================================
# 指标计算
# ======================================================================

def compute_metrics(output_dir: Path) -> dict:
    metrics = {}

    # segments
    seg_path = output_dir / "segments.json"
    if seg_path.exists():
        with open(seg_path, encoding="utf-8") as f:
            segs = json.load(f)
        metrics["segment_count"] = len(segs.get("segments", []))
        metrics["transcript_warnings"] = len(segs.get("warnings", []))

    # metadata
    meta_path = output_dir / "metadata.json"
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        metrics["metadata_warnings"] = len(meta.get("warnings", []))

    # semantic
    sem_path = output_dir / "semantic.json"
    if sem_path.exists():
        with open(sem_path, encoding="utf-8") as f:
            sem = json.load(f)
        chapters = sem.get("chapters", [])
        metrics["chapter_count"] = len(chapters)
        metrics["total_points"] = sum(len(ch.get("points", [])) for ch in chapters)
        pt_counts = {}
        for ch in chapters:
            for p in ch.get("points", []):
                t = p.get("type", "unknown")
                pt_counts[t] = pt_counts.get(t, 0) + 1
        metrics["points_by_type"] = pt_counts
        metrics["semantic_warnings"] = len(sem.get("warnings", []))

    # visual
    vis_path = output_dir / "visual_plan.json"
    if vis_path.exists():
        with open(vis_path, encoding="utf-8") as f:
            vis = json.load(f)
        metrics["visual_count"] = len(vis.get("visuals", []))
        metrics["skipped_count"] = len(vis.get("skipped", []))
        metrics["visual_warnings"] = len(vis.get("warnings", []))
        metrics["visual_type_distribution"] = vis.get("stats", {}).get("type_distribution", {})

    # HTML
    html_path = output_dir / "index.html"
    if html_path.exists():
        html_text = html_path.read_text(encoding="utf-8")
        metrics["html_size_bytes"] = len(html_text.encode("utf-8"))
        metrics["html_svg_count"] = html_text.count("<svg xmlns")
        metrics["html_chapter_sections"] = html_text.count('class="chapter-section"')

    return metrics


# ======================================================================
# Hash
# ======================================================================

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ======================================================================
# Helpers
# ======================================================================

def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def check_outputs_exist(video_id: str) -> bool:
    d = OUTPUT_ROOT / video_id
    required = ["metadata.json", "segments.json", "semantic.json", "visual_plan.json"]
    return all((d / f).exists() for f in required)
