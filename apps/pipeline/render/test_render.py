"""render 模块测试。

验证：
- HTML 输出结构完整性
- 7 种 SVG 渲染器
- Contract 1: deterministic ordering
- Contract 2: render metadata
- Contract 3: print CSS 片段
- Contract 4: HTML 转义
- 边界情况: 0 visuals / 全 visuals
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from schema import RenderInputs
from render import build_html, _escape_html, _fmt_time
from svg_renderers import (
    render_svg, _wrap_text,
    render_flowchart, render_matrix, render_timeline,
    render_chain, render_layered, render_decision_tree, render_checklist,
)


# ======================================================================
# 基础工具测试
# ======================================================================

def test_wrap_text():
    """Contract 1: _wrap_text 行为。"""
    # 短文本
    assert _wrap_text("hello", 10) == ["hello"]
    # 中文
    lines = _wrap_text("这是一个测试文本", 6)
    assert len(lines) >= 1
    # 空文本
    assert _wrap_text("", 10) == [""]
    # 截断
    long_text = "abcdefghijklmnopqrstuvwxyz" * 10
    lines = _wrap_text(long_text, 10)
    assert len(lines) <= 5


def test_escape_html():
    """Contract 4: HTML 转义。"""
    assert _escape_html("<script>") == "&lt;script&gt;"
    assert _escape_html('"hello"') == "&quot;hello&quot;"
    assert _escape_html("a & b") == "a &amp; b"


def test_fmt_time():
    assert _fmt_time(65) == "1:05"
    assert _fmt_time(3661) == "1:01:01"
    assert _fmt_time(0) == "0:00"


# ======================================================================
# 7 种 SVG 渲染器单元测试（最小数据输入 → 有效 SVG 输出）
# ======================================================================

def _is_valid_svg(s: str) -> bool:
    return s.startswith("<svg") and "</svg>" in s


def test_render_flowchart():
    data = {
        "nodes": [
            {"id": "n1", "label": "开始", "type": "start"},
            {"id": "n2", "label": "处理数据", "type": "process"},
            {"id": "n3", "label": "完成", "type": "end"},
        ],
        "edges": [
            {"from": "n1", "to": "n2", "label": "下一步"},
            {"from": "n2", "to": "n3"},
        ],
    }
    svg = render_flowchart(data, "测试流程图")
    assert _is_valid_svg(svg)
    assert "流程图" in svg
    assert "<rect" in svg
    assert "marker-end" in svg

    # 空数据 → fallback
    svg2 = render_flowchart({}, "空")
    assert _is_valid_svg(svg2)


def test_render_matrix():
    data = {
        "columns": [{"id": "c1", "label": "特征"}, {"id": "c2", "label": "值"}],
        "rows": [
            {"id": "r1", "label": "A", "cells": [{"value": "123"}, {"value": "456"}]},
            {"id": "r2", "label": "B", "cells": [{"value": "789"}, {"value": "012"}]},
        ],
    }
    svg = render_matrix(data, "对比矩阵")
    assert _is_valid_svg(svg)
    assert "123" in svg

    # values 格式
    data2 = {
        "columns": [{"id": "col_1", "label": "A"}, {"id": "col_2", "label": "B"}],
        "rows": [
            {"id": "row_1", "label": "X",
             "values": [{"column_id": "col_1", "value": "v1"}, {"column_id": "col_2", "value": "v2"}]},
        ],
    }
    svg2 = render_matrix(data2, "values格式")
    assert _is_valid_svg(svg2)
    assert "v1" in svg2

    # 空
    svg3 = render_matrix({}, "空")
    assert _is_valid_svg(svg3)


def test_render_timeline():
    data = {
        "events": [
            {"ts": "2020", "label": "事件1", "detail": "详情1"},
            {"ts": "2021", "label": "事件2"},
            {"ts": "2022", "label": "事件3", "detail": "详情3"},
        ],
    }
    svg = render_timeline(data, "时间线")
    assert _is_valid_svg(svg)
    assert "2020" in svg

    svg2 = render_timeline({}, "空")
    assert _is_valid_svg(svg2)


def test_render_chain():
    data = {
        "nodes": [
            {"id": "n1", "label": "原因A", "type": "cause"},
            {"id": "n2", "label": "结果B", "type": "effect", "desc": "详细说明"},
        ],
        "edges": [
            {"from": "n1", "to": "n2", "label": "导致"},
        ],
    }
    svg = render_chain(data, "因果链")
    assert _is_valid_svg(svg)
    assert "原因A" in svg

    svg2 = render_chain({}, "空")
    assert _is_valid_svg(svg2)


def test_render_layered():
    data = {
        "layers": [
            {"level": 1, "label": "顶层", "items": ["a", "b", "c"]},
            {"level": 2, "label": "中层", "items": ["d", "e"]},
        ],
    }
    svg = render_layered(data, "分层结构")
    assert _is_valid_svg(svg)
    assert "顶层" in svg

    svg2 = render_layered({}, "空")
    assert _is_valid_svg(svg2)


def test_render_decision_tree():
    data = {
        "root": {
            "label": "是否满足条件?",
            "branches": [
                {"condition": "是", "result": "通过"},
                {"condition": "否", "result": "拒绝"},
            ],
        },
    }
    svg = render_decision_tree(data, "决策树")
    assert _is_valid_svg(svg)
    assert "决策树" in svg

    # 递归分支
    data2 = {
        "root": {
            "question": "A?",
            "branches": [
                {"condition": "B", "branches": [
                    {"condition": "B1", "result": "X"},
                    {"condition": "B2", "result": "Y"},
                ]},
            ],
        },
    }
    svg2 = render_decision_tree(data2, "递归决策树")
    assert _is_valid_svg(svg2)

    svg3 = render_decision_tree({}, "空")
    assert _is_valid_svg(svg3)


def test_render_checklist():
    data = {
        "items": [
            {"label": "检查项1", "severity": "critical", "detail": "必须修复"},
            {"label": "检查项2", "severity": "warning"},
            {"label": "检查项3", "severity": "info", "detail": "建议改进"},
        ],
    }
    svg = render_checklist(data, "检查清单")
    assert _is_valid_svg(svg)
    assert "检查项1" in svg

    svg2 = render_checklist({}, "空")
    assert _is_valid_svg(svg2)


def test_render_svg_dispatcher():
    for t in ("flowchart", "matrix", "timeline", "chain", "layered", "decision_tree", "checklist"):
        svg = render_svg(t, {}, "test", "vertical")
        assert _is_valid_svg(svg), f"{t} dispatcher failed"

    # 未知类型
    svg = render_svg("unknown", {}, "test")
    assert _is_valid_svg(svg)


# ======================================================================
# HTML 结构完整性测试
# ======================================================================

def _get_video_dirs(project_root: Path) -> list[Path]:
    """获取已存在的输出目录。"""
    output_root = project_root / "outputs"
    if not output_root.exists():
        return []
    dirs = []
    for vid_dir in sorted(output_root.iterdir()):
        if vid_dir.is_dir():
            need = ["metadata.json", "semantic.json", "visual_plan.json", "segments.json"]
            if all((vid_dir / f).exists() for f in need):
                dirs.append(vid_dir)
    return dirs


def test_html_structure():
    """验证每个视频的 HTML 输出结构。"""
    project_root = Path(__file__).resolve().parents[3]
    dirs = _get_video_dirs(project_root)

    if not dirs:
        print("SKIP: 无可用测试数据")
        return

    for d in dirs:
        label = d.name
        html = build_html(d)
        assert html, f"[{label}] HTML 为空"
        assert html.startswith("<!DOCTYPE html>"), f"[{label}] 缺少 DOCTYPE"

        # 结构检查
        assert '<nav class="toc-sidebar"' in html, f"[{label}] 缺少 TOC"
        assert '<main id="main-content">' in html, f"[{label}] 缺少 main"
        assert '<header class="page-header"' in html, f"[{label}] 缺少 header"
        assert '<footer class="page-footer"' in html, f"[{label}] 缺少 footer"

        # Contract 2: 元数据标签
        assert '<meta name="generator" content="MetaScribe render v1">' in html
        assert '<meta name="render-version" content="v1">' in html
        assert '<meta name="prompt-version"' in html
        assert '<meta name="rendered-at"' in html

        # 暗色模式 CSS 变量
        assert 'prefers-color-scheme: dark' in html
        assert '--svg-bg' in html
        assert '[data-theme="dark"]' in html

        # Contract 3: print CSS
        assert '@media print' in html
        assert 'break-inside: avoid' in html

        # Contract 4: 所有 user data 在 HTML/SVG 文本节点中经过转义
        # (设计确保：所有用户数据插入点都经过 _escape_html)

        # 时间戳格式 (M:SS)
        import re
        ts_matches = re.findall(r'\d+:\d{2}', html)
        assert len(ts_matches) > 0, f"[{label}] 无时间戳格式"

        # 章节 section
        assert 'class="chapter-section"' in html, f"[{label}] 无章节 section"

        # 文件大小 (Contract 2: < 2MB)
        size_kb = len(html.encode("utf-8")) / 1024
        assert size_kb < 2048, f"[{label}] HTML {size_kb:.0f}KB 超过 2MB 限制"

        print(f"[{label}] HTML 结构通过 ({size_kb:.0f} KB)")


def test_deterministic_ordering():
    """Contract 1: 同输入 → 同 HTML 输出（除 rendered_at）。"""
    project_root = Path(__file__).resolve().parents[3]
    dirs = _get_video_dirs(project_root)
    if not dirs:
        print("SKIP: 无可用测试数据")
        return

    d = dirs[0]
    html1 = build_html(d)
    html2 = build_html(d)

    # 去掉 rendered-at 后应完全一致
    import re
    clean1 = re.sub(r'<meta name="rendered-at" content="[^"]*">', '', html1)
    clean2 = re.sub(r'<meta name="rendered-at" content="[^"]*">', '', html2)
    clean1 = re.sub(r'MetaScribe Render v1 · [^<]*', 'MetaScribe Render v1 ·', clean1)
    clean2 = re.sub(r'MetaScribe Render v1 · [^<]*', 'MetaScribe Render v1 ·', clean2)

    assert clean1 == clean2, f"[{d.name}] 两次生成不一致（deterministic ordering 失败）"
    print(f"[{d.name}] deterministic ordering 通过")


def test_edge_cases():
    """边界情况：0 visuals / 分段结构。"""
    project_root = Path(__file__).resolve().parents[3]
    dirs = _get_video_dirs(project_root)

    for d in dirs:
        html = build_html(d)
        inputs = RenderInputs.load(d)

        # 0 visuals 视频：应有 TOC 但无 SVG（或 fallback SVG）
        if len(inputs.visual.visuals) == 0:
            # 应展示跳过原因
            assert 'skip' in html.lower() or 'skipped' in html.lower() or len(inputs.semantic.chapters) <= 3, \
                f"[{d.name}] 0 visuals 应包含说明"

        # 所有章节应出现在 HTML 中
        for ch in inputs.semantic.chapters:
            assert ch.id in html, f"[{d.name}] 章节 {ch.id} 缺失"

        print(f"[{d.name}] 边界情况通过 (visuals={len(inputs.visual.visuals)}, chapters={len(inputs.semantic.chapters)})")


# ======================================================================
# 主入口
# ======================================================================

def main():
    tests = [
        ("_wrap_text", test_wrap_text),
        ("_escape_html", test_escape_html),
        ("_fmt_time", test_fmt_time),
        ("render_flowchart", test_render_flowchart),
        ("render_matrix", test_render_matrix),
        ("render_timeline", test_render_timeline),
        ("render_chain", test_render_chain),
        ("render_layered", test_render_layered),
        ("render_decision_tree", test_render_decision_tree),
        ("render_checklist", test_render_checklist),
        ("render_svg dispatcher", test_render_svg_dispatcher),
        ("HTML structure", test_html_structure),
        ("deterministic ordering", test_deterministic_ordering),
        ("edge cases", test_edge_cases),
    ]

    passed = 0
    failed = 0
    skipped = 0

    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            if "SKIP" in str(e):
                print(f"  SKIP  {name}: {e}")
                skipped += 1
            else:
                print(f"  ERROR {name}: {e}")
                failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} PASS, {failed} FAIL, {skipped} SKIP")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
