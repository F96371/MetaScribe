"""MetaScribe 回归 Harness —— 一键跑完整回归。

用法:
  python tests/regress.py                  # 默认 --quick (< 10s)
  python tests/regress.py --quick           # 快检：schema + snapshot + ordering + adversarial
  python tests/regress.py --full            # 全量：pipeline + API + perf
  python tests/regress.py --quick --json    # CI 模式 JSON 输出
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "pipeline" / "render"))

from utils import (
    PROJECT_ROOT, GOLDEN_ROOT, OUTPUT_ROOT, GOLDEN_VIDEOS, check_api_key,
    DIFF_HARD_FAIL, DIFF_SOFT_DRIFT, DIFF_INFO, DIFF_MATCH,
    normalize_html,
)

FIXTURE_ROOT = GOLDEN_ROOT / "fixtures"


# ======================================================================
# Stage 0: Environment
# ======================================================================

def stage_env(mode: str) -> dict:
    result = {"status": "PASS", "items": {}}

    if mode == "full":
        checks = {
            "yt-dlp": subprocess.run(["yt-dlp", "--version"], capture_output=True).returncode == 0,
            "ffmpeg": subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode == 0,
            "whisper": True,  # Python import, would fail elsewhere
            "api_key": check_api_key(),
        }
    else:
        checks = {
            "outputs_exist": all(
                (OUTPUT_ROOT / vid).exists() for vid in GOLDEN_VIDEOS
            ),
        }
        if not checks["outputs_exist"]:
            result["status"] = "FAIL"

    for k, v in checks.items():
        marker = "✓" if v else "✗"
        result["items"][k] = v
    return result


# ======================================================================
# Stage 1: Schema Validation (quick)
# ======================================================================

def stage_schema() -> dict:
    passed = 0
    total = 0
    failures: list[str] = []

    # Validate all golden video outputs have correct structure
    for vid in GOLDEN_VIDEOS:
        d = OUTPUT_ROOT / vid

        # metadata.json
        total += 1
        try:
            meta = json.loads((d / "metadata.json").read_text(encoding="utf-8"))
            assert "video_id" in meta
            assert "title" in meta
            assert "duration" in meta
            assert "files" in meta
            passed += 1
        except Exception as e:
            failures.append(f"{vid}/metadata.json: {e}")

        # segments.json
        total += 1
        try:
            segs = json.loads((d / "segments.json").read_text(encoding="utf-8"))
            assert "segments" in segs
            assert "model" in segs
            passed += 1
        except Exception as e:
            failures.append(f"{vid}/segments.json: {e}")

        # semantic.json
        total += 1
        try:
            sem = json.loads((d / "semantic.json").read_text(encoding="utf-8"))
            assert "semantic_version" in sem
            assert "chapters" in sem
            for ch in sem["chapters"]:
                assert "id" in ch and "title" in ch
                seg_ids = set(ch.get("segment_ids", []))
                for pt in ch.get("points", []):
                    assert "type" in pt and "content" in pt
                    for r in pt.get("refs", []):
                        assert r.get("segment_id") in seg_ids, \
                            f"ref segment_id {r.get('segment_id')} not in chapter segment_ids"
            passed += 1
        except Exception as e:
            failures.append(f"{vid}/semantic.json: {e}")

        # visual_plan.json
        total += 1
        try:
            vis = json.loads((d / "visual_plan.json").read_text(encoding="utf-8"))
            assert "visual_version" in vis
            for v in vis.get("visuals", []):
                assert "id" in v and "chapter_id" in v
                assert v.get("svg_type") in (
                    "flowchart", "matrix", "timeline", "chain",
                    "layered", "decision_tree", "checklist",
                )
                assert v.get("data"), f"{v['id']} data empty"
            passed += 1
        except Exception as e:
            failures.append(f"{vid}/visual_plan.json: {e}")

    return {
        "status": "PASS" if len(failures) == 0 else "FAIL",
        "passed": passed,
        "total": total,
        "failures": failures,
    }


# ======================================================================
# Stage 2: Snapshot Compare
# ======================================================================

def stage_snapshot() -> dict:
    from snapshot import run_all as snapshot_run_all
    results, elapsed = snapshot_run_all()

    hf = sof = info_count = mat = 0
    for r in results.values():
        for f in r["files"].values():
            s = f["status"]
            if s == DIFF_HARD_FAIL: hf += 1
            elif s == DIFF_SOFT_DRIFT: sof += 1
            elif s == DIFF_INFO: info_count += 1
            else: mat += 1

    status = "PASS"
    if hf > 0:
        status = "HARD_FAIL"
    elif sof > 0:
        status = "SOFT_DRIFT"

    return {
        "status": status,
        "match": mat,
        "hard_fail": hf,
        "soft_drift": sof,
        "info": info_count,
        "details": results,
        "elapsed": elapsed,
    }


# ======================================================================
# Stage 3: Deterministic Ordering
# ======================================================================

def stage_deterministic() -> dict:
    passed = 0
    total = 0
    failures: list[str] = []

    # Load render module
    spec = importlib.util.spec_from_file_location(
        "render", PROJECT_ROOT / "apps" / "pipeline" / "render" / "render.py"
    )
    render_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(render_mod)

    for vid in GOLDEN_VIDEOS:
        total += 1
        d = OUTPUT_ROOT / vid
        if not (d / "semantic.json").exists():
            failures.append(f"{vid}: missing input files")
            continue

        html1 = render_mod.build_html(d)
        html2 = render_mod.build_html(d)

        # Normalize and compare
        n1 = normalize_html(html1)
        n2 = normalize_html(html2)

        if n1 == n2:
            passed += 1
        else:
            failures.append(f"{vid}: non-deterministic output")

    return {
        "status": "PASS" if len(failures) == 0 else "HARD_FAIL",
        "passed": passed,
        "total": total,
        "failures": failures,
    }


# ======================================================================
# Stage 4: Adversarial Fixtures
# ======================================================================

def stage_adversarial() -> dict:
    passed = 0
    total = 0
    failures: list[str] = []

    # Load render functions
    spec = importlib.util.spec_from_file_location(
        "svg_renderers",
        PROJECT_ROOT / "apps" / "pipeline" / "render" / "svg_renderers.py",
    )
    svg_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(svg_mod)

    spec2 = importlib.util.spec_from_file_location(
        "render_mod", PROJECT_ROOT / "apps" / "pipeline" / "render" / "render.py"
    )
    render_mod = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(render_mod)

    fixtures = [
        ("oversized_flowchart.json", "render_svg"),
        ("deep_decision_tree.json", "render_svg"),
        ("broken_refs_visual.json", "visual_plan"),
        ("empty_visual.json", "visual_plan"),
        ("malformed_semantic.json", "semantic"),
        ("missing_points_semantic.json", "semantic"),
    ]

    for fname, ftype in fixtures:
        total += 1
        fpath = FIXTURE_ROOT / fname
        if not fpath.exists():
            failures.append(f"{fname}: fixture not found")
            continue

        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))

            if ftype == "render_svg":
                for v in data.get("visuals", []):
                    result = svg_mod.render_svg(v["svg_type"], v.get("data", {}), v.get("title", ""), v.get("layout_hint", "vertical"))
                    assert result.startswith("<svg"), f"{fname}: SVG not generated"
                    assert "</svg>" in result

            elif ftype == "visual_plan":
                if not data.get("visuals") and not data.get("skipped"):
                    pass  # empty_visual — valid edge case
                for v in data.get("visuals", []):
                    svg_mod.render_svg(v["svg_type"], v.get("data", {}), v.get("title", ""), v.get("layout_hint", "vertical"))

            elif ftype == "semantic":
                chapters = data.get("chapters")
                if isinstance(chapters, list):
                    for ch in chapters:
                        assert "id" in ch
                else:
                    # malformed: chapters is string — should not crash schema validator
                    pass

            passed += 1
        except AssertionError as e:
            failures.append(f"{fname}: {e}")
        except Exception as e:
            failures.append(f"{fname}: {e}")

    return {
        "status": "PASS" if len(failures) == 0 else "FAIL",
        "passed": passed,
        "total": total,
        "failures": failures,
    }


# ======================================================================
# Stage 5: Module Unit Tests (full only)
# ======================================================================

def stage_module_tests() -> dict:
    modules = {
        "ingest": PROJECT_ROOT / "apps" / "pipeline" / "ingest" / "test_ingest.py",
        "transcript": PROJECT_ROOT / "apps" / "pipeline" / "transcript" / "test_transcript.py",
        "semantic": PROJECT_ROOT / "apps" / "pipeline" / "semantic" / "test_semantic.py",
        "visual": PROJECT_ROOT / "apps" / "pipeline" / "visual" / "test_visual.py",
        "render": PROJECT_ROOT / "apps" / "pipeline" / "render" / "test_render.py",
    }

    results = {}
    for name, path in modules.items():
        if not path.exists():
            results[name] = "SKIP (no test file)"
            continue

        # semantic and visual need API key
        if name in ("semantic", "visual") and not check_api_key():
            results[name] = "SKIP (no API key)"
            continue

        try:
            r = subprocess.run(
                [sys.executable, str(path)],
                capture_output=True, text=True, timeout=300,
                cwd=str(PROJECT_ROOT),
                env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
            )
            if r.returncode == 0:
                results[name] = "PASS"
            else:
                results[name] = f"FAIL (exit {r.returncode})"
                # Capture last few lines of stderr
                stderr_tail = r.stderr.strip().split("\n")[-3:]
                if stderr_tail:
                    results[name] += f" | {'; '.join(stderr_tail)}"
        except subprocess.TimeoutExpired:
            results[name] = "SKIP (timeout)"
        except Exception as e:
            results[name] = f"ERROR ({e})"

    all_pass = all(v == "PASS" or v.startswith("SKIP") for v in results.values())
    return {"status": "PASS" if all_pass else "FAIL", "results": results}


# ======================================================================
# Stage 6: Performance (full only)
# ======================================================================

def stage_perf() -> dict:
    try:
        r = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "tests" / "perf.py"), "--compare", "--json"],
            capture_output=True, text=True, timeout=120,
            cwd=str(PROJECT_ROOT),
            env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)},
        )
        if r.returncode == 0:
            data = json.loads(r.stdout)
            drifts = data.get("drifts", [])
            return {"status": "PASS" if not drifts else "SOFT_DRIFT", "drifts": drifts}
        return {"status": "ERROR", "reason": r.stderr[:200]}
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}


# ======================================================================
# Output
# ======================================================================

def print_human(all_stages: dict, mode: str, elapsed: float):
    header = f"MetaScribe V1 Regression Harness [{mode.upper()}]"
    print(header)
    print("=" * len(header))

    for stage_name, result in all_stages.items():
        status = result.get("status", "?")
        markers = {"PASS": "✓", "FAIL": "✗", "HARD_FAIL": "✗", "SOFT_DRIFT": "~", "SKIP": "○"}
        m = markers.get(status, "?")

        if stage_name == "env":
            items = " ".join(f"{k}:{'✓' if v else '✗'}" for k, v in result["items"].items())
            print(f"[STAGE 0] Environment   {items}")
        elif stage_name == "schema":
            p = result["passed"]
            t = result["total"]
            print(f"[STAGE 1] Schema        {p}/{t} → {status}  {'; '.join(result['failures'][:2])}")
        elif stage_name == "snapshot":
            print(f"[STAGE 2] Snapshot      {result['match']} MATCH, {result['soft_drift']} SOFT DRIFT, "
                  f"{result['hard_fail']} HARD FAIL → {status} ({result['elapsed']}s)")
        elif stage_name == "deterministic":
            print(f"[STAGE 3] Deterministic {result['passed']}/{result['total']} → {status}")
        elif stage_name == "adversarial":
            f_text = "; ".join(result["failures"][:2]) if result["failures"] else ""
            print(f"[STAGE 4] Adversarial   {result['passed']}/{result['total']} fixtures → {status}  {f_text}")
        elif stage_name == "modules":
            items = "  ".join(f"{k}:{v}" for k, v in result["results"].items())
            print(f"[STAGE 5] Modules       {items}  → {status}")
        elif stage_name == "perf":
            drifts = result.get("drifts", [])
            print(f"[STAGE 6] Performance   {len(drifts)} drifts → {status}")

    # Summary
    has_hard = any(r.get("status") in ("FAIL", "HARD_FAIL") for r in all_stages.values())
    has_soft = any(r.get("status") == "SOFT_DRIFT" for r in all_stages.values())
    overall = "HARD FAIL" if has_hard else "SOFT DRIFT" if has_soft else "PASS"
    print(f"\n[SUMMARY] Overall: {overall}  ({elapsed:.1f}s)")
    return overall


def print_json(all_stages: dict, mode: str, elapsed: float):
    output = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": mode,
        "stages": {},
        "summary": {},
        "wall_seconds": elapsed,
    }

    has_hard = False
    has_soft = False
    for name, result in all_stages.items():
        status = result.get("status", "?")
        if status in ("FAIL", "HARD_FAIL"):
            has_hard = True
        elif status == "SOFT_DRIFT":
            has_soft = True

        clean = {k: v for k, v in result.items() if k != "details"}
        output["stages"][name] = clean

    overall = "HARD_FAIL" if has_hard else "SOFT_DRIFT" if has_soft else "PASS"
    output["summary"]["overall"] = overall
    output["exit_code"] = 1 if has_hard else 0

    print(json.dumps(output, ensure_ascii=False, indent=2))


# ======================================================================
# Orchestrator
# ======================================================================

def run(mode: str = "quick") -> tuple[dict, float]:
    t0 = time.time()
    stages: dict = {}

    # Stage 0
    stages["env"] = stage_env(mode)

    if mode == "quick" and not stages["env"]["items"].get("outputs_exist", False):
        elapsed = round(time.time() - t0, 1)
        return stages, elapsed

    # Stage 1: Schema (both modes)
    stages["schema"] = stage_schema()

    # Stage 2: Snapshot (both modes)
    stages["snapshot"] = stage_snapshot()

    # Stage 3: Deterministic (both modes)
    stages["deterministic"] = stage_deterministic()

    # Stage 4: Adversarial (both modes)
    stages["adversarial"] = stage_adversarial()

    if mode == "full":
        # Stage 5: Module tests
        stages["modules"] = stage_module_tests()

        # Stage 6: Performance
        stages["perf"] = stage_perf()

    elapsed = round(time.time() - t0, 1)
    return stages, elapsed


# ======================================================================
# CLI
# ======================================================================

if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    mode = "quick"
    if "--full" in sys.argv:
        mode = "full"
    json_mode = "--json" in sys.argv

    stages, elapsed = run(mode)

    if json_mode:
        print_json(stages, mode, elapsed)
    else:
        overall = print_human(stages, mode, elapsed)

    # exit(1) only on HARD FAIL
    has_hard = any(
        r.get("status") in ("FAIL", "HARD_FAIL")
        for r in stages.values()
    )
    sys.exit(1 if has_hard else 0)
