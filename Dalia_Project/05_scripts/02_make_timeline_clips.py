#!/usr/bin/env python3
"""Render 04_output/01_timeline_clips/NNN.mp4 for every clip in
03_working/manifest.json.

- Real matched images -> exact-duration MP4 with a restrained zoom.
- Real matched videos -> trimmed/scaled/padded MP4, source audio kept only
  for INSERT clips, muted otherwise. Freezes the last frame if the source is
  too short.
- Original/editor-created graphics (title cards, timelines, lower-thirds,
  etc.) -> generated directly as a clean text card.
- Anything unmatched -> an obvious "MISSING MEDIA" placeholder slate, logged
  in the missing-media report.

Run after 01_build_media_map.py.
"""
import json
import shutil
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
if not Path(FONT_REGULAR).exists():
    FONT_REGULAR = FONT_BOLD = None  # fall back to fontconfig default lookup

SILENT_AUDIO = ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
V_ENCODE = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(common.FPS)]
A_ENCODE = ["-c:a", "aac", "-b:a", "160k"]


def wrap(text, width=46):
    if not text:
        return []
    return textwrap.wrap(text.strip(), width=width) or []


def text_layers(lines):
    """lines: list of (text, fontsize, color, bold). Returns chained drawtext filter."""
    total_h = sum(int(fs * 1.5) for _, fs, _, _ in lines)
    y = f"(h-{total_h})/2"
    filters = []
    cum = "0"
    for text, fontsize, color, bold in lines:
        font = FONT_BOLD if bold else FONT_REGULAR
        font_opt = f"fontfile='{font}':" if font else ""
        esc = common.drawtext_escape(text)
        filters.append(
            f"drawtext={font_opt}text='{esc}':fontsize={fontsize}:fontcolor={color}:"
            f"x=(w-text_w)/2:y={y}+({cum})"
        )
        cum += f"+{int(fontsize * 1.5)}"
    return ",".join(filters)


def make_slate_clip(out_path, duration, title, subtitle, body, footer, bg="0x1c2028", accent="0xffffff"):
    lines = []
    if title:
        lines.append((title, 60, accent, True))
    if subtitle:
        lines.append((subtitle, 34, "0xaaaaaa", False))
    if body:
        lines.append(("", 20, "0x000000", False))  # spacer
        for line in wrap(body, 50)[:6]:
            lines.append((line, 30, "0xdddddd", False))
    if footer:
        lines.append(("", 20, "0x000000", False))
        for line in wrap(footer, 60)[:3]:
            lines.append((line, 22, "0x888888", False))

    vf = text_layers(lines)
    d = max(0.5, duration)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c={bg}:s={common.WIDTH}x{common.HEIGHT}:d={d}:r={common.FPS}",
        *SILENT_AUDIO,
        "-vf", vf,
        "-t", f"{d}",
        *V_ENCODE, *A_ENCODE,
        "-shortest",
        str(out_path),
    ]
    common.run(cmd, capture_output=True, text=True)


def make_missing_media_clip(out_path, duration, clip):
    beat = f"Beat {clip['beat_order']}.{clip['visual_number']}"
    make_slate_clip(
        out_path, duration,
        title="MISSING MEDIA",
        subtitle=f"{beat} — {clip.get('section') or ''}",
        body=clip.get("what_goes_on_screen") or "",
        footer=f"Source needed: {clip.get('source_name') or 'unspecified'}",
        bg="0x3a1414", accent="0xff6b6b",
    )


def make_graphic_clip(out_path, duration, clip):
    beat = f"Beat {clip['beat_order']}.{clip['visual_number']}"
    make_slate_clip(
        out_path, duration,
        title=clip.get("what_goes_on_screen") or clip.get("source_name") or "",
        subtitle=beat,
        body=None,
        footer="Original graphic — refine styling in CapCut",
        bg="0x14161c", accent="0xffffff",
    )


def make_image_clip(out_path, duration, image_path):
    d = max(0.5, duration)
    frames = max(2, round(d * common.FPS))
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", f"{d}", "-i", str(image_path),
        "-f", "lavfi", "-t", f"{d}", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-filter_complex",
        (
            f"[0:v]scale={common.WIDTH * 2}:{common.HEIGHT * 2}:force_original_aspect_ratio=increase,"
            f"crop={common.WIDTH * 2}:{common.HEIGHT * 2},"
            f"zoompan=z='min(zoom+0.0007,1.06)':d={frames}:s={common.WIDTH}x{common.HEIGHT}:fps={common.FPS},"
            f"format=yuv420p,setsar=1[v]"
        ),
        "-map", "[v]", "-map", "1:a",
        *V_ENCODE, *A_ENCODE,
        "-shortest",
        str(out_path),
    ]
    common.run(cmd, capture_output=True, text=True)


def make_video_clip(out_path, duration, video_path, keep_audio):
    d = max(0.5, duration)
    src_duration = common.ffprobe_duration(video_path) or d
    needs_freeze = src_duration < d

    vf = (
        f"scale={common.WIDTH}:{common.HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={common.WIDTH}:{common.HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={common.FPS}"
    )
    if needs_freeze:
        vf += f",tpad=stop_mode=clone:stop_duration={max(0.0, d - src_duration):.3f}"

    cmd = ["ffmpeg", "-y", "-i", str(video_path)]
    filter_parts = [f"[0:v]{vf}[v]"]
    if keep_audio:
        # Pad source audio with silence too, so a freeze-extended video isn't
        # cut short by "-shortest" truncating to the original (shorter) track.
        filter_parts.append(f"[0:a]apad,atrim=0:{d}[a]")
    else:
        cmd += SILENT_AUDIO
        filter_parts.append(f"[1:a]atrim=0:{d}[a]")
    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[v]", "-map", "[a]",
        "-t", f"{d}", *V_ENCODE, *A_ENCODE, str(out_path),
    ]
    common.run(cmd, capture_output=True, text=True)


def main():
    common.CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    for f in common.CLIPS_DIR.glob("*.mp4"):
        f.unlink()

    manifest = json.loads((common.WORKING_DIR / "manifest.json").read_text())
    clips = manifest["clips"]

    counts = {"image": 0, "video": 0, "graphic": 0, "missing": 0}

    for clip in clips:
        out_path = common.CLIPS_DIR / clip["clip_filename"]
        duration = clip["duration"]

        if clip["is_graphic"]:
            make_graphic_clip(out_path, duration, clip)
            counts["graphic"] += 1
        elif clip["chosen_local_file"]:
            src = common.SOURCE_MEDIA_DIR / clip["chosen_local_file"]
            ext = src.suffix.lower()
            if ext in common.IMAGE_EXTS:
                make_image_clip(out_path, duration, src)
                counts["image"] += 1
            elif ext in common.VIDEO_EXTS:
                make_video_clip(out_path, duration, src, keep_audio=clip["uses_source_audio"])
                counts["video"] += 1
            else:
                # Documents (e.g. raw PDFs) aren't directly renderable by
                # ffmpeg — export the page as an image first. Fall back to a
                # labeled placeholder rather than guessing.
                make_missing_media_clip(out_path, duration, clip)
                counts["missing"] += 1
        else:
            make_missing_media_clip(out_path, duration, clip)
            counts["missing"] += 1

        if not out_path.exists():
            print(f"  WARNING: ffmpeg did not produce {out_path.name}")

    print(f"Rendered {len(clips)} clips into {common.CLIPS_DIR}")
    print(f"  From real images:  {counts['image']}")
    print(f"  From real videos:  {counts['video']}")
    print(f"  Generated graphics: {counts['graphic']}")
    print(f"  Missing-media placeholders: {counts['missing']}")


if __name__ == "__main__":
    main()
