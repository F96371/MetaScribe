# AI Video Factory Dev Status

---

# Overall Progress

| Module | Status | Progress | Last Update |
|---|---|---|---|
| ingest | DONE | 100% | 2026-05-17 |
| transcript | DONE | 100% | 2026-05-17 |
| semantic | TODO | 0% | - |
| visual | TODO | 0% | - |
| render | TODO | 0% | - |

---

# Current Focus

ingest 模块已稳定完成，可进入 transcript 模块开发。

---

# Current Blocking

暂无阻塞。

---

# Latest Update

## 2026-05-17 (transcript)

- transcript 模块开发完成
- Whisper 转录 + 时间戳对齐
- segments.json schema 契约
- 时长校验（last segment.end vs audio duration）
- zh (turbo) / en (small.en) 双模型
- 短(19s) / 中(8min) / 长(53min) 三级测试通过
- warnings 机制：顺序/重叠/偏差/空文本/低置信度

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
