"""ingest 模块测试。固定测试 URL，验证输出正确性。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingest import ingest
from schema import Metadata, OUTPUT_ROOT

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # MetaScribe/

TEST_URLS = [
    {
        "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "label": "YouTube (短)",
        "required": True,
    },
    {
        "url": "https://www.bilibili.com/video/BV1Js596dEnT",
        "label": "B站",
        "required": True,
    },
]


def test_ingest_contract(url: str, label: str):
    print(f"\n{'='*60}")
    print(f"测试: {label}")
    print(f"URL: {url}")

    # 1. 运行 ingest
    result = ingest(url, str(PROJECT_ROOT))
    video_id = result["video_id"]
    output_dir = PROJECT_ROOT / OUTPUT_ROOT / video_id
    print(f"输出目录: {output_dir}")

    print("\n--- metadata.json ---")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 2. 验证目录结构
    assert output_dir.exists(), f"输出目录不存在: {output_dir}"
    print(f"\n[PASS] 目录结构: outputs/{video_id}/")

    # 3. 验证 metadata.json
    meta_path = output_dir / "metadata.json"
    assert meta_path.exists(), "metadata.json 未生成"
    with open(meta_path, encoding="utf-8") as f:
        raw = json.load(f)
    metadata = Metadata.from_dict(raw)
    print(f"[PASS] schema 校验通过")

    # 4. 验证必填字段
    assert metadata.video_id == video_id
    assert metadata.title, "title 为空"
    assert metadata.duration > 0, f"duration 异常: {metadata.duration}"
    assert metadata.uploader, "uploader 为空"
    assert metadata.source_url == url
    assert metadata.extracted_at, "extracted_at 为空"
    print(f"[PASS] 必填字段: video_id='{metadata.video_id}', title='{metadata.title}', duration={metadata.duration:.1f}s")

    # 5. files.path 格式验证（统一 / 分隔符）
    for f_item in metadata.files:
        expected_prefix = f"outputs/{video_id}/"
        assert f_item.path.startswith(expected_prefix), \
            f"files.path 格式错误: {f_item.path}"
        full = PROJECT_ROOT / f_item.path
        assert full.exists(), f"文件不存在: {full}"
    print(f"[PASS] files.path 格式: outputs/{video_id}/...")

    # 6. 音频
    audio_files = [f for f in metadata.files if f.format == "mp3"]
    assert audio_files, "未找到 mp3"
    audio = audio_files[0]
    assert audio.duration_seconds and audio.duration_seconds > 0
    print(f"[PASS] 音频: {audio.path} ({audio.size_bytes:,} bytes, {audio.duration_seconds:.1f}s)")

    # 7. 时长一致性
    diff = abs(metadata.duration - audio.duration_seconds)
    assert diff < 1.0, f"时长偏差过大: {diff:.1f}s"
    print(f"[PASS] 时长一致性: 偏差 {diff:.1f}s")

    # 8. 封面
    cover_files = [f for f in metadata.files if f.format == "jpg"]
    if cover_files:
        cover = cover_files[0]
        print(f"[PASS] 封面: {cover.path} ({cover.size_bytes:,} bytes)")
    else:
        print("[WARN] 未生成封面")

    # 9. chapters 来源标记
    for ch in metadata.chapters:
        assert ch.is_generated is False, f"chapters.is_generated 应为 False，实际 {ch.is_generated}"
    print(f"[PASS] chapters.is_generated=False ({len(metadata.chapters)} 个章节，平台原生)")

    # 10. description 来源说明
    print(f"[INFO] description 原始长度: {len(metadata.description)} chars")
    print(f"[INFO] description 来源: yt-dlp 直接提取，非 mock/cache")

    # 11. JSON Schema 导出
    schema = Metadata.json_schema()
    assert "$schema" in schema
    assert "required" in schema
    print(f"[PASS] JSON Schema 导出: {len(schema['required'])} 个必填字段, {len(schema['properties'])} 个属性")

    print(f"\n{label} 全部测试通过 [OK]")


if __name__ == "__main__":
    passed = 0
    failed = 0
    skipped = 0
    for t in TEST_URLS:
        label = t["label"]
        try:
            test_ingest_contract(t["url"], label)
            passed += 1
        except RuntimeError as e:
            msg = str(e)
            if "geo-restricted" in msg or "deleted" in msg:
                print(f"\n[SKIP] {label}: 网络限制 → {msg[:120]}")
                skipped += 1
            else:
                print(f"\n[FAIL] {label}: {e}")
                import traceback; traceback.print_exc()
                failed += 1
        except Exception as e:
            print(f"\n[FAIL] {label}: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    print(f"\n{'='*60}")
    print(f"结果: {passed} passed, {failed} failed, {skipped} skipped")
    if failed:
        sys.exit(1)
