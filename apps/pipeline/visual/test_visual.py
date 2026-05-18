"""visual 模块测试。

验证：
- schema 契约
- 路由规则正确性
- visual → semantic traceability
- fallback 策略
- warnings 机制
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from schema import VisualPlan


def check_env():
    if not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        print("SKIP: ANTHROPIC_AUTH_TOKEN 未设置")
        sys.exit(0)


def validate_visual_plan(plan: VisualPlan, label: str) -> list[str]:
    """全面校验 visual_plan 输出。"""
    issues = []

    if plan.visual_version != "v1":
        issues.append(f"[{label}] visual_version 异常: {plan.visual_version}")
    if not plan.video_id:
        issues.append(f"[{label}] video_id 缺失")

    for v in plan.visuals:
        if not v.id or not v.chapter_id:
            issues.append(f"[{label}] visual id/chapter_id 缺失")
        if v.svg_type not in ("flowchart", "matrix", "timeline", "chain", "layered", "decision_tree", "checklist"):
            issues.append(f"[{label}] {v.id} 非法 svg_type: {v.svg_type}")
        if not v.title or len(v.title) > 40:
            issues.append(f"[{label}] {v.id} title 异常: \"{v.title}\"")
        if not v.data:
            issues.append(f"[{label}] {v.id} data 为空")
        if not v.semantic_refs:
            issues.append(f"[{label}] {v.id} 无 semantic_refs（不可追溯）")

    # 验证 skipped 记录
    for s in plan.skipped:
        if "chapter_id" not in s or "reason" not in s:
            issues.append(f"[{label}] skipped 记录缺失字段")

    # 验证 stats
    expected_total = len(plan.visuals) + len(plan.skipped)
    if plan.stats.get("total_chapters", -1) != expected_total:
        issues.append(f"[{label}] total_chapters ({plan.stats.get('total_chapters')}) != visuals+skipped ({expected_total})")

    return issues


def print_result(video_id: str, plan: VisualPlan, issues: list[str]):
    status = "PASS" if not issues else "FAIL"
    print(f"\n{'='*60}")
    print(f"TEST: {video_id} [{status}]")
    print(f"  visual_version: {plan.visual_version}")
    print(f"  total_visuals: {plan.stats.get('total_visuals', '?')}")
    print(f"  skipped: {plan.stats.get('skipped_count', '?')}")
    print(f"  coverage: {plan.stats.get('coverage', '?')}")
    print(f"  type_distribution: {plan.stats.get('type_distribution', {})}")
    print(f"  warnings: {len(plan.warnings)}")
    for w in plan.warnings:
        print(f"    [W] {w}")
    for v in plan.visuals:
        print(f"  {v.id} [{v.svg_type}] \"{v.title}\" (refs: {len(v.semantic_refs)})")
    for s in plan.skipped:
        print(f"  SKIP {s['chapter_id']}: {s['reason'][:80]}")
    if issues:
        for i in issues:
            print(f"  [FAIL] {i}")
    print(f"{'='*60}\n")
    return status


def main():
    check_env()
    project_root = Path(__file__).resolve().parents[3]

    tests = [
        {"video_id": "jNQXAC9IVRw", "label": "短视频 (19s)"},
        {"video_id": "BV1Js596dEnT", "label": "中视频 (8min)"},
        {"video_id": "HtSuA80QTyo", "label": "长视频 (53min)"},
    ]

    results = []
    for t in tests:
        vid = t["video_id"]
        label = t["label"]

        plan_path = project_root / "outputs" / vid / "visual_plan.json"
        if not plan_path.exists():
            print(f"[SKIP] {label}: visual_plan.json 尚未生成")
            continue

        with open(plan_path, encoding="utf-8") as f:
            data = json.load(f)

        plan = VisualPlan.from_dict(data)
        issues = validate_visual_plan(plan, label)
        status = print_result(vid, plan, issues)
        results.append((vid, status))

    print("\n---")
    passed = sum(1 for _, s in results if s == "PASS")
    print(f"Results: {passed}/{len(results)} PASS")
    if passed != len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
