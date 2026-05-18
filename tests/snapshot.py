"""Snapshot 测试 —— 对比 golden snapshots vs 当前 outputs。

用法:
  python tests/snapshot.py              # 人类可读输出
  python tests/snapshot.py --json       # 机器可读 JSON 输出
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils import (
    PROJECT_ROOT, GOLDEN_ROOT, OUTPUT_ROOT, GOLDEN_VIDEOS,
    DIFF_HARD_FAIL, DIFF_SOFT_DRIFT, DIFF_INFO, DIFF_MATCH,
    normalize_metadata, normalize_html,
    extract_semantic_fingerprint, extract_visual_fingerprint,
    _diff_dicts, classify_diff, compute_metrics, load_json,
)


def compare_full_file(golden_path: Path, current_path: Path,
                      normalize_fn=None) -> tuple[str, list[dict]]:
    """逐字节比较两个文件（可选归一化）。返回 (status, diffs)。"""
    if not current_path.exists():
        return DIFF_HARD_FAIL, [{"path": current_path.name, "reason": "文件不存在"}]

    g_text = golden_path.read_text(encoding="utf-8")
    c_text = current_path.read_text(encoding="utf-8")

    if normalize_fn:
        g_text = normalize_fn(g_text) if normalize_fn == normalize_html else g_text
        c_text = normalize_fn(c_text) if normalize_fn == normalize_html else c_text

    # For JSON files
    if golden_path.suffix == ".json":
        g_data = load_json(golden_path)
        if normalize_fn == normalize_metadata:
            g_data = normalize_metadata(g_data)
        c_data = load_json(current_path)
        if normalize_fn == normalize_metadata:
            c_data = normalize_metadata(c_data)
        diffs = _diff_dicts(g_data, c_data)
        return classify_diff(diffs), diffs

    # For HTML
    if g_text != c_text:
        return DIFF_HARD_FAIL, [{"path": golden_path.name, "reason": "HTML 内容不一致"}]
    return DIFF_MATCH, []


def compare_fingerprint(golden_fp_path: Path, current_path: Path,
                        extract_fn) -> tuple[str, list[dict]]:
    """对比结构指纹。返回 (status, diffs)。"""
    if not current_path.exists():
        return DIFF_HARD_FAIL, [{"path": current_path.name, "reason": "文件不存在"}]

    g_fp = load_json(golden_fp_path)
    c_data = load_json(current_path)
    c_fp = extract_fn(c_data)

    diffs = _diff_dicts(g_fp, c_fp)
    return classify_diff(diffs), diffs


def compare_metrics(golden_manifest: dict, output_dir: Path) -> tuple[str, list[dict]]:
    """对比 metrics。返回 (status, diffs)。"""
    gm = golden_manifest.get("metrics", {})
    cm = compute_metrics(output_dir)
    diffs: list[dict] = []

    # HTML size: +-20%
    g_html = gm.get("html_size_bytes", 0)
    c_html = cm.get("html_size_bytes", 0)
    if g_html > 0:
        ratio = c_html / g_html
        if ratio > 1.2 or ratio < 0.8:
            diffs.append({
                "path": "metrics.html_size_bytes",
                "golden": g_html, "current": c_html,
                "severity": DIFF_SOFT_DRIFT,
                "reason": f"HTML 大小变化 {ratio*100:.0f}%",
                "delta_pct": round((ratio - 1) * 100, 1),
            })

    # Warning count increase
    for key, label in [("transcript_warnings", "transcript"),
                        ("semantic_warnings", "semantic"),
                        ("visual_warnings", "visual")]:
        gw = gm.get(key, 0)
        cw = cm.get(key, 0)
        if cw > gw:
            diffs.append({
                "path": f"metrics.{key}",
                "golden": gw, "current": cw,
                "severity": DIFF_SOFT_DRIFT,
                "reason": f"{label} warnings 增加 ({gw}→{cw})",
            })

    # SVG count change
    g_svg = gm.get("html_svg_count", 0)
    c_svg = cm.get("html_svg_count", 0)
    if c_svg != g_svg:
        diffs.append({
            "path": "metrics.html_svg_count",
            "golden": g_svg, "current": c_svg,
            "severity": DIFF_SOFT_DRIFT,
            "reason": f"SVG 数量变化 ({g_svg}→{c_svg})",
        })

    # Chapter count change
    g_ch = gm.get("chapter_count", 0)
    c_ch = cm.get("chapter_count", 0)
    if c_ch != g_ch:
        diffs.append({
            "path": "metrics.chapter_count",
            "golden": g_ch, "current": c_ch,
            "severity": DIFF_SOFT_DRIFT,
            "reason": f"章节数变化 ({g_ch}→{c_ch})",
        })

    # Point count drift >30%
    g_pts = gm.get("total_points", 0)
    c_pts = cm.get("total_points", 0)
    if g_pts > 0:
        ratio = c_pts / g_pts
        if ratio > 1.3 or ratio < 0.7:
            diffs.append({
                "path": "metrics.total_points",
                "golden": g_pts, "current": c_pts,
                "severity": DIFF_SOFT_DRIFT,
                "reason": f"信息点数量漂移 {ratio*100:.0f}%",
                "delta_pct": round((ratio - 1) * 100, 1),
            })

    return classify_diff(diffs), diffs


def run_snapshot(video_id: str) -> dict:
    """对单个视频运行 snapshot 对比。返回结果 dict。"""
    g_manifest = load_json(GOLDEN_ROOT / "manifests" / f"{video_id}.json")
    g_snap = GOLDEN_ROOT / "snapshots" / video_id
    cur = OUTPUT_ROOT / video_id

    result = {"video_id": video_id, "files": {}}

    # metadata.json
    status, diffs = compare_full_file(
        g_snap / "metadata.json", cur / "metadata.json",
        normalize_fn=normalize_metadata,
    )
    result["files"]["metadata"] = {"status": status, "diffs": diffs}

    # segments.json
    status, diffs = compare_full_file(g_snap / "segments.json", cur / "segments.json")
    result["files"]["segments"] = {"status": status, "diffs": diffs}

    # semantic.snapshot.json (fingerprint)
    status, diffs = compare_fingerprint(
        g_snap / "semantic.snapshot.json", cur / "semantic.json",
        extract_fn=extract_semantic_fingerprint,
    )
    result["files"]["semantic"] = {"status": status, "diffs": diffs}

    # visual.snapshot.json (fingerprint)
    status, diffs = compare_fingerprint(
        g_snap / "visual.snapshot.json", cur / "visual_plan.json",
        extract_fn=extract_visual_fingerprint,
    )
    result["files"]["visual"] = {"status": status, "diffs": diffs}

    # index.html
    status, diffs = compare_full_file(
        g_snap / "index.html", cur / "index.html",
        normalize_fn=normalize_html,
    )
    result["files"]["index_html"] = {"status": status, "diffs": diffs}

    # metrics
    m_status, m_diffs = compare_metrics(g_manifest, cur)
    cm = compute_metrics(cur)
    result["metrics"] = {
        "status": m_status,
        "diffs": m_diffs,
        "html_kb": round(cm.get("html_size_bytes", 0) / 1024, 1),
        "warnings": cm.get("semantic_warnings", 0) + cm.get("visual_warnings", 0),
        "svgs": cm.get("html_svg_count", 0),
        "points": cm.get("total_points", 0),
    }

    return result


def run_all() -> tuple[dict, float]:
    """运行所有视频的 snapshot 对比。"""
    started = time.time()
    all_results = {}
    for vid in GOLDEN_VIDEOS:
        all_results[vid] = run_snapshot(vid)
    elapsed = round(time.time() - started, 2)
    return all_results, elapsed


# ======================================================================
# 输出
# ======================================================================

def print_human(results: dict, elapsed: float):
    """人类可读输出。"""
    for vid, r in results.items():
        print(f"\nSNAPSHOT: {vid}")
        file_names = {
            "metadata": "metadata.json",
            "segments": "segments.json",
            "semantic": "semantic.snapshot",
            "visual": "visual.snapshot",
            "index_html": "index.html",
        }
        for key, label in file_names.items():
            f = r["files"][key]
            status = f["status"]
            marker = {"MATCH": "✓", "HARD_FAIL": "✗", "SOFT_DRIFT": "~", "INFO": "i"}.get(status, "?")
            print(f"  {marker} {label:22s} {status}")
            if f["diffs"]:
                for d in f["diffs"][:3]:
                    print(f"      {d['path']}: {d.get('reason', '?')}")

        m = r["metrics"]
        m_status = m["status"]
        print(f"  Metrics:  {m_status}  (HTML:{m['html_kb']}KB W:{m['warnings']} SVG:{m['svgs']} Pts:{m['points']})")

    # Summary
    hf = sof = info = mat = 0
    for r in results.values():
        for f in r["files"].values():
            s = f["status"]
            if s == DIFF_HARD_FAIL: hf += 1
            elif s == DIFF_SOFT_DRIFT: sof += 1
            elif s == DIFF_INFO: info += 1
            else: mat += 1
        if r["metrics"]["status"] == DIFF_HARD_FAIL: hf += 1
        elif r["metrics"]["status"] == DIFF_SOFT_DRIFT: sof += 1

    total = hf + sof + info + mat
    print(f"\n{'='*50}")
    print(f"Summary: {mat} MATCH, {sof} SOFT DRIFT, {info} INFO, {hf} HARD FAIL")
    print(f"Time: {elapsed}s")
    print(f"{'='*50}")


def print_json(results: dict, elapsed: float):
    """机器可读 JSON 输出。"""
    output = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "snapshot",
        "results": {},
        "summary": {"total_videos": 0, "match": 0, "hard_fail": 0, "soft_drift": 0, "info": 0},
        "wall_seconds": elapsed,
    }

    for vid, r in results.items():
        entry = {}
        for key, label in [("metadata", "metadata"), ("segments", "segments"),
                           ("semantic", "semantic"), ("visual", "visual"),
                           ("index_html", "index_html")]:
            f = r["files"][key]
            entry[label] = {"status": f["status"]}
            if f["diffs"]:
                entry[label]["diffs"] = f["diffs"]
        entry["metrics"] = r["metrics"]
        output["results"][vid] = entry

    s = output["summary"]
    s["total_videos"] = len(results)
    for r in results.values():
        for f in r["files"].values():
            st = f["status"]
            if st == DIFF_MATCH: s["match"] += 1
            elif st == DIFF_HARD_FAIL: s["hard_fail"] += 1
            elif st == DIFF_SOFT_DRIFT: s["soft_drift"] += 1
            elif st == DIFF_INFO: s["info"] += 1

    # exit_code: 0 unless HARD_FAIL
    output["exit_code"] = 1 if s["hard_fail"] > 0 else 0

    print(json.dumps(output, ensure_ascii=False, indent=2))


# ======================================================================
# CLI
# ======================================================================

if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    json_mode = "--json" in sys.argv

    results, elapsed = run_all()

    if json_mode:
        print_json(results, elapsed)
    else:
        print_human(results, elapsed)

    # exit(1) only on HARD_FAIL
    has_hard_fail = any(
        f["status"] == DIFF_HARD_FAIL
        for r in results.values()
        for f in r["files"].values()
    )
    sys.exit(1 if has_hard_fail else 0)
