"""性能基线 —— 收集 per-stage wall-clock / size / count 指标。

用法:
  python tests/perf.py                        # 首次运行：生成 baselines/perf-baseline.json
  python tests/perf.py --compare               # 与 baseline 对比（ratio-based）
  python tests/perf.py --json                  # JSON 输出
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "pipeline" / "render"))

from utils import (
    PROJECT_ROOT, GOLDEN_ROOT, OUTPUT_ROOT, GOLDEN_VIDEOS,
    compute_metrics, check_api_key, DIFF_MATCH, DIFF_SOFT_DRIFT, DIFF_INFO,
)

BASELINE_PATH = GOLDEN_ROOT / "baselines" / "perf-baseline.json"


def collect_stage(video_id: str) -> dict:
    """收集单个视频的 render 阶段指标（离线）。"""
    import importlib.util

    t0 = time.time()

    # Load render module and run build_html
    spec = importlib.util.spec_from_file_location(
        "render", PROJECT_ROOT / "apps" / "pipeline" / "render" / "render.py"
    )
    render_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(render_mod)

    output_dir = OUTPUT_ROOT / video_id
    html = render_mod.build_html(output_dir)
    elapsed = round(time.time() - t0, 3)

    # Load existing outputs for stats
    metrics = compute_metrics(output_dir)

    # Estimate token counts from file sizes (rough heuristic)
    sem_path = output_dir / "semantic.json"
    vis_path = output_dir / "visual_plan.json"
    sem_tokens_est = len(sem_path.read_text(encoding="utf-8")) // 2 if sem_path.exists() else None
    vis_tokens_est = len(vis_path.read_text(encoding="utf-8")) // 2 if vis_path.exists() else None

    return {
        "render": {
            "wall_seconds": elapsed,
            "html_size_bytes": len(html.encode("utf-8")),
            "svg_count": metrics.get("html_svg_count", 0),
        },
        "semantic_tokens_estimated": sem_tokens_est,
        "visual_tokens_estimated": vis_tokens_est,
        "chapter_count": metrics.get("chapter_count", 0),
        "point_count": metrics.get("total_points", 0),
        "visual_count": metrics.get("visual_count", 0),
    }


def collect_all() -> dict:
    baseline = {
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": "v1",
        "videos": {},
    }
    for vid in GOLDEN_VIDEOS:
        dur = 0
        meta_path = OUTPUT_ROOT / vid / "metadata.json"
        if meta_path.exists():
            with open(meta_path, encoding="utf-8") as f:
                dur = json.load(f).get("duration", 0)
        baseline["videos"][vid] = {
            "duration_seconds": dur,
            "stages": collect_stage(vid),
        }
    return baseline


def compare_baseline(current: dict, golden: dict) -> list[dict]:
    """Ratio-based 对比。返回 SOFT_DRIFT 列表。"""
    drifts: list[dict] = []
    for vid in GOLDEN_VIDEOS:
        if vid not in golden.get("videos", {}) or vid not in current.get("videos", {}):
            continue
        gs = golden["videos"][vid]["stages"]
        cs = current["videos"][vid]["stages"]

        # render wall_seconds
        gw = gs.get("render", {}).get("wall_seconds", 0)
        cw = cs.get("render", {}).get("wall_seconds", 0)
        if gw > 0 and cw > gw * 2.0:
            drifts.append({
                "video_id": vid, "stage": "render", "metric": "wall_seconds",
                "golden": gw, "current": cw, "ratio": round(cw / gw, 2),
                "severity": DIFF_SOFT_DRIFT,
            })

        # HTML size
        gs_size = gs.get("render", {}).get("html_size_bytes", 0)
        cs_size = cs.get("render", {}).get("html_size_bytes", 0)
        if gs_size > 0:
            r = cs_size / gs_size
            if r > 1.5 or r < 0.5:
                drifts.append({
                    "video_id": vid, "stage": "render", "metric": "html_size_bytes",
                    "golden": gs_size, "current": cs_size, "ratio": round(r, 2),
                    "severity": DIFF_SOFT_DRIFT,
                })

        # SVG count
        gs_svg = gs.get("render", {}).get("svg_count", 0)
        cs_svg = cs.get("render", {}).get("svg_count", 0)
        if cs_svg != gs_svg:
            drifts.append({
                "video_id": vid, "stage": "render", "metric": "svg_count",
                "golden": gs_svg, "current": cs_svg,
                "severity": DIFF_INFO,
            })

    return drifts


# ======================================================================
# CLI
# ======================================================================

if __name__ == "__main__":
    compare_mode = "--compare" in sys.argv
    json_mode = "--json" in sys.argv

    current = collect_all()

    if compare_mode and BASELINE_PATH.exists():
        with open(BASELINE_PATH, encoding="utf-8") as f:
            golden = json.load(f)
        drifts = compare_baseline(current, golden)
        if json_mode:
            print(json.dumps({
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "drifts": drifts,
                "exit_code": 0,
            }, ensure_ascii=False, indent=2))
        else:
            print("Performance Baseline Comparison")
            print("-" * 50)
            if drifts:
                for d in drifts:
                    print(f"  [{d['severity']}] {d['video_id']}/{d['stage']}/{d['metric']}: "
                          f"{d['golden']}→{d['current']} (×{d['ratio']})")
            else:
                print("  All metrics within baseline range.")
            print(f"  Drifts: {len(drifts)}")
    else:
        # First run: save baseline
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BASELINE_PATH, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        if json_mode:
            print(json.dumps({"status": "baseline_created", "path": str(BASELINE_PATH)}, ensure_ascii=False))
        else:
            print(f"Performance baseline saved to {BASELINE_PATH}")
            for vid, vd in current["videos"].items():
                r = vd["stages"]["render"]
                print(f"  {vid}: render={r['wall_seconds']}s HTML={r['html_size_bytes']}B SVG={r['svg_count']}")
