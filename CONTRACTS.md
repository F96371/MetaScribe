# MetaScribe v1 Contracts

合约冻结文档。所有 pipeline 模块的 schema 版本、输出契约、确定性排序规则、演化策略在此定义。

任何 schema 变更必须在此文档中记录，并在 golden snapshot 中更新。

---

## 1. Frozen Schema Versions

| 模块 | 版本字段 | 版本号 | 定义位置 |
|------|---------|--------|---------|
| transcript | `transcript_version` | `v1` | `apps/pipeline/transcript/schema.py` |
| semantic | `semantic_version` | `v1` | `apps/pipeline/semantic/schema.py` |
| semantic | `prompt_version` | `v1` | `apps/pipeline/semantic/prompts.py` |
| visual | `visual_version` | `v1` | `apps/pipeline/visual/schema.py` |
| render | `render_version` | `v1` | `apps/pipeline/render/render.py` |

所有版本号硬编码在各模块的 `schema.py` 或 `prompts.py` 中。非破坏性变更不升版本号，破坏性变更须升版本号并在此记录。

---

## 2. Non-Breaking-Change Rules

1. 新增字段 → 允许，须提供默认值（保证向前兼容）
2. 重命名已有字段 → 禁止（破坏下游解析）
3. 修改已有字段类型 → 禁止（破坏下游解析）
4. 修改已有字段语义 → 禁止（例：`ts` 单位不能从秒变毫秒）
5. 删除已有字段 → 禁止（破坏下游解析）。确需删除须升级 `*_version` 至 v2
6. 任何导致下游模块解析失败的变更 = breaking change

**向前兼容性检查清单：**
- 下游模块 `from_dict()` 使用 `.get()` 处理新增字段
- 新增字段不出现在 `required` 数组中
- 不改变已有输出的 `json_schema()` 校验结果

---

## 3. Allowed Evolution Surface

以下变更**允许**在无版本号升级的情况下进行：

| 类别 | 允许 | 示例 |
|------|------|------|
| Visual types | 新增 SVG 类型 | `taxonomy.py` 新增 `timeline_v2` |
| Metadata fields | 新增可选字段 | `metadata.json` 新增 `subtitles_available` |
| Warning types | 新增警告类型字符串 | `warnings` 数组新增 `"large_svg_truncated"` |
| Render theme | 新增 CSS 变量 / 主题 | 新增 `--svg-node-highlight` 等变量 |
| Prompt versions | 新增 prompt 版本 | `prompts.py` 注册 `v2` 入口 |
| Test cases | 新增测试 | 新增 adversarial fixture 或 golden video |
| HTML structure | 新增 CSS class / data 属性 | 不影响 snapshot 对比的增量 |

以下变更**禁止**在无版本号升级的情况下进行：

| 类别 | 禁止 | 后果 |
|------|------|------|
| 删除字段 | 删除任何 schema 必填字段 | breaking change → 版本号升级 |
| 修改字段语义 | 更改字段含义或单位 | 破坏下游解析 |
| Ordering keys | 修改 `sorted()` 的 key 函数 | 破坏 deterministic contract |
| SVG types | 删除已有 SVG 类型 | 破坏已有 visual_plan 兼容性 |
| Layout hints | 修改 `layout_hint` 语义 | 破坏 render 布局 |
| Required fields | 为已有可选字段添加 `required` | 破坏向前兼容 |

---

## 4. Deterministic Ordering Keys

Render 模块保证同输入 → 同 HTML 输出（除 `rendered-at` 时间戳）。以下 sort 键冻结：

| 排序对象 | Sort Key | 位置 |
|---------|----------|------|
| chapters | `ch.id` (string) | `render.py:_build_toc()` |
| visuals | `(v.chapter_id, v.id)` | `render.py:build_html()` |
| TOC visuals | `v.id` (within chapter group) | `render.py:_build_toc()` |
| points | `(point.type, point.content)` | `render.py:_build_chapter_section()` |
| refs | `r.segment_id` | `render.py:_build_point_card()` / `_build_visual_figure()` |
| skipped | `s["chapter_id"]` | `render.py:build_html()` |

**规则：**
- 不依赖 dict insertion order（Python 3.7+）
- 不依赖 filesystem 顺序（`os.listdir()` 等）
- Generator 输出前必须 `sorted()`

---

## 5. Non-Deterministic Fields

以下字段每次运行可能不同，snapshot 对比前须剥离或归一化：

| 文件 | 字段 | 归一化方式 |
|------|------|-----------|
| `metadata.json` | `extracted_at` | 替换为 `"<STRIPPED>"` |
| `index.html` | `<meta name="rendered-at" content="...">` | 替换为 `<meta name="rendered-at" content="<STRIPPED>">` |
| `index.html` | footer `MetaScribe Render v1 · <timestamp>` | 替换为 `MetaScribe Render v1 · <STRIPPED>` |
| `semantic.json` | LLM 生成的 `content` 字段 | 不存全文快照，仅存结构指纹 |
| `visual_plan.json` | LLM 生成的 `data` 对象 | 不存全文快照，仅存结构指纹 |

**注意：** `segments.json` 在相同 Whisper 模型 + 相同音频输入下是确定性的。

---

## 6. Module Output Contracts

### 6.1 metadata.json (ingest → all downstream)

```json
{
  "video_id": "string (required)",
  "title": "string (required)",
  "duration": "number (required, seconds)",
  "uploader": "string (required)",
  "source_url": "string (required)",
  "extracted_at": "string (ISO8601, required, non-deterministic)",
  "description": "string (optional, default '')",
  "chapters": "array (optional, default [])",
  "tags": "array[string] (optional, default [])",
  "view_count": "integer (optional, default 0)",
  "like_count": "integer (optional, default 0)",
  "upload_date": "string (optional, default '')",
  "files": "array[{path, format, size_bytes, duration_seconds?}] (required)",
  "warnings": "array[string] (optional, default [])"
}
```

### 6.2 segments.json (transcript → semantic, render)

```json
{
  "transcript_version": "string (required, 'v1')",
  "video_id": "string (required)",
  "model": "string (required)",
  "language": "string (required)",
  "duration": "number (required, seconds)",
  "segments": "array[{start, end, text, confidence}] (required)",
  "warnings": "array[string] (optional, default [])"
}
```

### 6.3 semantic.json (semantic → visual, render)

```json
{
  "semantic_version": "string (required, 'v1')",
  "prompt_version": "string (required)",
  "video_id": "string (required)",
  "chapters": "array[{id, title, start_ts, end_ts, segment_ids[], points[{type, content, confidence, refs[{segment_id, ts, quote}]}]}] (required)",
  "warnings": "array[string] (optional, default [])",
  "stats": "object (optional)"
}
```

### 6.4 visual_plan.json (visual → render)

```json
{
  "visual_version": "string (required, 'v1')",
  "video_id": "string (required)",
  "visuals": "array[{id, chapter_id, svg_type, title, rationale, trigger_points[], data{}, semantic_refs[{segment_id, ts, quote}], layout_hint, confidence}] (required)",
  "skipped": "array[{chapter_id, reason}] (required)",
  "stats": "object (required)",
  "warnings": "array[string] (optional, default [])"
}
```

### 6.5 index.html (render → terminal output)

- `<meta name="generator" content="MetaScribe render v1">`
- `<meta name="render-version" content="v1">`
- `<meta name="prompt-version" content="...">`
- `<meta name="rendered-at" content="ISO8601">`
- 内联 CSS 变量暗色模式
- 7 种 SVG 渲染器内联
- 确定性 DOM 结构

---

## 7. Migration Protocol

当必须进行破坏性变更时：

1. 在对应模块的 `schema.py` 中升级 `*_version`（如 `v1` → `v2`）
2. 在本文档第 1 节更新版本号
3. 在本文档底部新增 `## Migration: v1 → v2` 记录变更详情
4. 重新生成所有 golden snapshot（运行 `tests/regress.py --full`）
5. 更新所有下游模块的 `from_dict()` 以兼容新版本
6. 重新运行 `tests/regress.py --quick` 确认所有 MATCH

---

*Frozen at: 2026-05-18. MetaScribe v1.*
