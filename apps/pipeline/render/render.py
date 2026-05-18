"""render 模块 —— HTML 文档生成器。

输入：outputs/{video_id}/metadata.json + semantic.json + visual_plan.json + segments.json
输出：outputs/{video_id}/index.html

单文件离线 HTML，内联 CSS + SVG，无外部依赖。
"""

from __future__ import annotations

import json
import sys
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from schema import RenderInputs, Segment
from svg_renderers import render_svg


# ======================================================================
# 工具函数
# ======================================================================

def _escape_html(text: str) -> str:
    """统一 HTML/SVG 安全转义 (Contract 4)。"""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


def _fmt_time(seconds: float) -> str:
    """秒数 → H:MM:SS 或 M:SS。"""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _point_type_class(ptype: str) -> str:
    """信息点类型 → CSS class。"""
    return {
        "problem": "type-problem",
        "step": "type-step",
        "pitfall": "type-pitfall",
        "conclusion": "type-conclusion",
        "context": "type-context",
    }.get(ptype, "type-context")


def _point_type_label(ptype: str) -> str:
    """信息点类型 → 中文标签。"""
    return {
        "problem": "问题",
        "step": "步骤",
        "pitfall": "陷阱",
        "conclusion": "结论",
        "context": "背景",
    }.get(ptype, ptype)


# ======================================================================
# CSS (~200 lines)
# ======================================================================

def _build_css() -> str:
    return """/* MetaScribe Render v1 — 内联样式 */
:root {
  /* 亮色主题 */
  --bg: #ffffff;
  --bg-secondary: #f8fafc;
  --bg-card: #ffffff;
  --text: #1e293b;
  --text-secondary: #64748b;
  --text-muted: #94a3b8;
  --border: #e2e8f0;
  --accent: #3b82f6;
  --accent-hover: #2563eb;
  --shadow: 0 1px 3px rgba(0,0,0,.08);
  --shadow-md: 0 4px 12px rgba(0,0,0,.1);

  /* 语义类型颜色 */
  --color-problem: #ef4444;
  --color-step: #3b82f6;
  --color-pitfall: #f59e0b;
  --color-conclusion: #10b981;
  --color-context: #8b5cf6;

  --color-problem-bg: #fef2f2;
  --color-step-bg: #eff6ff;
  --color-pitfall-bg: #fffbeb;
  --color-conclusion-bg: #ecfdf5;
  --color-context-bg: #f5f3ff;

  /* SVG 变量（继承到 inline SVG） */
  --svg-bg: #ffffff;
  --svg-stroke: #cbd5e1;
  --svg-text: #334155;
  --svg-text-secondary: #94a3b8;
  --svg-node-fill: #f1f5f9;
  --svg-node-start: #dbeafe;
  --svg-node-end: #d1fae5;
  --svg-node-decision: #fef3c7;
  --svg-node-cause: #fee2e2;
  --svg-node-effect: #dbeafe;
  --svg-accent: #3b82f6;
  --svg-critical: #ef4444;
  --svg-warning: #f59e0b;
  --svg-info: #3b82f6;

  --font-mono: "Cascadia Code", "Fira Code", "JetBrains Mono", Consolas, monospace;
  --radius: 8px;
  --max-width: 1100px;
  --sidebar-width: 260px;
}

[data-theme="dark"] {
  --bg: #0f172a;
  --bg-secondary: #1e293b;
  --bg-card: #1e293b;
  --text: #e2e8f0;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --border: #334155;
  --accent: #60a5fa;
  --accent-hover: #93bbfd;
  --shadow: 0 1px 3px rgba(0,0,0,.4);
  --shadow-md: 0 4px 12px rgba(0,0,0,.5);

  --color-problem-bg: #3b1212;
  --color-step-bg: #0f1d3d;
  --color-pitfall-bg: #3d2e0a;
  --color-conclusion-bg: #0a2e1f;
  --color-context-bg: #1a1035;

  --svg-bg: #1e293b;
  --svg-stroke: #475569;
  --svg-text: #e2e8f0;
  --svg-text-secondary: #94a3b8;
  --svg-node-fill: #334155;
  --svg-node-start: #1e3a5f;
  --svg-node-end: #144d33;
  --svg-node-decision: #4a3510;
  --svg-node-cause: #4a2020;
  --svg-node-effect: #1e3a5f;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0f172a;
    --bg-secondary: #1e293b;
    --bg-card: #1e293b;
    --text: #e2e8f0;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --border: #334155;
    --accent: #60a5fa;
    --accent-hover: #93bbfd;
    --shadow: 0 1px 3px rgba(0,0,0,.4);
    --shadow-md: 0 4px 12px rgba(0,0,0,.5);
    --color-problem-bg: #3b1212;
    --color-step-bg: #0f1d3d;
    --color-pitfall-bg: #3d2e0a;
    --color-conclusion-bg: #0a2e1f;
    --color-context-bg: #1a1035;
    --svg-bg: #1e293b;
    --svg-stroke: #475569;
    --svg-text: #e2e8f0;
    --svg-text-secondary: #94a3b8;
    --svg-node-fill: #334155;
    --svg-node-start: #1e3a5f;
    --svg-node-end: #144d33;
    --svg-node-decision: #4a3510;
    --svg-node-cause: #4a2020;
    --svg-node-effect: #1e3a5f;
  }
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif;
  font-size: 15px;
  line-height: 1.6;
  color: var(--text);
  background: var(--bg);
  -webkit-font-smoothing: antialiased;
}

.skip-link {
  position: absolute; top: -100px; left: 8px;
  background: var(--accent); color: #fff; padding: 4px 12px; border-radius: var(--radius);
  z-index: 1000; text-decoration: none; font-size: 13px;
}
.skip-link:focus { top: 8px; }

/* ---- header ---- */
.page-header {
  background: var(--bg-secondary); border-bottom: 1px solid var(--border);
  padding: 20px 24px; position: sticky; top: 0; z-index: 100;
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 12px;
}
.page-header h1 {
  font-size: 18px; font-weight: 700; color: var(--text);
  max-width: 600px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.header-meta { font-size: 12px; color: var(--text-secondary); display: flex; gap: 16px; flex-wrap: wrap; align-items: center; }
.header-meta span { white-space: nowrap; }

.theme-toggle {
  background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 6px 12px; font-size: 13px; cursor: pointer; color: var(--text);
  white-space: nowrap;
}
.theme-toggle:hover { border-color: var(--accent); }

/* ---- page layout ---- */
.page-layout { display: flex; max-width: var(--max-width); margin: 0 auto; }

/* ---- TOC sidebar ---- */
.toc-sidebar {
  width: var(--sidebar-width); flex-shrink: 0; position: sticky; top: 80px;
  max-height: calc(100vh - 96px); overflow-y: auto; padding: 20px 16px;
  border-right: 1px solid var(--border); background: var(--bg-secondary);
  font-size: 13px;
}
.toc-title { font-size: 12px; font-weight: 600; text-transform: uppercase; color: var(--text-muted); margin-bottom: 12px; letter-spacing: .05em; }
.toc-list { list-style: none; }
.toc-list li { margin-bottom: 2px; }
.toc-list a {
  display: block; padding: 5px 8px; border-radius: 4px; color: var(--text-secondary);
  text-decoration: none; transition: background .15s;
}
.toc-list a:hover, .toc-list a:focus { background: var(--bg); color: var(--text); }
.toc-list a.toc-visual { padding-left: 20px; font-size: 12px; color: var(--text-muted); }

.toc-mobile-toggle {
  display: none; position: fixed; bottom: 20px; right: 20px; z-index: 200;
  width: 44px; height: 44px; border-radius: 50%; background: var(--accent); color: #fff;
  border: none; font-size: 20px; cursor: pointer; box-shadow: var(--shadow-md);
}

/* ---- main content ---- */
main {
  flex: 1; min-width: 0; padding: 32px 40px 80px;
}

/* ---- chapter section ---- */
.chapter-section {
  margin-bottom: 48px; padding-bottom: 32px;
  border-bottom: 1px solid var(--border);
  break-inside: avoid; page-break-inside: avoid;
}
.chapter-section:last-of-type { border-bottom: none; }

.chapter-header {
  margin-bottom: 20px;
  break-inside: avoid; page-break-inside: avoid;
}
.chapter-header h2 {
  font-size: 20px; font-weight: 700; color: var(--text); scroll-margin-top: 100px;
}
.chapter-time {
  font-size: 12px; color: var(--text-muted); margin-top: 2px;
  font-family: var(--font-mono);
}

/* ---- points grid ---- */
.points-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 28px; }
.point-card {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 14px; box-shadow: var(--shadow);
  break-inside: avoid; page-break-inside: avoid;
}
.point-card .badge {
  display: inline-block; font-size: 10px; font-weight: 600; text-transform: uppercase;
  padding: 2px 8px; border-radius: 99px; margin-bottom: 6px; letter-spacing: .03em;
}
.badge-problem    { background: var(--color-problem-bg); color: var(--color-problem); }
.badge-step       { background: var(--color-step-bg); color: var(--color-step); }
.badge-pitfall    { background: var(--color-pitfall-bg); color: var(--color-pitfall); }
.badge-conclusion { background: var(--color-conclusion-bg); color: var(--color-conclusion); }
.badge-context    { background: var(--color-context-bg); color: var(--color-context); }

.point-content { font-size: 14px; color: var(--text); margin-bottom: 6px; }
.point-refs { display: flex; flex-wrap: wrap; gap: 4px; }
.point-ref {
  font-size: 11px; font-family: var(--font-mono); color: var(--accent);
  text-decoration: none; cursor: pointer; padding: 1px 6px;
  border-radius: 4px; background: var(--bg-secondary);
  transition: background .15s;
}
.point-ref:hover { background: var(--border); color: var(--accent-hover); }

/* ---- visual figure ---- */
.visual-figure {
  margin-top: 24px; margin-bottom: 32px;
  border: 1px solid var(--border); border-radius: var(--radius);
  overflow: hidden; box-shadow: var(--shadow);
  break-inside: avoid; page-break-inside: avoid;
}
.visual-figure figcaption {
  padding: 12px 16px; border-bottom: 1px solid var(--border);
  background: var(--bg-secondary); font-size: 13px;
}
.visual-figure figcaption .fig-title { font-weight: 600; color: var(--text); }
.visual-figure figcaption .fig-rationale { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
.visual-figure figcaption .fig-refs { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px; }
.visual-figure .svg-wrapper {
  padding: 12px; background: var(--svg-bg);
  overflow-x: auto; -webkit-overflow-scrolling: touch;
}
.visual-figure .svg-wrapper svg { display: block; min-width: 100%; height: auto; }

/* ---- skipped aside ---- */
.skipped-note {
  margin-top: 40px; padding: 16px; background: var(--bg-secondary);
  border: 1px solid var(--border); border-radius: var(--radius);
  font-size: 13px; color: var(--text-secondary);
}
.skipped-note h3 { font-size: 14px; color: var(--text); margin-bottom: 8px; }

/* ---- footer ---- */
.page-footer {
  padding: 20px 40px 40px; text-align: center; font-size: 11px; color: var(--text-muted);
  border-top: 1px solid var(--border); margin-top: 40px;
}
.page-footer span { display: block; margin-top: 4px; }

/* ---- responsive ---- */
@media (max-width: 768px) {
  .toc-sidebar {
    display: none; position: fixed; top: 0; left: 0; width: 280px; height: 100vh;
    z-index: 300; padding-top: 60px; box-shadow: var(--shadow-md);
  }
  .toc-sidebar.open { display: block; }
  .toc-mobile-toggle { display: flex; align-items: center; justify-content: center; }
  main { padding: 20px 16px 80px; }
  .points-grid { grid-template-columns: 1fr; }
  .page-header h1 { font-size: 16px; max-width: 400px; }
}

@media (max-width: 480px) {
  .header-meta { gap: 8px; }
  .page-header { padding: 12px 16px; }
  .visual-figure .svg-wrapper { padding: 6px; }
}

/* ---- print (Contract 3) ---- */
@media print {
  @page { margin: 1.5cm; size: A4; }
  .toc-sidebar, .theme-toggle, .toc-mobile-toggle, .skip-link, .page-footer { display: none !important; }
  .page-header { position: static; border-bottom: 2px solid #000; padding: 0 0 12px; margin-bottom: 24px; }
  main { padding: 0; max-width: 100%; }
  body { font-size: 12px; color: #000; background: #fff; }
  .chapter-section, .point-card, .visual-figure, figure, figcaption, .svg-wrapper, .chapter-header {
    break-inside: avoid; page-break-inside: avoid;
  }
  .visual-figure { border: 1px solid #ccc; box-shadow: none; }
  .visual-figure .svg-wrapper svg { max-width: 100%; height: auto; }
  .point-card { border: 1px solid #ddd; box-shadow: none; }
  a { color: #000; text-decoration: none; }
}
"""


# ======================================================================
# JavaScript (~60 lines)
# ======================================================================

def _build_js() -> str:
    return r"""(() => {
  /* 主题切换 */
  const toggle = document.getElementById('theme-toggle');
  const stored = localStorage.getItem('metascribe-theme');
  if (stored) document.documentElement.setAttribute('data-theme', stored);
  toggle?.addEventListener('click', () => {
    const cur = document.documentElement.getAttribute('data-theme');
    const next = cur === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('metascribe-theme', next);
  });

  /* TOC 移动端 toggle */
  const tocBtn = document.getElementById('toc-mobile-toggle');
  const toc = document.getElementById('toc-sidebar');
  tocBtn?.addEventListener('click', () => toc?.classList.toggle('open'));
  document.addEventListener('click', (e) => {
    if (toc && toc.classList.contains('open')
        && !toc.contains(e.target) && e.target !== tocBtn) {
      toc.classList.remove('open');
    }
  });

  /* 时间戳导航 #t=123.5 */
  let lastClickedTs = null;
  let clickTimer = null;
  document.querySelectorAll('.point-ref,.fig-ref').forEach(el => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      const ts = parseFloat(el.dataset.ts);
      if (isNaN(ts)) return;
      /* 双击/二次点击复制时间戳 */
      if (lastClickedTs === ts && clickTimer) {
        clearTimeout(clickTimer);
        clickTimer = null;
        lastClickedTs = null;
        navigator.clipboard?.writeText(_fmt(ts)).catch(()=>{});
        el.style.outline = '2px solid var(--accent)';
        setTimeout(() => el.style.outline = '', 600);
        return;
      }
      lastClickedTs = ts;
      clickTimer = setTimeout(() => { lastClickedTs = null; clickTimer = null; }, 400);

      /* 在所有 segments 中查找包含此时间的 segment */
      const cards = document.querySelectorAll('.point-card[data-start]');
      for (const card of cards) {
        const start = parseFloat(card.dataset.start);
        const end = parseFloat(card.dataset.end);
        if (ts >= start && ts < end) {
          card.scrollIntoView({ behavior: 'smooth', block: 'center' });
          card.style.outline = '2px solid var(--accent)';
          setTimeout(() => card.style.outline = '', 1500);
          return;
        }
      }
      /* fallback: 滚到最接近的章节 */
      const sections = document.querySelectorAll('.chapter-section');
      for (const sec of sections) {
        const s = parseFloat(sec.dataset.startTs);
        const e = parseFloat(sec.dataset.endTs);
        if (ts >= s && ts < e) {
          sec.querySelector('h2')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
          return;
        }
      }
    });
  });

  function _fmt(s) {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return m + ':' + String(sec).padStart(2, '0');
  }

  /* 平滑滚动偏移 */
  const style = document.createElement('style');
  style.textContent = 'h2[class] { scroll-margin-top: 96px; }';
  document.head.appendChild(style);
})();
"""


# ======================================================================
# HTML 片段构建
# ======================================================================

def _build_header(meta) -> str:
    dur = _fmt_time(meta.duration)
    lines = [
        '<header class="page-header">',
        f'<h1>{_escape_html(meta.title)}</h1>',
        '<div class="header-meta">',
    ]
    if meta.uploader:
        lines.append(f'<span>上传者: {_escape_html(meta.uploader)}</span>')
    lines.append(f'<span>时长: {dur}</span>')
    if meta.view_count:
        lines.append(f'<span>播放: {meta.view_count:,}</span>')
    lines.append(
        '<button id="theme-toggle" class="theme-toggle" aria-label="切换主题">🌓 主题</button>'
        '</div>'
        '</header>'
    )
    return "\n".join(lines)


def _build_toc(chapters, visuals) -> str:
    """构建 TOC 侧边栏（Contract 1: deterministic ordering）。"""
    lines = [
        '<nav class="toc-sidebar" id="toc-sidebar">',
        '<div class="toc-title">目录</div>',
        '<ol class="toc-list">',
    ]

    # 按章排序，每章的 visuals 也排序
    vis_by_ch: dict[str, list] = {}
    for v in sorted(visuals, key=lambda x: x.id):
        vis_by_ch.setdefault(v.chapter_id, []).append(v)

    for ch in sorted(chapters, key=lambda x: x.id):
        lines.append(
            f'<li><a href="#{_escape_html(ch.id)}">'
            f'{_escape_html(ch.id.upper())} {_escape_html(ch.title)}</a></li>'
        )
        for vis in vis_by_ch.get(ch.id, []):
            lines.append(
                f'<li><a class="toc-visual" href="#{_escape_html(vis.id)}">'
                f'└ {_escape_html(vis.title)}</a></li>'
            )

    lines.append('</ol>')
    lines.append('</nav>')
    lines.append(
        '<button class="toc-mobile-toggle" id="toc-mobile-toggle" '
        'aria-label="目录">☰</button>'
    )
    return "\n".join(lines)


def _build_point_card(point, point_index: int) -> str:
    ptype = point.type
    badge_class = f"badge-problem" if ptype == "problem" else \
                  f"badge-step" if ptype == "step" else \
                  f"badge-pitfall" if ptype == "pitfall" else \
                  f"badge-conclusion" if ptype == "conclusion" else \
                  f"badge-context"
    label = _point_type_label(ptype)

    # refs sorted by segment_id (Contract 1)
    refs = sorted(point.refs, key=lambda r: r.segment_id)
    ref_html = ""
    if refs:
        ref_links = []
        for r in refs[:5]:
            ref_links.append(
                f'<span class="point-ref" data-ts="{r.ts}">{_fmt_time(r.ts)}</span>'
            )
        ref_html = '<div class="point-refs">' + "".join(ref_links) + '</div>'

    return (
        f'<article class="point-card" id="pt{point_index}" data-start="{point.refs[0].ts if point.refs else 0}" data-end="{point.refs[-1].ts if point.refs else 0}">'
        f'<span class="badge {badge_class}">{_escape_html(label)}</span>'
        f'<div class="point-content">{_escape_html(point.content)}</div>'
        f'{ref_html}'
        f'</article>'
    )


def _build_visual_figure(vis) -> str:
    svg = render_svg(vis.svg_type, vis.data, vis.title, vis.layout_hint)

    # refs sorted (Contract 1)
    refs = sorted(vis.semantic_refs, key=lambda r: r.segment_id)
    ref_links = []
    for r in refs[:8]:
        ref_links.append(
            f'<span class="point-ref fig-ref" data-ts="{r.ts}">'
            f'seg{r.segment_id} {_fmt_time(r.ts)}</span>'
        )

    return (
        f'<figure class="visual-figure" id="{_escape_html(vis.id)}">'
        f'<figcaption>'
        f'<div class="fig-title">{_escape_html(vis.title)} <span style="font-weight:400;font-size:11px;color:var(--text-muted)">[{vis.svg_type}]</span></div>'
        f'<div class="fig-rationale">{_escape_html(vis.rationale)}</div>'
        f'<div class="fig-refs">{"".join(ref_links)}</div>'
        f'</figcaption>'
        f'<div class="svg-wrapper">{svg}</div>'
        f'</figure>'
    )


def _build_chapter_section(ch, chapter_visuals, segments: dict[int, Segment]) -> str:
    ts_range = f"{_fmt_time(ch.start_ts)} – {_fmt_time(ch.end_ts)}"

    # points sorted by type then content (Contract 1)
    points = sorted(ch.points, key=lambda p: (p.type, p.content))

    point_cards = []
    for i, pt in enumerate(points):
        point_cards.append(_build_point_card(pt, i))

    vis_figures = []
    for vis in sorted(chapter_visuals, key=lambda v: v.id):
        vis_figures.append(_build_visual_figure(vis))

    return (
        f'<section class="chapter-section" id="{_escape_html(ch.id)}" data-start-ts="{ch.start_ts}" data-end-ts="{ch.end_ts}">'
        f'<div class="chapter-header">'
        f'<h2>{_escape_html(ch.id.upper())} {_escape_html(ch.title)}</h2>'
        f'<div class="chapter-time">{ts_range}</div>'
        f'</div>'
        f'<div class="points-grid">{"".join(point_cards)}</div>'
        f'{"".join(vis_figures)}'
        f'</section>'
    )


# ======================================================================
# HTML 组装
# ======================================================================

def build_html(output_dir: Path, prompt_version: str = "v1") -> str:
    """从 outputs/{video_id}/ 构建完整 index.html 字符串。"""
    inputs = RenderInputs.load(output_dir)
    meta = inputs.meta
    semantic = inputs.semantic
    visual = inputs.visual
    segments = inputs.segments

    rendered_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 按章排序 (Contract 1)
    chapters = sorted(semantic.chapters, key=lambda c: c.id)
    visuals = sorted(visual.visuals, key=lambda v: (v.chapter_id, v.id))

    # chapter → visuals 映射
    vis_by_ch: dict[str, list] = {}
    for v in visuals:
        vis_by_ch.setdefault(v.chapter_id, []).append(v)

    # 章节 sections
    sections = []
    for ch in chapters:
        ch_vis = vis_by_ch.get(ch.id, [])
        sections.append(_build_chapter_section(ch, ch_vis, segments))

    # 跳过说明
    skipped_note = ""
    if visual.skipped:
        skipped_items = "\n".join(
            f'<li>{_escape_html(s.get("chapter_id", "?"))}: {_escape_html(s.get("reason", ""))}</li>'
            for s in sorted(visual.skipped, key=lambda s: s.get("chapter_id", ""))
        )
        skipped_note = (
            f'<aside class="skipped-note">'
            f'<h3>跳过的章节</h3><ul>{skipped_items}</ul>'
            f'</aside>'
        )

    html = f"""<!DOCTYPE html>
<html lang="zh" data-theme>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="MetaScribe render v1">
<meta name="render-version" content="v1">
<meta name="prompt-version" content="{_escape_html(prompt_version)}">
<meta name="rendered-at" content="{rendered_at}">
<title>{_escape_html(meta.title)} — MetaScribe</title>
<style>
{_build_css()}
</style>
</head>
<body>
<a class="skip-link" href="#main-content">跳转到主内容</a>
{_build_header(meta)}
<div class="page-layout">
{_build_toc(chapters, visuals)}
<main id="main-content">
{"".join(sections)}
{skipped_note}
</main>
</div>
<footer class="page-footer">
<span>MetaScribe Render v1 · {rendered_at}</span>
<span>{len(chapters)} 章 · {len(visuals)} 个可视化图表 · {visual.stats.get('type_distribution', {})}</span>
</footer>
<script>
{_build_js()}
</script>
</body>
</html>"""

    return html


def run_render(video_id: str, project_root: str | Path, prompt_version: str = "v1") -> Path:
    """便捷入口：给定 video_id，生成 index.html。返回输出路径。"""
    root = Path(project_root)
    output_dir = root / "outputs" / video_id
    if not output_dir.exists():
        raise FileNotFoundError(f"输出目录不存在: {output_dir}")

    html = build_html(output_dir, prompt_version=prompt_version)
    out_path = output_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"[OK] {out_path} ({len(html):,} bytes)")
    return out_path


# ---- CLI ----
if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    if len(sys.argv) < 2:
        print("用法: python render.py <video_id> [project_root]", file=sys.stderr)
        print("示例: python render.py BV1Js596dEnT", file=sys.stderr)
        print("示例: python render.py jNQXAC9IVRw .", file=sys.stderr)
        sys.exit(1)

    vid = sys.argv[1]
    root = sys.argv[2] if len(sys.argv) > 2 else "."

    try:
        run_render(vid, root)
    except Exception as e:
        print(f"RENDER FAILED: {e}", file=sys.stderr)
        sys.exit(1)
