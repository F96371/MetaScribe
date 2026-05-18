"""visual 模块 —— 可视化决策与规划。

输入：outputs/{video_id}/metadata.json + semantic.json
输出：outputs/{video_id}/visual_plan.json

职责：判断是否需要 SVG → 选择类型 → 生成可视化数据集 → 不 render。
目录：apps/pipeline/visual/
"""

import importlib.util
import json
import re
import sys
import io
from pathlib import Path
from typing import Optional

from schema import VisualPlan, VisualSpec, SegmentRef
from taxonomy import route, get_data_template, type_info


def _parse_json_robust(raw: str, label: str) -> dict:
    """解析 LLM 输出的 JSON，带容错。"""
    if not raw.strip():
        raise RuntimeError(f"[{label}] LLM 返回空响应")

    attempts: list[str] = [raw]
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        attempts.append(m.group(1).strip())
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        attempts.append(m.group(0).strip())

    for i, text in enumerate(attempts):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            if i == len(attempts) - 1:
                raise RuntimeError(f"[{label}] JSON 解析失败（已尝试 {len(attempts)} 种策略）")
            continue

    raise RuntimeError(f"[{label}] JSON 解析失败")

# 复用 semantic 模块的 provider（避免 sys.path 污染本地 schema 导入）
_sem_provider = Path(__file__).resolve().parents[1] / "semantic" / "provider.py"
_spec = importlib.util.spec_from_file_location("semantic_provider", _sem_provider)
_sem_provider_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sem_provider_mod)
LLMProvider = _sem_provider_mod.LLMProvider
LLMConfig = _sem_provider_mod.LLMConfig


# ---------------------------------------------------------------------------
# LLM prompt — 可视化数据生成
# ---------------------------------------------------------------------------

VISUAL_SYSTEM = """\
你是一个可视化数据分析师。你的任务是基于视频章节的信息点，生成一个 SVG 图表的结构化数据。

核心原则：
- 数据必须来自原文信息点，不凭空编造
- 每个数据元素必须引用 segment_id
- 图表标题具体而非空洞（不要用「本章总结」「内容概览」等）
- 数据简洁，避免冗余——图表不是文章"""

VISUAL_DATA_PROMPT = """\
章节: {chapter_title}
选定的图表类型: {svg_type}（{svg_label}）
类型说明: {svg_desc}

该章节的信息点如下:
{points_text}

请为这个章节生成 {svg_type} 的数据结构。

数据模板:
{data_template}

填充规则:
1. 从信息点中提取具体内容填入模板
2. 每个数据节点引用至少一个 segment_id
3. 标题 ≤20 字，具体而非空洞
4. 节点/项数量由内容决定，不要硬凑

输出严格 JSON（不要 markdown 代码块）:
{{
  "title": "图表标题",
  "data": <按模板填充的数据对象>,
  "refs": [
    {{"segment_id": N, "ts": 0.0, "quote": "原文关键短句"}}
  ]
}}
"""


def _format_points(points: list[dict]) -> str:
    """将 semantic info points 格式化为 LLM 输入。"""
    lines = []
    for p in points:
        refs_str = ", ".join(
            f"seg={r['segment_id']}@{r['ts']:.0f}s"
            for r in p.get("refs", [])[:3]
        )
        lines.append(f"[{p['type']}] {p['content']}  (refs: {refs_str})")
    return "\n".join(lines)


def _generate_visual_data(
    chapter: dict,
    svg_type: str,
    llm: LLMProvider,
) -> tuple[str, dict, list[SegmentRef], float]:
    """用 LLM 对单个章节生成可视化数据。返回 (title, data, refs, confidence)。"""
    info = type_info(svg_type)
    template = get_data_template(svg_type)
    points_text = _format_points(chapter.get("points", []))
    data_template_str = json.dumps(template, ensure_ascii=False, indent=2)

    user_message = VISUAL_DATA_PROMPT.format(
        chapter_title=chapter["title"],
        svg_type=svg_type,
        svg_label=info.get("label", svg_type),
        svg_desc=info.get("description", ""),
        points_text=points_text,
        data_template=data_template_str,
    )

    raw = llm.complete(
        system=VISUAL_SYSTEM,
        messages=[{"role": "user", "content": user_message}],
        max_tokens=4096,
    )

    # 空响应重试一次
    if not raw.strip():
        raw = llm.complete(
            system=VISUAL_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=4096,
        )

    result = _parse_json_robust(raw, f"visual:{chapter['title']}")
    title = result.get("title", chapter["title"])
    data = result.get("data", {})
    confidence = result.get("confidence", 0.5)
    refs = [
        SegmentRef(
            segment_id=r["segment_id"],
            ts=r.get("ts", 0.0),
            quote=r.get("quote", "")[:40],
        )
        for r in result.get("refs", [])
    ]
    return title, data, refs, confidence


def build_visual_plan(
    semantic_path: Path,
    model: Optional[str] = None,
) -> VisualPlan:
    """主流程：读取 semantic.json → 路由 → LLM 生成数据 → visual_plan.json。"""
    config = LLMConfig.from_env(model=model)
    llm = LLMProvider(config)
    print(f"[INFO] provider={config.provider}, base_url={config.base_url}, model={config.model}")

    # 1. 读取输入
    with open(semantic_path, encoding="utf-8") as f:
        semantic = json.load(f)

    output_dir = semantic_path.parent
    video_id = semantic["video_id"]
    chapters = semantic["chapters"]

    # 2. 逐章节路由 + 数据生成
    visuals = []
    skipped = []
    all_warnings = []

    for i, ch in enumerate(chapters):
        ch_id = ch["id"]
        ch_title = ch["title"]

        decision = route(ch)
        if decision is None:
            skipped.append({
                "chapter_id": ch_id,
                "reason": f"信息点不足或类型不匹配（共 {len(ch.get('points', []))} 个点）",
            })
            continue

        svg_type = decision["svg_type"]
        confidence = decision["confidence"]
        rationale = decision["rationale"]

        print(f"[INFO] {ch_id} \"{ch_title}\" → {svg_type} (confidence={confidence:.2f})")

        try:
            vis_title, data, refs, gen_conf = _generate_visual_data(ch, svg_type, llm)
        except Exception as e:
            all_warnings.append(f"[{ch_id}] 可视化数据生成失败: {e}")
            skipped.append({"chapter_id": ch_id, "reason": f"LLM 填充失败: {e}"})
            continue

        if gen_conf < 0.5:
            all_warnings.append(
                f"[{ch_id}] {svg_type} 数据生成置信度偏低 ({gen_conf:.2f})"
            )

        # 触发的 point type 组合
        trigger_types = list(set(p["type"] for p in ch.get("points", [])))

        visuals.append(VisualSpec(
            id=f"vis{i+1:02d}",
            chapter_id=ch_id,
            svg_type=svg_type,
            title=vis_title,
            rationale=rationale,
            trigger_points=trigger_types,
            data=data,
            semantic_refs=refs,
            layout_hint=type_info(svg_type).get("layout_hint", "vertical"),
            confidence=round(gen_conf, 2),
        ))

    # 3. 统计
    type_dist = {}
    for v in visuals:
        type_dist[v.svg_type] = type_dist.get(v.svg_type, 0) + 1

    stats = {
        "total_chapters": len(chapters),
        "total_visuals": len(visuals),
        "skipped_count": len(skipped),
        "type_distribution": type_dist,
        "coverage": round(len(visuals) / len(chapters), 2) if chapters else 0,
    }

    # 4. 全局 warnings
    if not visuals:
        all_warnings.append("全视频无可视化生成")

    plan = VisualPlan(
        visual_version="v1",
        video_id=video_id,
        visuals=visuals,
        skipped=skipped,
        stats=stats,
        warnings=all_warnings,
    )

    # 5. 输出
    plan.to_json(output_dir / "visual_plan.json")
    return plan


def run_visual(
    video_id: str,
    project_root: str | Path,
    model: Optional[str] = None,
) -> dict:
    """便捷入口：给定 video_id，自动找到 semantic.json 并执行可视化规划。"""
    root = Path(project_root)
    sem_path = root / "outputs" / video_id / "semantic.json"
    if not sem_path.exists():
        raise FileNotFoundError(f"semantic.json 不存在: {sem_path}")
    plan = build_visual_plan(sem_path, model=model)
    return plan.to_dict()


# ---- CLI ----
if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    if len(sys.argv) < 2:
        print("用法: python visual.py <video_id> [project_root] [model]", file=sys.stderr)
        print("示例: python visual.py jNQXAC9IVRw", file=sys.stderr)
        print("示例: python visual.py BV1Js596dEnT . deepseek-v4-pro", file=sys.stderr)
        sys.exit(1)

    vid = sys.argv[1]
    root = sys.argv[2] if len(sys.argv) > 2 else "."
    model = sys.argv[3] if len(sys.argv) > 3 else None

    try:
        result = run_visual(vid, root, model=model)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"VISUAL FAILED: {e}", file=sys.stderr)
        sys.exit(1)
