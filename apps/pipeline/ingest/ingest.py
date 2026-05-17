"""ingest 模块 —— 视频摄取。

输入：视频 URL
输出：outputs/{video_id}/
      ├── metadata.json
      ├── audio.mp3
      └── cover.jpg

目录：apps/pipeline/ingest/
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from schema import Metadata, MediaFile, Chapter, OUTPUT_ROOT

# ---- 配置 ----
YT_DLP = "yt-dlp"
FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"


def run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    """运行 shell 命令，遇错即停。"""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"命令超时 ({timeout}s): {' '.join(cmd)}")


def extract_info(url: str) -> dict:
    """用 yt-dlp 提取视频元信息，不下载。"""
    cmd = [
        YT_DLP,
        "--dump-json",
        "--no-download",
        "--no-playlist",
        url,
    ]
    result = run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp 提取信息失败: {result.stderr.strip()}")
    return json.loads(result.stdout.strip())


def download_audio(url: str, output_dir: Path) -> Path:
    """下载音频为 mp3。"""
    tmpl = str(output_dir / "audio.%(ext)s")
    cmd = [
        YT_DLP,
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "-o", tmpl,
        "--no-playlist",
        url,
    ]
    result = run(cmd, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"音频下载失败: {result.stderr.strip()}")

    mp3_files = list(output_dir.glob("audio.*"))
    if not mp3_files:
        raise FileNotFoundError(f"未找到音频输出文件: {output_dir}")
    return mp3_files[0]


def download_thumbnail(url: str, output_dir: Path) -> Path | None:
    """下载封面图并统一转换为 jpg。"""
    tmpl = str(output_dir / "cover_temp.%(ext)s")
    cmd = [
        YT_DLP,
        "--write-thumbnail",
        "--skip-download",
        "-o", tmpl,
        "--no-playlist",
        url,
    ]
    result = run(cmd)
    if result.returncode != 0:
        return None

    found = None
    for ext in ("jpg", "webp", "png"):
        candidates = list(output_dir.glob(f"cover_temp.{ext}"))
        if candidates:
            found = candidates[0]
            break
    if not found:
        return None

    cover_jpg = output_dir / "cover.jpg"
    convert_cmd = [
        FFMPEG,
        "-i", str(found),
        "-q:v", "2",
        "-y",
        str(cover_jpg),
    ]
    conv = run(convert_cmd)
    found.unlink(missing_ok=True)
    if conv.returncode != 0:
        return found if found.exists() else None
    return cover_jpg if cover_jpg.exists() else None


def ffprobe_duration(filepath: Path) -> float:
    """用 ffprobe 获取实际时长。"""
    cmd = [
        FFPROBE,
        "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(filepath),
    ]
    result = run(cmd)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {result.stderr.strip()}")
    return float(result.stdout.strip())


def validate_duration(expected: float, actual: float) -> list[str]:
    """校验时长偏差。偏差 >5% 告警。"""
    if expected <= 0:
        return [f"预期时长异常: {expected}s"]
    deviation = abs(expected - actual) / expected
    if deviation > 0.05:
        return [f"时长偏差 {deviation:.1%}: yt-dlp={expected:.1f}s ffprobe={actual:.1f}s"]
    return []


def build_output(url: str, project_root: Path) -> Metadata:
    """主流程：提取 -> 下载 -> 校验 -> 输出到 outputs/{video_id}/。

    返回 Metadata，同时写入 metadata.json。
    """
    # 1. 提取元信息
    info = extract_info(url)

    video_id = info.get("id", info.get("display_id", ""))
    if not video_id:
        raise RuntimeError("无法提取 video_id")

    title = info.get("title", "")
    duration = float(info.get("duration", 0))
    uploader = info.get("uploader", info.get("channel", ""))
    description = info.get("description", "") or ""
    view_count = int(info.get("view_count", 0) or 0)
    like_count = int(info.get("like_count", 0) or 0)
    upload_date = info.get("upload_date", "") or ""
    tags = info.get("tags") or []

    # 章节（平台原生数据，非 ingest 生成）
    chapters_raw = info.get("chapters") or []
    chapters = [
        Chapter(
            start=c.get("start_time", 0),
            end=c.get("end_time", 0),
            title=c.get("title", ""),
            is_generated=False,
        )
        for c in chapters_raw
    ]

    # 2. 固定输出目录 outputs/{video_id}/
    output_dir = project_root / OUTPUT_ROOT / video_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # 3. 下载音频
    audio_path = download_audio(url, output_dir)

    # 4. ffprobe 校验
    actual_duration = ffprobe_duration(audio_path)
    warnings = validate_duration(duration, actual_duration)

    # 5. 下载封面
    thumb_path = download_thumbnail(url, output_dir)

    # 6. 构建文件清单（path 相对于项目根，统一 /）
    files: list[MediaFile] = []
    audio_rel = audio_path.relative_to(project_root).as_posix()
    audio_size = audio_path.stat().st_size
    files.append(MediaFile(
        path=audio_rel,
        format="mp3",
        size_bytes=audio_size,
        duration_seconds=actual_duration,
    ))
    if thumb_path:
        thumb_rel = thumb_path.relative_to(project_root).as_posix()
        thumb_size = thumb_path.stat().st_size
        files.append(MediaFile(
            path=thumb_rel,
            format="jpg",
            size_bytes=thumb_size,
        ))

    metadata = Metadata(
        video_id=video_id,
        title=title,
        duration=actual_duration,
        uploader=uploader,
        source_url=url,
        extracted_at=datetime.now(timezone.utc).isoformat(),
        description=description,
        chapters=chapters,
        tags=tags,
        view_count=view_count,
        like_count=like_count,
        upload_date=upload_date,
        files=files,
        warnings=warnings,
    )

    metadata.to_json(output_dir / "metadata.json")
    return metadata


def ingest(url: str, project_root: str | None = None) -> dict:
    """入口函数：给定 URL，产出 metadata dict。

    输出目录固定为: {project_root}/outputs/{video_id}/
    """
    if project_root is None:
        project_root = str(Path.cwd())
    metadata = build_output(url, Path(project_root))
    return metadata.to_dict()


# ---- CLI ----
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python ingest.py <URL> [project_root]", file=sys.stderr)
        sys.exit(1)

    url = sys.argv[1]
    root = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        result = ingest(url, root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"INGEST FAILED: {e}", file=sys.stderr)
        sys.exit(1)
