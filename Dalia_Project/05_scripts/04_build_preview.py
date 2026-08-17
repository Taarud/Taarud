#!/usr/bin/env python3
"""Concatenate the numbered timeline clips and mix in the timeline-adjusted
voiceover to produce a single QC roughcut:

  04_output/03_preview/roughcut_preview.mp4

Each clip already carries its own audio track (real source audio for INSERT
clips, silence everywhere else), and voiceover_for_timeline.wav carries
narration everywhere except where an INSERT clip's own audio should be
heard. Concatenating the clips and mixing that combined track against the
timeline-adjusted voiceover therefore reproduces the intended edit without
double-narration or dead air.

Run after 02_make_timeline_clips.py and 03_build_timeline_voiceover.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def main():
    common.PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

    clip_paths = sorted(common.CLIPS_DIR.glob("*.mp4"))
    if not clip_paths:
        print("No timeline clips found in 04_output/01_timeline_clips/ — run 02_make_timeline_clips.py first.")
        sys.exit(1)

    concat_list = common.WORKING_DIR / "clips_concat_list.txt"
    with open(concat_list, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")

    clips_concat = common.WORKING_DIR / "clips_concat.mp4"
    print(f"Concatenating {len(clip_paths)} clips...")
    common.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-r", str(common.FPS), "-c:a", "aac", "-b:a", "160k",
        str(clips_concat),
    ], capture_output=True, text=True)

    timeline_wav = common.AUDIO_DIR / "voiceover_for_timeline.wav"
    out_path = common.PREVIEW_DIR / "roughcut_preview.mp4"

    if timeline_wav.exists():
        print("Mixing clip audio with the timeline-adjusted voiceover...")
        common.run([
            "ffmpeg", "-y", "-i", str(clips_concat), "-i", str(timeline_wav),
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=0[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            str(out_path),
        ], capture_output=True, text=True)
    else:
        print("WARNING: voiceover_for_timeline.wav not found — copying video-only preview.")
        common.run(["ffmpeg", "-y", "-i", str(clips_concat), "-c", "copy", str(out_path)],
                    capture_output=True, text=True)

    dur = common.ffprobe_duration(out_path)
    print(f"Wrote {out_path}" + (f" ({dur:.1f}s)" if dur else ""))


if __name__ == "__main__":
    main()
