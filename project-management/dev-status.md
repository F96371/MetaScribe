# AI Video Factory Dev Status

---

# Overall Progress

| Module | Status | Progress | Last Update |
|---|---|---|---|
| ingest | DONE | 100% | 2026-05-17 |
| transcript | DONE | 100% | 2026-05-17 |
| semantic | DONE | 100% | 2026-05-17 |
| visual | DONE | 100% | 2026-05-18 |
| render | DONE | 100% | 2026-05-18 |
| stabilization | DONE | 100% | 2026-05-18 |

---

# Current Focus

render 模块已完成，全部 5 个终端流水线开发完毕。Stabilization 完成，进入维护模式。

---

# Current Blocking

暂无阻塞。

---

# Latest Update

## 2026-05-18 (stabilization)

- Stabilization phase 完成
- CONTRACTS.md：合约冻结文档（7 章节 + allowed evolution surface）
- Golden Dataset：3 个永久回归基线 (jNQXAC9IVRw / BV1Js596dEnT / HtSuA80QTyo)
- golden/snapshots/：全量快照 (metadata / segments / index.html) + 结构指纹 (semantic.snapshot / visual.snapshot)
- golden/manifests/：每个视频的 metrics + hash 基线
- golden/fixtures/：6 个 adversarial bad-path fixture
- golden/baselines/perf-baseline.json：性能基线（relative, ratio-based）
- tests/utils.py：指纹提取 / 归一化 / 三级 diff / metrics 计算
- tests/snapshot.py：snapshot 对比（HARD FAIL / SOFT DRIFT / INFO）+ --json 模式
- tests/perf.py：性能收集 + ratio-based 对比
- tests/regress.py：一键回归 (--quick <10s / --full) + --json CI 模式
- --quick: 12/12 schema PASS, 15/15 MATCH, 3/3 deterministic PASS, 6/6 adversarial PASS
- 总耗时 0.1s (--quick 模式)

## 2026-05-17 (transcript)

- transcript 模块开发完成
- Whisper 转录 + 时间戳对齐
- segments.json schema 契约
- 时长校验（last segment.end vs audio duration）
- zh (turbo) / en (small.en) 双模型
- 短(19s) / 中(8min) / 长(53min) 三级测试通过
- warnings 机制：顺序/重叠/偏差/空文本/低置信度

## 2026-05-18 (render)

- render 模块开发完成
- 输入：outputs/{video_id}/metadata.json + semantic.json + visual_plan.json + segments.json
- 输出：outputs/{video_id}/index.html（单文件离线 HTML，零外部依赖）
- 4 文件结构：schema.py（输入数据模型）/ svg_renderers.py（7 种 SVG 渲染器）/ render.py（HTML 组装器）/ test_render.py（测试）
- 7 种 SVG 渲染器：flowchart / matrix / timeline / chain / layered / decision_tree / checklist
- CSS 变量暗色模式：prefers-color-scheme 自动 + data-theme 手动切换
- 响应式布局：桌面 sticky 侧边栏 / 平板折叠 TOC / 手机单列
- 时间戳导航：#t=123.5 hash + JS 点击定位 + 再次点击复制
- Print CSS：@page A4, break-inside: avoid 禁止打印断裂
- 安全转义：_escape_html() 统一处理 HTML/SVG/属性值
- 确定性排序：chapters/visuals/points/refs 全部 sorted()，同输入→同输出
- 渲染元数据：<meta> generator / render-version / prompt-version / rendered-at
- SVG 文本预换行：_wrap_text() Python 端计算 + <tspan> 输出，最大 5 行
- HTML 体积控制：SVG 节点数限制 + SegmentRef quote 40 字符 + 总 < 2MB
- 14 项测试全部通过
- 3 个真实 HTML 输出生成并验证

### 三级测试结果

| 视频 | 时长 | 章节 | Visuals | SVG | Points | HTML 大小 |
|------|------|------|---------|-----|--------|-----------|
| Me at the zoo (en) | 19s | 2 | 0 | 0 | 1 | 15 KB |
| 浙江宣传 (zh) | 8.1min | 4 | 4 | 4 | 44 | 73 KB |
| MIT 6.006 (en) | 53.4min | 9 | 9 | 9 | 95 | 108 KB |

## 2026-05-18 (visual)

- visual 模块开发完成
- visual_plan.json schema 契约（VisualPlan / VisualSpec / SegmentRef）
- SVG taxonomy 7 类：flowchart / matrix / timeline / chain / layered / decision_tree / checklist
- 规则路由：semantic type 分布 → SVG 类型决策（7 条优先级规则）
- LLM 填充：类型决定 → 数据模板 → LLM 生成具体节点/边/项
- fallback：<3 点章节自动跳过，无合适类型不强制
- JSON 容错 + 空响应重试
- 短(0 visuals) / 中(4 visuals) / 长(9 visuals) 三级测试通过

### 三级测试结果

| 视频 | 时长 | 章节 | Visuals | Skipped | Coverage | Types |
|------|------|------|---------|---------|----------|-------|
| Me at the zoo (en) | 19s | 2 | 0 | 2 | 0% | — (正确跳过) |
| 浙江宣传 (zh) | 8.1min | 4 | 4 | 0 | 100% | decision_tree:1, chain:1, matrix:2 |
| MIT 6.006 (en) | 53.4min | 9 | 9 | 0 | 100% | flowchart:5, chain:3, layered:1 |

## 2026-05-17 (semantic)

- semantic 模块开发完成
- semantic.json schema 契约（Semantic / Chapter / InfoPoint / SegmentRef）
- 5 类信息点拆解：problem / step / pitfall / conclusion / context
- 逐章节 LLM 提取（优先 metadata 原生章节 → LLM 检测回退）
- LLM Provider 抽象层（Anthropic-compatible / DeepSeek 等，全可配）
- Prompt 版本管理（prompts.py + PROMPTS 注册表）
- 三级 JSON 解析容错（直接 → markdown → 最外层 {}）
- warnings：低置信度 / 空章节 / JSON 容错 / 提取异常
- 短(19s/1pt) / 中(8min/44pts) / 长(53min/95pts) 三级测试通过

### 三级测试结果

| 视频 | 时长 | 章节 | 信息点 | type 分布 | PASS |
|------|------|------|--------|-----------|------|
| Me at the zoo (en) | 19s | 2 | 1 | context:1 | PASS |
| 浙江宣传 (zh) | 8.1min | 4 | 44 | problem:13 conclusion:16 context:9 pitfall:4 step:2 | PASS |
| MIT 6.006 (en) | 53.4min | 9 | 95 | context:32 conclusion:28 step:21 problem:11 pitfall:3 | PASS |

## 2026-05-17 (ingest)

- ingest 模块最终完善
- 新增 video_id 字段（schema 契约更新）
- 封面统一转换为 cover.jpg（ffmpeg webp→jpg）
- B站支持（yt-dlp 原生 BiliBili extractor，需国内网络）
- 测试：YouTube PASS, B站 geo-skip
- 所有必填字段完整，时长校验正常

## 2026-05-16

- ingest 模块初始开发完成
- yt-dlp 视频信息提取
- 音频下载 mp3
- 封面下载
- ffprobe 时长校验（偏差 < 5%）
- schema 契约定义完成
- 测试通过（YouTube test URL: jNQXAC9IVRw）
