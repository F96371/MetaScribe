# V1 Roadmap

## Phase 1 — ingest (COMPLETE)

- [x] 视频 URL 解析 (YouTube + B站)
- [x] 元信息提取 (yt-dlp) + video_id
- [x] 音频下载 mp3
- [x] 封面下载 + 统一转 jpg
- [x] ffprobe 时长校验
- [x] metadata.json schema 契约

---

## Phase 2 — transcript (DONE)

- [x] Whisper 转录 (openai-whisper)
- [x] segments.json schema 契约
- [x] 时间戳对齐校验
- [x] 多语言支持（中文 turbo / 英文 small.en）
- [x] 短/中/长 三级视频测试 (19s / 8min / 53min)
- [x] warnings 机制

---

## Phase 3 — semantic

- [ ] 章节结构化
- [ ] 问题 / 陷阱 / 步骤 / 结论 拆解
- [ ] 信息密度控制
- [ ] chapters.json

---

## Phase 4 — visual

- [ ] visual intent 推断
- [ ] 图类型自动判断
- [ ] SVG schema
- [ ] visual.json

---

## Phase 5 — render

- [ ] HTML 模板
- [ ] CSS 样式
- [ ] SVG 渲染
- [ ] Playwright 截图
- [ ] index.html + full.png
