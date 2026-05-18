"""SVG 渲染器 —— 7 种图表类型，纯 Python 生成 inline SVG。

所有 SVG 使用 CSS 变量适配暗色模式，无外部依赖。
"""

import re
from html import escape as _html_escape


# ---------------------------------------------------------------------------
# 文本换行工具 (Contract 1)
# ---------------------------------------------------------------------------

def _wrap_text(text: str, max_chars: int, font_size: int = 14) -> list[str]:
    """将文本按显示宽度折行，返回行列表。

    中文字符宽度 ≈ 1.0, ASCII 字符宽度 ≈ 0.55（以 font_size 为单位）。
    最大 5 行，超出截断为 "..."。
    """
    if not text:
        return [""]

    lines: list[str] = []
    current: list[str] = []
    current_width: float = 0.0

    for ch in text:
        ch_w = 1.0 if ord(ch) > 127 else 0.55
        if current_width + ch_w > max_chars and current:
            lines.append("".join(current))
            if len(lines) >= 5:
                lines[-1] = lines[-1][:max_chars - 3] + "..."
                return lines
            current = []
            current_width = 0.0
        current.append(ch)
        current_width += ch_w

    if current:
        lines.append("".join(current))

    return lines if lines else [""]


def _full_text_tspan(text: str, max_chars: int, font_size: int = 14,
                     line_height: float = 1.4, x: float = 4) -> str:
    """生成 <tspan> 序列，同时在 <title> 中保留全文用于 tooltip。"""
    lines = _wrap_text(text, max_chars, font_size)
    safe_text = _html_escape(text)
    tspans = []
    for i, line in enumerate(lines):
        dy = f'{line_height}em' if i > 0 else '0'
        tspans.append(f'<tspan x="{x}" dy="{dy}">{_html_escape(line)}</tspan>')
    return "\n".join(tspans), safe_text


# ---------------------------------------------------------------------------
# SVG 元素工具
# ---------------------------------------------------------------------------

_SVG_HEAD = '<svg xmlns="http://www.w3.org/2000/svg" role="img" width="100%" height="100%" viewBox="{viewbox}" preserveAspectRatio="xMidYMid meet">'
_SVG_STYLE = """<style>
  text { font-family: system-ui, -apple-system, sans-serif; }
  .title-text { font-size: 15px; font-weight: 600; }
  .body-text { font-size: 12px; }
  .small-text { font-size: 10px; }
  .edge { stroke: var(--svg-stroke, #94a3b8); stroke-width: 1.5; fill: none; }
  .edge-label { font-size: 10px; fill: var(--svg-text-secondary, #64748b); }
</style>"""
_MARKER = """<defs>
  <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto">
    <path d="M0,0 L10,5 L0,10 Z" fill="var(--svg-stroke, #94a3b8)"/>
  </marker>
</defs>"""


def _svg(*parts: str, viewbox: str = "0 0 800 600") -> str:
    body = "\n".join(parts)
    return f'{_SVG_HEAD.format(viewbox=viewbox)}\n{_SVG_STYLE}\n{_MARKER}\n{body}\n</svg>'


def _fallback_svg(svg_type: str, title: str) -> str:
    """数据不足时的 fallback SVG。"""
    return _svg(
        f'<rect width="100%" height="100%" fill="var(--svg-bg, #f8fafc)" rx="8"/>',
        f'<text x="400" y="45" text-anchor="middle" class="title-text" fill="var(--svg-text, #334155)">{_html_escape(title)}</text>',
        f'<text x="400" y="75" text-anchor="middle" class="body-text" fill="var(--svg-text-secondary, #94a3b8)">（数据不足，无法渲染 {svg_type}）</text>',
        viewbox="0 0 800 120",
    )


# ---------------------------------------------------------------------------
# 1. flowchart
# ---------------------------------------------------------------------------

_NODE_SHAPES = {
    "start":    'rx="20" ry="20"',
    "end":      'rx="20" ry="20"',
    "process":  'rx="6" ry="6"',
    "decision": 'd="M{xc},0 L{xr},{yh} L{xc},{yb} L{xl},{yh} Z"',  # diamond, special
}


def render_flowchart(data: dict, title: str, layout_hint: str = "vertical") -> str:
    nodes = data.get("nodes", [])[:20]
    edges = data.get("edges", [])[:25]

    if not nodes:
        return _fallback_svg("flowchart", title)

    n = len(nodes)
    node_w, node_h = 160, 50
    view_w = 800
    view_h = n * 110 + 40
    cx = view_w / 2
    start_y = 60

    node_positions: dict[str, tuple[float, float]] = {}
    parts: list[str] = []

    # title
    parts.append(f'<text x="{cx}" y="30" text-anchor="middle" class="title-text" fill="var(--svg-text, #1e293b)">{_html_escape(title)}</text>')

    # 先计算所有节点位置
    for i, node in enumerate(nodes):
        nx = cx - node_w / 2
        ny = start_y + i * 110
        nid = node.get("id", f"n{i}")
        node_positions[nid] = (nx, ny)

    # edges (behind nodes)
    for e in edges:
        frm = e.get("from", "")
        to = e.get("to", "")
        if frm not in node_positions or to not in node_positions:
            continue
        x1, y1 = node_positions[frm]
        x2, y2 = node_positions[to]
        elabel = e.get("label", "")
        parts.append(f'<line x1="{x1 + node_w/2}" y1="{y1 + node_h}" x2="{x2 + node_w/2}" y2="{y2}" class="edge" marker-end="url(#arrow)"/>')
        if elabel:
            mx = (x1 + x2 + node_w) / 2
            my = (y1 + node_h + y2) / 2
            parts.append(f'<text x="{mx}" y="{my}" text-anchor="middle" class="edge-label">{_html_escape(elabel[:20])}</text>')

    # nodes
    for i, node in enumerate(nodes):
        nx = cx - node_w / 2
        ny = start_y + i * 110
        ntype = node.get("type", "process")
        nlabel = node.get("label", "")
        nid = node.get("id", f"n{i}")

        fill = {
            "start": "var(--svg-node-start, #dbeafe)",
            "end": "var(--svg-node-end, #d1fae5)",
            "process": "var(--svg-node-fill, #f1f5f9)",
            "decision": "var(--svg-node-decision, #fef3c7)",
        }.get(ntype, "var(--svg-node-fill, #f1f5f9)")

        stroke = {
            "start": "var(--svg-accent, #3b82f6)",
            "end": "var(--svg-accent, #10b981)",
            "process": "var(--svg-stroke, #64748b)",
            "decision": "var(--svg-warning, #f59e0b)",
        }.get(ntype, "var(--svg-stroke, #64748b)")

        if ntype == "decision":
            hw = node_w / 2
            hh = node_h / 2
            parts.append(f'<polygon points="{nx + hw},{ny} {nx + node_w},{ny + hh} {nx + hw},{ny + node_h} {nx},{ny + hh}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
        else:
            rx = "20" if ntype in ("start", "end") else "6"
            parts.append(f'<rect x="{nx}" y="{ny}" width="{node_w}" height="{node_h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')

        max_ch = int(node_w / (12 * 0.85))
        tspan_html, full = _full_text_tspan(nlabel, max_ch, font_size=12, line_height=1.4, x=nx + 4)
        parts.append(f'<text x="{nx + 4}" y="{ny + 20}" class="body-text" fill="var(--svg-text, #334155)"><title>{full}</title>{tspan_html}</text>')

    return _svg(*parts, viewbox=f"0 0 {view_w} {view_h}")


# ---------------------------------------------------------------------------
# 2. matrix
# ---------------------------------------------------------------------------

def render_matrix(data: dict, title: str, layout_hint: str = "grid") -> str:
    columns = data.get("columns", [])[:8]
    rows = data.get("rows", [])[:10]

    if not columns or not rows:
        return _fallback_svg("matrix", title)

    col_w = 130
    row_h = 60
    header_h = 36
    label_w = 100
    n_cols = len(columns)
    n_rows = len(rows)
    view_w = label_w + n_cols * col_w + 20
    view_h = header_h + n_rows * row_h + 40

    parts: list[str] = []

    # title
    parts.append(f'<text x="{view_w/2}" y="24" text-anchor="middle" class="title-text" fill="var(--svg-text, #1e293b)">{_html_escape(title)}</text>')

    # column headers
    for j, col in enumerate(columns):
        cx = label_w + j * col_w
        clabel = col.get("label", col.get("id", f"c{j}")) if isinstance(col, dict) else str(col)
        parts.append(f'<rect x="{cx}" y="30" width="{col_w}" height="{header_h}" fill="var(--svg-node-fill, #e2e8f0)" stroke="var(--svg-stroke, #cbd5e1)" stroke-width="1"/>')
        max_ch = int((col_w - 8) / (11 * 0.85))
        tspan_html, full = _full_text_tspan(clabel, max_ch, font_size=11, line_height=1.3, x=cx + 4)
        parts.append(f'<text x="{cx + 4}" y="48" class="small-text" fill="var(--svg-text, #475569)" font-weight="600"><title>{full}</title>{tspan_html}</text>')

    # rows
    for i, row in enumerate(rows):
        ry = header_h + 30 + i * row_h
        rlabel = row.get("label", row.get("id", f"r{i}"))
        parts.append(f'<rect x="0" y="{ry}" width="{label_w}" height="{row_h}" fill="var(--svg-node-fill, #f1f5f9)" stroke="var(--svg-stroke, #cbd5e1)" stroke-width="1"/>')
        max_ch = int((label_w - 8) / (11 * 0.85))
        tspan_html, full = _full_text_tspan(rlabel, max_ch, font_size=11, line_height=1.3, x=4)
        parts.append(f'<text x="4" y="{ry + 18}" class="small-text" fill="var(--svg-text, #475569)" font-weight="600"><title>{full}</title>{tspan_html}</text>')

        # cells — handle both formats: cells[{value}] and values[{column_id, value}]
        cells = row.get("cells", [])
        values = row.get("values", [])

        if values:
            # values format: map by column_id
            val_map = {}
            for v in values:
                cid = v.get("column_id", "")
                val_map[cid] = v.get("value", "")
            for j, col in enumerate(columns):
                cid = col.get("id", "") if isinstance(col, dict) else ""
                cell_val = val_map.get(cid, "")
                cx = label_w + j * col_w
                parts.append(f'<rect x="{cx}" y="{ry}" width="{col_w}" height="{row_h}" fill="var(--svg-bg, #fff)" stroke="var(--svg-stroke, #cbd5e1)" stroke-width="1"/>')
                if cell_val:
                    max_ch = int((col_w - 8) / (11 * 0.85))
                    tspan_html, full = _full_text_tspan(cell_val, max_ch, font_size=11, line_height=1.3, x=cx + 4)
                    parts.append(f'<text x="{cx + 4}" y="{ry + 18}" class="small-text" fill="var(--svg-text, #334155)"><title>{full}</title>{tspan_html}</text>')
        elif cells:
            for j, cell in enumerate(cells):
                if j >= len(columns):
                    break
                cx = label_w + j * col_w
                cell_val = cell.get("value", "") if isinstance(cell, dict) else str(cell)
                parts.append(f'<rect x="{cx}" y="{ry}" width="{col_w}" height="{row_h}" fill="var(--svg-bg, #fff)" stroke="var(--svg-stroke, #cbd5e1)" stroke-width="1"/>')
                if cell_val:
                    max_ch = int((col_w - 8) / (11 * 0.85))
                    tspan_html, full = _full_text_tspan(cell_val, max_ch, font_size=11, line_height=1.3, x=cx + 4)
                    parts.append(f'<text x="{cx + 4}" y="{ry + 18}" class="small-text" fill="var(--svg-text, #334155)"><title>{full}</title>{tspan_html}</text>')

    return _svg(*parts, viewbox=f"0 0 {view_w} {view_h}")


# ---------------------------------------------------------------------------
# 3. timeline
# ---------------------------------------------------------------------------

def render_timeline(data: dict, title: str, layout_hint: str = "horizontal") -> str:
    events = data.get("events", [])[:15]

    if not events:
        return _fallback_svg("timeline", title)

    n = len(events)
    view_w = 900
    view_h = max(240, n * 56 + 60)
    cx = 200
    start_y = 60

    parts: list[str] = []
    parts.append(f'<text x="450" y="28" text-anchor="middle" class="title-text" fill="var(--svg-text, #1e293b)">{_html_escape(title)}</text>')

    # center line
    parts.append(f'<line x1="{cx}" y1="{start_y}" x2="{cx}" y2="{start_y + n * 56}" stroke="var(--svg-stroke, #94a3b8)" stroke-width="2"/>')

    for i, ev in enumerate(events):
        y = start_y + i * 56
        ts = ev.get("ts", "")
        label = ev.get("label", "")
        detail = ev.get("detail", "")

        # circle on line
        parts.append(f'<circle cx="{cx}" cy="{y}" r="6" fill="var(--svg-accent, #3b82f6)" stroke="var(--svg-bg, #fff)" stroke-width="2"/>')

        # ts label (left)
        parts.append(f'<text x="{cx - 12}" y="{y + 4}" text-anchor="end" class="small-text" fill="var(--svg-text-secondary, #64748b)">{_html_escape(str(ts))}</text>')

        # event label (right)
        side = 1 if i % 2 == 0 else -1
        tx = cx + 20
        ty = y + (20 if side > 0 else -10)
        anchor = "start"
        max_ch = 50
        tspan_html, full = _full_text_tspan(label, max_ch, font_size=12, line_height=1.4, x=tx)
        parts.append(f'<text x="{tx}" y="{ty}" text-anchor="{anchor}" class="body-text" fill="var(--svg-text, #334155)" font-weight="600"><title>{full}</title>{tspan_html}</text>')

        if detail:
            ty2 = ty + len(_wrap_text(label, max_ch)) * 16 + 4
            tspan_d, full_d = _full_text_tspan(detail, 40, font_size=10, line_height=1.3, x=tx)
            parts.append(f'<text x="{tx}" y="{ty2}" text-anchor="{anchor}" class="small-text" fill="var(--svg-text-secondary, #94a3b8)"><title>{full_d}</title>{tspan_d}</text>')

    return _svg(*parts, viewbox=f"0 0 {view_w} {view_h}")


# ---------------------------------------------------------------------------
# 4. chain
# ---------------------------------------------------------------------------

def render_chain(data: dict, title: str, layout_hint: str = "horizontal") -> str:
    nodes = data.get("nodes", [])[:12]
    edges = data.get("edges", [])[:15]

    if not nodes:
        return _fallback_svg("chain", title)

    n = len(nodes)
    node_w = 180
    node_h = 70
    gap = 40
    view_w = max(800, n * (node_w + gap) + 40)
    view_h = 220
    start_x = 20
    start_y = 80

    parts: list[str] = []
    parts.append(f'<text x="{view_w/2}" y="30" text-anchor="middle" class="title-text" fill="var(--svg-text, #1e293b)">{_html_escape(title)}</text>')

    node_positions: dict[str, tuple[float, float]] = {}

    for i, node in enumerate(nodes):
        nx = start_x + i * (node_w + gap) + (20 if i == 0 else 0)
        ny = start_y
        nid = node.get("id", f"n{i}")
        nlabel = node.get("label", "")
        node_positions[nid] = (nx, ny)

        ntype = node.get("type", "cause")
        fill = "var(--svg-node-cause, #fee2e2)" if ntype == "cause" else "var(--svg-node-effect, #dbeafe)" if ntype == "effect" else "var(--svg-node-fill, #f1f5f9)"
        stroke = "var(--svg-critical, #ef4444)" if ntype == "cause" else "var(--svg-accent, #3b82f6)" if ntype == "effect" else "var(--svg-stroke, #94a3b8)"

        parts.append(f'<rect x="{nx}" y="{ny}" width="{node_w}" height="{node_h}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')

        max_ch = int(node_w / (12 * 0.85))
        tspan_html, full = _full_text_tspan(nlabel, max_ch, font_size=12, line_height=1.4, x=nx + 6)
        parts.append(f'<text x="{nx + 6}" y="{ny + 18}" class="body-text" fill="var(--svg-text, #334155)" font-weight="600"><title>{full}</title>{tspan_html}</text>')

        desc = node.get("desc", "")
        if desc:
            tspan_d, full_d = _full_text_tspan(desc, max_ch, font_size=10, line_height=1.3, x=nx + 6)
            parts.append(f'<text x="{nx + 6}" y="{ny + 38}" class="small-text" fill="var(--svg-text-secondary, #94a3b8)"><title>{full_d}</title>{tspan_d}</text>')

    # edges
    for e in edges:
        frm = e.get("from", "")
        to = e.get("to", "")
        if frm not in node_positions or to not in node_positions:
            continue
        fx, fy = node_positions[frm]
        tx, ty = node_positions[to]
        ex1 = fx + node_w
        ey1 = fy + node_h / 2
        ex2 = tx
        ey2 = ty + node_h / 2
        elabel = e.get("label", "")
        parts.append(f'<line x1="{ex1}" y1="{ey1}" x2="{ex2}" y2="{ey2}" class="edge" marker-end="url(#arrow)"/>')
        if elabel:
            mx = (ex1 + ex2) / 2
            my = ey1 - 8
            parts.append(f'<text x="{mx}" y="{my}" text-anchor="middle" class="edge-label">{_html_escape(elabel[:24])}</text>')

    return _svg(*parts, viewbox=f"0 0 {view_w} {view_h}")


# ---------------------------------------------------------------------------
# 5. layered
# ---------------------------------------------------------------------------

def render_layered(data: dict, title: str, layout_hint: str = "vertical") -> str:
    layers = data.get("layers", [])[:8]

    if not layers:
        return _fallback_svg("layered", title)

    n = len(layers)
    view_w = 800
    view_h = n * 100 + 40
    cx = view_w / 2
    start_y = 50

    parts: list[str] = []
    parts.append(f'<text x="{cx}" y="28" text-anchor="middle" class="title-text" fill="var(--svg-text, #1e293b)">{_html_escape(title)}</text>')

    for i, layer in enumerate(layers):
        level = layer.get("level", i + 1)
        llabel = layer.get("label", "")
        items = layer.get("items", [])[:10]

        margin = i * 40
        lw = view_w - 80 - margin * 2
        lx = 40 + margin
        ly = start_y + i * 100
        lh = 80

        fill = f"hsl({(i * 40) % 360}, 40%, {90 - i * 3}%)"
        parts.append(f'<rect x="{lx}" y="{ly}" width="{lw}" height="{lh}" rx="6" fill="{fill}" stroke="var(--svg-stroke, #cbd5e1)" stroke-width="1"/>')

        parts.append(f'<text x="{lx + 8}" y="{ly + 18}" class="small-text" fill="var(--svg-text-secondary, #64748b)">L{level}</text>')
        tspan_l, full_l = _full_text_tspan(llabel, 30, font_size=12, line_height=1.3, x=lx + 8)
        parts.append(f'<text x="{lx + 8}" y="{ly + 36}" class="body-text" fill="var(--svg-text, #334155)" font-weight="600"><title>{full_l}</title>{tspan_l}</text>')

        if items:
            item_text = "  ·  ".join(items[:5])
            if len(items) > 5:
                item_text += f"  ...{len(items) - 5} more"
            max_ch = int((lw - 16) / (10 * 0.85))
            tspan_i, full_i = _full_text_tspan(item_text, max_ch, font_size=10, line_height=1.3, x=lx + 8)
            parts.append(f'<text x="{lx + 8}" y="{ly + 52}" class="small-text" fill="var(--svg-text-secondary, #94a3b8)"><title>{full_i}</title>{tspan_i}</text>')

    return _svg(*parts, viewbox=f"0 0 {view_w} {view_h}")


# ---------------------------------------------------------------------------
# 6. decision_tree
# ---------------------------------------------------------------------------

def _render_branches(branches: list[dict], x: float, y: float, depth: int,
                     max_depth: int = 6, max_leaf: int = 50) -> tuple[list[str], float, int]:
    """递归渲染决策树分支。返回 (svg_parts, bottom_y, leaf_count)。"""
    parts: list[str] = []
    leaf_count = 0
    node_w = 200 - depth * 12
    node_h = 44 if depth <= 3 else 36
    gap_y = 18
    gap_x = node_w + 30

    if depth > max_depth:
        return parts, y, 0

    cy = y
    for branch in branches:
        condition = branch.get("condition", "")
        result = branch.get("outcome", branch.get("result", ""))
        sub = branch.get("branches", branch.get("sub_branches", []))

        # condition node (left)
        cond_fill = "var(--svg-node-decision, #fef3c7)"
        max_ch = int(node_w / (11 * 0.85))
        tspan_c, full_c = _full_text_tspan(condition, max_ch, font_size=11, line_height=1.3, x=x + 6)
        parts.append(f'<rect x="{x}" y="{cy}" width="{node_w}" height="{node_h}" rx="4" fill="{cond_fill}" stroke="var(--svg-warning, #f59e0b)" stroke-width="1"/>')
        parts.append(f'<text x="{x + 6}" y="{cy + 16}" class="small-text" fill="var(--svg-text, #334155)"><title>{full_c}</title>{tspan_c}</text>')

        if result:
            # result node (right)
            rx = x + gap_x
            res_fill = "var(--svg-node-effect, #dbeafe)"
            tspan_r, full_r = _full_text_tspan(result, max_ch, font_size=11, line_height=1.3, x=rx + 6)
            parts.append(f'<rect x="{rx}" y="{cy}" width="{node_w}" height="{node_h}" rx="4" fill="{res_fill}" stroke="var(--svg-accent, #3b82f6)" stroke-width="1"/>')
            parts.append(f'<text x="{rx + 6}" y="{cy + 16}" class="small-text" fill="var(--svg-text, #334155)"><title>{full_r}</title>{tspan_r}</text>')
            # connector line
            parts.append(f'<line x1="{x + node_w}" y1="{cy + node_h/2}" x2="{rx}" y2="{cy + node_h/2}" class="edge" marker-end="url(#arrow)"/>')
            leaf_count += 1
            cy += node_h + gap_y
        elif sub:
            # connector to sub-branches
            parts.append(f'<line x1="{x + node_w}" y1="{cy + node_h/2}" x2="{x + gap_x}" y2="{cy + node_h/2}" class="edge" marker-end="url(#arrow)"/>')

        # recurse sub-branches
        if sub:
            sub_x = x + gap_x + 20
            sub_parts, sub_bottom, sub_leaf = _render_branches(sub, sub_x, cy, depth + 1, max_depth, max_leaf)
            parts.extend(sub_parts)
            cy = sub_bottom
            leaf_count += sub_leaf
        elif not result:
            cy += node_h + gap_y

        if leaf_count >= max_leaf:
            parts.append(f'<text x="{x}" y="{cy + 14}" class="small-text" fill="var(--svg-text-secondary, #94a3b8)">...{(max_leaf - leaf_count)} more</text>')
            break

    return parts, cy, leaf_count


def render_decision_tree(data: dict, title: str, layout_hint: str = "horizontal") -> str:
    root = data.get("root", {})

    if not root:
        return _fallback_svg("decision_tree", title)

    root_label = root.get("question", root.get("label", ""))
    branches = root.get("branches", [])

    view_w = 900
    start_x = 20
    start_y = 60

    parts: list[str] = []
    parts.append(f'<text x="{view_w/2}" y="28" text-anchor="middle" class="title-text" fill="var(--svg-text, #1e293b)">{_html_escape(title)}</text>')

    # root node
    parts.append(f'<rect x="{start_x}" y="{start_y - 14}" width="180" height="44" rx="22" fill="var(--svg-node-start, #dbeafe)" stroke="var(--svg-accent, #3b82f6)" stroke-width="2"/>')
    max_ch = int(180 / (12 * 0.85))
    tspan_r, full_r = _full_text_tspan(root_label, max_ch, font_size=12, line_height=1.4, x=start_x + 10)
    parts.append(f'<text x="{start_x + 10}" y="{start_y + 8}" class="body-text" fill="var(--svg-text, #334155)" font-weight="600"><title>{full_r}</title>{tspan_r}</text>')

    # root→branches connector
    parts.append(f'<line x1="{start_x + 180}" y1="{start_y + 8}" x2="{start_x + 220}" y2="{start_y + 8}" class="edge" marker-end="url(#arrow)"/>')

    branch_parts, bottom_y, _ = _render_branches(branches, start_x + 220, start_y - 6, 1)
    parts.extend(branch_parts)

    view_h = bottom_y + 40
    return _svg(*parts, viewbox=f"0 0 {view_w} {view_h}")


# ---------------------------------------------------------------------------
# 7. checklist
# ---------------------------------------------------------------------------

def render_checklist(data: dict, title: str, layout_hint: str = "vertical") -> str:
    items = data.get("items", [])[:20]

    if not items:
        return _fallback_svg("checklist", title)

    n = len(items)
    view_w = 700
    item_h = 56
    view_h = n * item_h + 50
    start_y = 50

    parts: list[str] = []
    parts.append(f'<text x="350" y="28" text-anchor="middle" class="title-text" fill="var(--svg-text, #1e293b)">{_html_escape(title)}</text>')

    severity_icons = {
        "critical": ('<polygon points="8,2 14,14 2,14" fill="var(--svg-critical, #ef4444)"/>', "var(--svg-critical, #ef4444)"),
        "warning": ('<circle cx="8" cy="8" r="6" fill="var(--svg-warning, #f59e0b)"/>', "var(--svg-warning, #f59e0b)"),
        "info": ('<circle cx="8" cy="8" r="6" fill="var(--svg-accent, #3b82f6)"/>', "var(--svg-accent, #3b82f6)"),
    }

    for i, item in enumerate(items):
        y = start_y + i * item_h
        severity = item.get("severity", "info")
        label = item.get("label", "")
        detail = item.get("detail", "")

        icon_svg, icon_color = severity_icons.get(severity, severity_icons["info"])

        # icon
        parts.append(f'<g transform="translate(20, {y + 12})">{icon_svg}</g>')

        # label
        max_ch = 55
        tspan_l, full_l = _full_text_tspan(label, max_ch, font_size=13, line_height=1.4, x=48)
        parts.append(f'<text x="48" y="{y + 24}" class="body-text" fill="var(--svg-text, #334155)" font-weight="600"><title>{full_l}</title>{tspan_l}</text>')

        if detail:
            tspan_d, full_d = _full_text_tspan(detail, 60, font_size=10, line_height=1.3, x=48)
            parts.append(f'<text x="48" y="{y + 42}" class="small-text" fill="var(--svg-text-secondary, #94a3b8)"><title>{full_d}</title>{tspan_d}</text>')

    return _svg(*parts, viewbox=f"0 0 {view_w} {view_h}")


# ---------------------------------------------------------------------------
# 路由表
# ---------------------------------------------------------------------------

RENDERERS = {
    "flowchart": render_flowchart,
    "matrix": render_matrix,
    "timeline": render_timeline,
    "chain": render_chain,
    "layered": render_layered,
    "decision_tree": render_decision_tree,
    "checklist": render_checklist,
}


def render_svg(svg_type: str, data: dict, title: str, layout_hint: str = "vertical") -> str:
    """统一入口：根据 SVG 类型分发到对应渲染器。"""
    renderer = RENDERERS.get(svg_type)
    if renderer is None:
        return _fallback_svg(svg_type, title)
    try:
        return renderer(data, title, layout_hint)
    except Exception:
        return _fallback_svg(svg_type, title)
