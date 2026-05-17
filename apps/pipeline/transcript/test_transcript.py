"""transcript 模块测试。固定测试视频，验证输出正确性。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from transcript import transcribe_ingest_output, ffprobe_duration
from schema import Transcript, Segment

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # MetaScribe/

TEST_CASES = [
    # (video_id, model, language_hint, label, required)
    ("jNQXAC9IVRw",   "small.en", None,  "YouTube 英文 (短, 19s)",   True),
    ("BV1Js596dEnT",  "turbo",    "zh",  "B站 中文 (中, 8min)",       True),
    # 长视频测试需单独提供 URL，通过 ingest 产出后再运行
]


def test_transcribe(video_id: str, model: str, language: str | None, label: str):
    print(f"\n{'='*60}")
    print(f"测试: {label}")
    print(f"video_id: {video_id}, model: {model}, language: {language}")

    # 1. 运行转录
    result = transcribe_ingest_output(video_id, str(PROJECT_ROOT), model_name=model, language=language)
    output_dir = PROJECT_ROOT / "outputs" / video_id

    print("\n--- segments.json (片段摘要) ---")
    print(f"segments: {len(result['segments'])}")
    for s in result["segments"][:8]:
        conf_str = f", conf={s['confidence']:.2f}" if s['confidence'] is not None else ""
        print(f"  [{s['start']:6.1f}-{s['end']:6.1f}] {s['text'][:100]}{conf_str}")
    if len(result["segments"]) > 8:
        print(f"  ... 共 {len(result['segments'])} 段")

    print(f"\nmodel: {result['model']}")
    print(f"language: {result['language']}")
    print(f"duration: {result['duration']:.1f}s")
    print(f"warnings: {result['warnings']}")

    # 2. 验证 segments.json 已生成
    seg_path = output_dir / "segments.json"
    assert seg_path.exists(), "segments.json 未生成"
    print(f"\n[PASS] segments.json 已生成 ({seg_path.stat().st_size} bytes)")

    # 3. 验证 schema
    with open(seg_path, encoding="utf-8") as f:
        raw = json.load(f)
    transcript = Transcript.from_dict(raw)
    print(f"[PASS] schema 校验通过")

    # 4. 必填字段
    assert transcript.video_id == video_id
    assert transcript.model == model
    assert transcript.language
    assert transcript.duration > 0
    assert len(transcript.segments) > 0
    print(f"[PASS] 必填字段: model={transcript.model}, lang={transcript.language}, {len(transcript.segments)} segments")

    # 5. 最后 segment.end 与音频时长校验
    last_end = transcript.segments[-1].end
    audio_duration = result["duration"]
    deviation = abs(last_end - audio_duration)
    print(f"[PASS] 最后 segment.end={last_end:.1f}s, 音频时长={audio_duration:.1f}s, 偏差={deviation:.1f}s")

    # 偏差 >5s 触发 warning
    if deviation > 5.0:
        assert any("最后 segment" in w for w in transcript.warnings), "大偏差未出现在 warnings 中"
        print(f"[PASS] 大偏差已记录到 warnings")
    else:
        print(f"[PASS] 偏差在合理范围")

    # 6. segments 按时间序
    for i in range(1, len(transcript.segments)):
        assert transcript.segments[i].start >= transcript.segments[i-1].start - 0.05, \
            f"segments 时间序异常: [{i}] start={transcript.segments[i].start}"
    print(f"[PASS] segments 时间序正确")

    # 7. 无空文本
    empty = [s for s in transcript.segments if not s.text.strip()]
    assert not empty, f"{len(empty)} 个空文本 segment"
    print(f"[PASS] 无空文本 segment")

    # 8. JSON Schema 导出
    schema = Transcript.json_schema()
    assert "$schema" in schema
    print(f"[PASS] JSON Schema 导出")

    print(f"\n{label} 全部测试通过 [OK]")


if __name__ == "__main__":
    passed = 0
    failed = 0
    for video_id, model, lang, label, required in TEST_CASES:
        try:
            test_transcribe(video_id, model, lang, label)
            passed += 1
        except Exception as e:
            print(f"\n[FAIL] {label}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*60}")
    print(f"结果: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
