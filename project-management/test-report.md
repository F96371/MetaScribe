# Test Report

## TEST-003 — transcript

日期：2026-05-17

| # | 视频 | 语言 | 模型 | 时长 | segments | deviation | warnings |
|---|------|------|------|------|----------|-----------|----------|
| 1 | Me at the zoo (YouTube) | en | small.en | 19s | 4 | 0.0s | 0 |
| 2 | 浙江宣传 (B站) | zh | turbo | 8.1min | 198 | 1.0s | 0 |
| 3 | MIT Algorithmic Thinking (YouTube) | en | small.en | 53.4min | 868 | 0.4s | 0 |

全部 PASS.

---

## TEST-001 — ingest

视频：
  YouTube: Me at the zoo (jNQXAC9IVRw)

日期：2026-05-16 / 复测 2026-05-17

结果：
- metadata.json：PASS
- video_id：PASS (jNQXAC9IVRw)
- schema 校验：PASS
- 音频下载：PASS (mp3, 331KB, 19.0s)
- 时长一致性：PASS (偏差 0.0s)
- 封面下载：PASS (cover.jpg, 41KB)
- 章节提取：PASS (3 chapters)

备注：
  首个 YouTube 视频（最短公开视频，适合快速回归测试）

---

## TEST-002

视频：
  B站: BV1uT4y1P7CX

日期：2026-05-17

结果：
- SKIP（当前网络 geo-restricted，yt-dlp 原生 BiliBili extractor 支持 B站）
- 需在国内网络或 VPN 环境测试

备注：
  B站测试依赖网络环境，非代码缺陷
