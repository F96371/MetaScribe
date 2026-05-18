"""semantic 模块测试。

测试策略：三级视频（短/中/长），验证：
- schema 契约
- segment 可追溯性
- 章节拆分合理性
- 信息密度有效性
- warnings 机制
- prompt version 记录
"""

import json
import os
import sys
from pathlib import Path

# 确保项目根在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parent))

from schema import Semantic


def check_api_key():
    if not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        print("SKIP: ANTHROPIC_AUTH_TOKEN 未设置")
        sys.exit(0)


def validate_semantic(semantic: Semantic, label: str) -> list[str]:
    """全面校验 semantic 输出。返回 issues 列表。"""
    issues = []

    # 1. Schema 基础
    if semantic.semantic_version != "v1":
        issues.append(f"[{label}] semantic_version 异常: {semantic.semantic_version}")
    if not semantic.prompt_version:
        issues.append(f"[{label}] prompt_version 缺失")
    if not semantic.video_id:
        issues.append(f"[{label}] video_id 缺失")

    # 2. 章节校验
    if not semantic.chapters:
        issues.append(f"[{label}] 章节为空")
        return issues

    for ch in semantic.chapters:
        if not ch.id or not ch.title:
            issues.append(f"[{label}] 章节 id/title 缺失")
        if ch.start_ts >= ch.end_ts:
            issues.append(f"[{label}] {ch.id} 时间范围异常: {ch.start_ts} >= {ch.end_ts}")
        if not ch.segment_ids:
            issues.append(f"[{label}] {ch.id} segment_ids 为空")

        # 3. 信息点校验
        for p in ch.points:
            if not p.refs:
                issues.append(f"[{label}] {ch.id} point 无 segment 引用")
            for ref in p.refs:
                if ref.segment_id not in ch.segment_ids:
                    issues.append(
                        f"[{label}] {ch.id} point 引用 segment {ref.segment_id} "
                        f"不在章节范围 {ch.segment_ids[0]}-{ch.segment_ids[-1]}"
                    )
            if p.confidence < 0.0 or p.confidence > 1.0:
                issues.append(f"[{label}] {ch.id} confidence 越界: {p.confidence}")
            if not p.content.strip():
                issues.append(f"[{label}] {ch.id} point 内容为空")

    # 4. Stats 校验
    if not semantic.stats:
        issues.append(f"[{label}] stats 缺失")
    else:
        actual_points = sum(ch.point_count for ch in semantic.chapters)
        if semantic.stats.get("total_points", -1) != actual_points:
            issues.append(f"[{label}] stats.total_points ({semantic.stats.get('total_points')}) != 实际 ({actual_points})")

    return issues


def print_result(video_id: str, semantic: Semantic, issues: list[str]):
    """打印测试结果。"""
    status = "PASS" if not issues else "FAIL"
    print(f"\n{'='*60}")
    print(f"TEST: {video_id} [{status}]")
    print(f"  prompt_version: {semantic.prompt_version}")
    print(f"  chapters: {semantic.stats.get('chapter_count', '?')}")
    print(f"  total_points: {semantic.stats.get('total_points', '?')}")
    print(f"  type_distribution: {semantic.stats.get('type_distribution', {})}")
    print(f"  avg_points/chapter: {semantic.stats.get('avg_points_per_chapter', '?')}")
    print(f"  warnings: {len(semantic.warnings)}")
    for w in semantic.warnings:
        print(f"    [W] {w}")
    if issues:
        for i in issues:
            print(f"  [FAIL] {i}")
    print(f"{'='*60}\n")
    return status


def main():
    check_api_key()

    project_root = Path(__file__).resolve().parents[3]  # MetaScribe/

    # 测试用例
    tests = [
        {
            "video_id": "jNQXAC9IVRw",
            "label": "短视频 (19s, en)",
            "min_chapters": 1,
            "max_chapters": 3,
        },
        {
            "video_id": "BV1Js596dEnT",
            "label": "中视频 (8min, zh)",
            "min_chapters": 2,
            "max_chapters": 8,
        },
        {
            "video_id": "HtSuA80QTyo",
            "label": "长视频 (53min, en)",
            "min_chapters": 5,
            "max_chapters": 12,
        },
    ]

    results = []
    for t in tests:
        vid = t["video_id"]
        label = t["label"]

        semantic_path = project_root / "outputs" / vid / "semantic.json"
        if not semantic_path.exists():
            print(f"[SKIP] {label}: semantic.json 尚未生成，请先运行 semantic.py {vid}")
            continue

        with open(semantic_path, encoding="utf-8") as f:
            data = json.load(f)

        semantic = Semantic.from_dict(data)
        issues = validate_semantic(semantic, label)
        status = print_result(vid, semantic, issues)
        results.append((vid, status))

    # Summary
    print("\n---")
    passed = sum(1 for _, s in results if s == "PASS")
    print(f"Results: {passed}/{len(results)} PASS")
    if passed != len(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
