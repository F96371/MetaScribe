"""transcript 模块 —— 语音转录。

输入：outputs/{video_id}/metadata.json + audio.mp3
输出：outputs/{video_id}/segments.json

技术：Whisper
目录：apps/pipeline/transcript/
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import whisper

from schema import Transcript, Segment

# 语言 → 推荐模型
LANG_MODEL = {
    "zh": "turbo",
    "en": "small.en",
    "ja": "turbo",
    "ko": "turbo",
    "auto": "turbo",
}

FFPROBE = "ffprobe"


def ffprobe_duration(audio_path: Path) -> float:
    cmd = [
        FFPROBE, "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(audio_path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {r.stderr.strip()}")
    return float(r.stdout.strip())


def transcribe(audio_path: Path, model_name: str, language: Optional[str] = None) -> dict:
    """运行 Whisper 转录。返回原始 result dict。"""
    model = whisper.load_model(model_name)
    opts = {}
    if language and language != "auto":
        opts["language"] = language
    result = model.transcribe(str(audio_path), **opts)
    return result


def validate_segments(segments: list[Segment], audio_duration: float) -> list[str]:
    """校验 segments，返回 warnings 列表。"""
    warnings = []
    if not segments:
        warnings.append("转录结果为空，无 segments")
        return warnings

    # 1. 检查顺序
    for i in range(1, len(segments)):
        if segments[i].start < segments[i-1].start:
            warnings.append(f"segments 顺序异常: [{i}] start={segments[i].start} < [{i-1}] start={segments[i-1].start}")

    # 2. 检查重叠
    for i in range(1, len(segments)):
        if segments[i].start < segments[i-1].end - 0.01:  # 10ms tolerance
            warnings.append(f"segments 重叠: [{i-1}] end={segments[i-1].end:.2f} > [{i}] start={segments[i].start:.2f}")

    # 3. 最后一个 end 与音频时长偏差
    last_end = segments[-1].end
    if audio_duration > 0:
        deviation = abs(last_end - audio_duration)
        if deviation > 5.0:  # >5s 偏差
            warnings.append(f"最后 segment.end ({last_end:.1f}s) 与音频时长 ({audio_duration:.1f}s) 偏差 {deviation:.1f}s")

    # 4. 空文本
    empty_count = sum(1 for s in segments if not s.text.strip())
    if empty_count > 0:
        warnings.append(f"{empty_count} 个 segment 文本为空")

    # 5. 低置信度 (avg_logprob < -1.0 为可疑)
    low_conf = [s for s in segments if s.confidence is not None and s.confidence < -1.0]
    if low_conf:
        warnings.append(f"{len(low_conf)} 个 segment avg_logprob < -1.0")

    return warnings


def build_output(metadata_path: Path, model_name: str = "turbo", language: Optional[str] = None) -> Transcript:
    """主流程：读取 ingest 输出 → 转录 → 校验 → 输出 segments.json。"""
    # 1. 读取 ingest 输出
    with open(metadata_path, encoding="utf-8") as f:
        metadata = json.load(f)

    video_id = metadata["video_id"]
    audio_duration = metadata["duration"]
    output_dir = metadata_path.parent
    audio_path = output_dir / "audio.mp3"

    if not audio_path.exists():
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

    # 2. 校验音频时长一致性
    actual_duration = ffprobe_duration(audio_path)
    if abs(actual_duration - audio_duration) > 1.0:
        print(f"[WARN] metadata.duration ({audio_duration:.1f}s) 与 ffprobe ({actual_duration:.1f}s) 偏差 {abs(actual_duration - audio_duration):.1f}s")

    # 3. 运行 Whisper
    print(f"[INFO] 模型: {model_name}, 音频: {actual_duration:.1f}s")
    raw = transcribe(audio_path, model_name=model_name, language=language)

    detected_lang = raw.get("language", language or "unknown")

    # 4. 构建 segments (Whisper 原生输出，未做 merge/split/chunk)
    segments = [
        Segment(
            id=i,
            start=s["start"],
            end=s["end"],
            text=s["text"].strip(),
            confidence=round(s.get("avg_logprob", 0), 4),
        )
        for i, s in enumerate(raw.get("segments", []))
    ]

    # 5. stats
    total_chars = sum(len(s.text) for s in segments)
    stats = {
        "segment_count": len(segments),
        "char_count": total_chars,
    }

    # 6. 校验
    warnings = validate_segments(segments, actual_duration)

    transcript = Transcript(
        transcript_version="v1",
        video_id=video_id,
        model=model_name,
        language=detected_lang,
        duration=actual_duration,
        segments=segments,
        stats=stats,
        warnings=warnings,
    )

    # 7. 输出
    transcript.to_json(output_dir / "segments.json")
    return transcript


def transcribe_ingest_output(video_id: str, project_root: str | Path, model_name: str = "turbo", language: Optional[str] = None) -> dict:
    """便捷入口：给定 video_id，自动找到 outputs/{video_id}/metadata.json 并转录。"""
    root = Path(project_root)
    meta_path = root / "outputs" / video_id / "metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"metadata.json 不存在: {meta_path}")
    transcript = build_output(meta_path, model_name=model_name, language=language)
    return transcript.to_dict()


# ---- CLI ----
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python transcript.py <video_id> [project_root] [model] [language]", file=sys.stderr)
        print("示例: python transcript.py jNQXAC9IVRw", file=sys.stderr)
        print("示例: python transcript.py BV1Js596dEnT . turbo zh", file=sys.stderr)
        sys.exit(1)

    vid = sys.argv[1]
    root = sys.argv[2] if len(sys.argv) > 2 else "."
    model = sys.argv[3] if len(sys.argv) > 3 else "turbo"
    lang = sys.argv[4] if len(sys.argv) > 4 else None

    try:
        result = transcribe_ingest_output(vid, root, model_name=model, language=lang)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"TRANSCRIPT FAILED: {e}", file=sys.stderr)
        sys.exit(1)
