"""semantic 模块 —— 信息理解与结构化。

输入：outputs/{video_id}/metadata.json + segments.json
输出：outputs/{video_id}/semantic.json

技术：LLM (via provider 抽象层，支持 Anthropic-compatible / DeepSeek / Qwen 等)
目录：apps/pipeline/semantic/

环境变量：
  ANTHROPIC_BASE_URL     — API endpoint (默认 https://api.anthropic.com)
  ANTHROPIC_AUTH_TOKEN   — API key / auth token
  ANTHROPIC_MODEL        — 默认 model name
"""

import json
import re
import sys
from pathlib import Path
from typing import Optional

from schema import Semantic, Chapter, InfoPoint, SegmentRef
from prompts import get_prompt, LATEST
from provider import LLMProvider, LLMConfig


def _parse_json_strict(raw: str, label: str) -> dict:
    """解析 LLM 输出的 JSON，带容错。

    尝试顺序：
    1. 直接解析
    2. 提取 ```json ... ``` 代码块后解析
    3. 提取 { ... } 最外层后解析
    """
    attempts: list[str] = [raw]

    # 尝试提取 markdown 代码块
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        attempts.append(m.group(1).strip())

    # 尝试提取最外层 { ... }
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        attempts.append(m.group(0).strip())

    for i, text in enumerate(attempts):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            if i == len(attempts) - 1:
                raise RuntimeError(f"[{label}] JSON 解析失败，已尝试 {len(attempts)} 种策略")
            continue

    raise RuntimeError(f"[{label}] JSON 解析失败")


def _format_segments(segments: list[dict], start_idx: int, end_idx: int) -> str:
    """将 segment 范围格式化为 LLM 输入文本。"""
    lines = []
    for i in range(start_idx, min(end_idx + 1, len(segments))):
        s = segments[i]
        lines.append(f"[id:{s['id']}] ts:{s['start']:.1f}-{s['end']:.1f} text:{s['text']}")
    return "\n".join(lines)


def _format_all_segments(segments: list[dict]) -> str:
    """将所有 segments 格式化为 LLM 输入文本（用于章节检测）。"""
    return _format_segments(segments, 0, len(segments) - 1)


def _detect_chapters_with_llm(
    segments: list[dict],
    llm: LLMProvider,
    prompt_version: str,
) -> list[dict]:
    """使用 LLM 检测章节边界。返回章节列表。"""
    system_prompt = get_prompt(prompt_version, "system")
    detect_prompt = get_prompt(prompt_version, "chapter_detect")
    segments_text = _format_all_segments(segments)

    user_message = detect_prompt.format(segments_text=segments_text)

    raw = llm.complete(
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        max_tokens=4096,
    )

    chapters = _parse_json_strict(raw, "chapter_detect")
    return chapters


def _extract_points_for_chapter(
    chapter_title: str,
    start_ts: float,
    end_ts: float,
    segments: list[dict],
    first_seg_id: int,
    last_seg_id: int,
    llm: LLMProvider,
    prompt_version: str,
) -> tuple[list[InfoPoint], list[str]]:
    """对单个章节执行信息点提取。返回 (points, warnings)。"""
    system_prompt = get_prompt(prompt_version, "system")
    extract_prompt = get_prompt(prompt_version, "extract")
    segments_text = _format_segments(segments, first_seg_id, last_seg_id)

    user_message = extract_prompt.format(
        chapter_title=chapter_title,
        start_ts=start_ts,
        end_ts=end_ts,
        segments_text=segments_text,
    )

    raw = llm.complete(
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        max_tokens=16384,
    )

    result = _parse_json_strict(raw, f"extract:{chapter_title}")

    points = []
    warnings = []

    for p in result.get("points", []):
        refs = []
        for r in p.get("refs", []):
            sid = r["segment_id"]
            seg = next((s for s in segments if s["id"] == sid), None)
            ts = seg["start"] if seg else 0.0
            refs.append(SegmentRef(
                segment_id=sid,
                ts=ts,
                quote=r["quote"][:40],
            ))

        confidence = p.get("confidence", 0.5)

        if confidence < 0.5:
            warnings.append(
                f"[{chapter_title}] type={p['type']} confidence={confidence:.2f} — "
                f"低置信度提取: {p['content'][:60]}"
            )

        points.append(InfoPoint(
            type=p["type"],
            content=p["content"],
            refs=refs,
            confidence=confidence,
        ))

    return points, warnings


def _build_chapters_from_metadata(
    metadata: dict,
    llm: LLMProvider,
    prompt_version: str,
    segments: list[dict],
) -> list[Chapter]:
    """基于 ingest 的原生章节构建 Chapter 对象。"""
    chapters = []
    meta_chapters = metadata.get("chapters", [])

    if not meta_chapters:
        # 无原生章节，使用 LLM 检测
        llm_chapters = _detect_chapters_with_llm(segments, llm, prompt_version)
        for ch in llm_chapters:
            first = ch["first_segment_id"]
            last = ch["last_segment_id"]
            chapters.append(Chapter(
                id=ch["id"],
                title=ch["title"],
                start_ts=segments[first]["start"],
                end_ts=segments[last]["end"],
                segment_ids=list(range(first, last + 1)),
                points=[],
            ))
        return chapters

    # 将原生章节映射到 segment 范围
    for i, mc in enumerate(meta_chapters):
        ch_start = mc["start"]
        ch_end = mc["end"]

        seg_ids = [
            s["id"] for s in segments
            if s["start"] >= ch_start - 0.5 and s["start"] < ch_end
        ]

        if not seg_ids:
            continue

        chapters.append(Chapter(
            id=f"ch{i+1:02d}",
            title=mc["title"] if mc["title"] else f"章节 {i+1}",
            start_ts=ch_start,
            end_ts=ch_end,
            segment_ids=seg_ids,
            points=[],
        ))

    return chapters


def build_semantic(
    metadata_path: Path,
    prompt_version: str = LATEST,
    model: Optional[str] = None,
) -> Semantic:
    """主流程：读取 ingest+transcript 输出 → LLM 结构化 → semantic.json。"""
    config = LLMConfig.from_env(model=model)
    llm = LLMProvider(config)
    print(f"[INFO] provider={config.provider}, base_url={config.base_url}, model={config.model}")

    # 1. 读取输入
    with open(metadata_path, encoding="utf-8") as f:
        metadata = json.load(f)

    output_dir = metadata_path.parent
    video_id = metadata["video_id"]

    segments_path = output_dir / "segments.json"
    if not segments_path.exists():
        raise FileNotFoundError(f"segments.json 不存在: {segments_path}")

    with open(segments_path, encoding="utf-8") as f:
        transcript = json.load(f)

    segments = transcript["segments"]

    # 兼容旧 transcript 输出（无 id 字段时用 index 合成）
    for i, s in enumerate(segments):
        if "id" not in s:
            s["id"] = i

    # 2. 构建章节结构
    chapters = _build_chapters_from_metadata(
        metadata, llm, prompt_version, segments,
    )

    # 3. 逐章节提取信息点
    all_warnings = []
    total_points = 0

    for chapter in chapters:
        if not chapter.segment_ids:
            all_warnings.append(f"[{chapter.id}] 无对应 segment，跳过提取")
            continue

        first_seg = chapter.segment_ids[0]
        last_seg = chapter.segment_ids[-1]

        print(f"[INFO] 提取章节: {chapter.id} \"{chapter.title}\" "
              f"(segments {first_seg}-{last_seg})")

        try:
            points, warnings = _extract_points_for_chapter(
                chapter_title=chapter.title,
                start_ts=chapter.start_ts,
                end_ts=chapter.end_ts,
                segments=segments,
                first_seg_id=first_seg,
                last_seg_id=last_seg,
                llm=llm,
                prompt_version=prompt_version,
            )
            chapter.points = points
            all_warnings.extend(warnings)
            total_points += len(points)

        except Exception as e:
            all_warnings.append(f"[{chapter.id}] 提取失败: {e}")

    # 4. 统计
    type_dist = {}
    for ch in chapters:
        for p in ch.points:
            type_dist[p.type] = type_dist.get(p.type, 0) + 1

    stats = {
        "chapter_count": len(chapters),
        "total_points": total_points,
        "type_distribution": type_dist,
        "avg_points_per_chapter": round(total_points / len(chapters), 1) if chapters else 0,
    }

    # 5. 全局 warnings
    if total_points == 0:
        all_warnings.append("全视频无信息点提取")
    empty_chapters = [ch.id for ch in chapters if not ch.points]
    if empty_chapters:
        all_warnings.append(f"以下章节无信息点: {empty_chapters}")

    semantic = Semantic(
        semantic_version="v1",
        prompt_version=prompt_version,
        video_id=video_id,
        chapters=chapters,
        stats=stats,
        warnings=all_warnings,
    )

    # 6. 输出
    semantic.to_json(output_dir / "semantic.json")
    return semantic


def run_semantic(
    video_id: str,
    project_root: str | Path,
    prompt_version: str = LATEST,
    model: Optional[str] = None,
) -> dict:
    """便捷入口：给定 video_id，自动找到输入文件并执行语义分析。"""
    root = Path(project_root)
    meta_path = root / "outputs" / video_id / "metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"metadata.json 不存在: {meta_path}")
    semantic = build_semantic(meta_path, prompt_version=prompt_version, model=model)
    return semantic.to_dict()


# ---- CLI ----
if __name__ == "__main__":
    # Windows console UTF-8
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    if len(sys.argv) < 2:
        print("用法: python semantic.py <video_id> [project_root] [model]", file=sys.stderr)
        print("示例: python semantic.py jNQXAC9IVRw", file=sys.stderr)
        print("示例: python semantic.py BV1Js596dEnT . deepseek-v4-pro", file=sys.stderr)
        sys.exit(1)

    vid = sys.argv[1]
    root = sys.argv[2] if len(sys.argv) > 2 else "."
    model = sys.argv[3] if len(sys.argv) > 3 else None

    try:
        result = run_semantic(vid, root, model=model)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"SEMANTIC FAILED: {e}", file=sys.stderr)
        sys.exit(1)
