#!/usr/bin/env python3
"""Build the two voiceover outputs:

  04_output/02_audio/voiceover_clean.mp3       - untouched narration copy
  04_output/02_audio/voiceover_for_timeline.wav - same narration, but with
      silence inserted everywhere a PAUSE VO / INSERT REAL CLIP (or a
      PRE-VO cold-open shot) sits in the final project timeline, so that
      dropping this file under the numbered clips in CapCut lines up
      automatically.

Run after 01_build_media_map.py.
"""
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

SAMPLE_RATE = 48000


def make_silence(out_path, duration):
    common.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"anullsrc=channel_layout=stereo:sample_rate={SAMPLE_RATE}",
        "-t", f"{max(0.02, duration):.3f}", "-c:a", "pcm_s16le", str(out_path),
    ], capture_output=True, text=True)


def make_vo_slice(out_path, start, end):
    common.run([
        "ffmpeg", "-y", "-i", str(common.MASTER_VO_MP3),
        "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
        "-ar", str(SAMPLE_RATE), "-ac", "2", "-c:a", "pcm_s16le", str(out_path),
    ], capture_output=True, text=True)


def main():
    common.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    seg_dir = common.WORKING_DIR / "vo_segments"
    if seg_dir.exists():
        shutil.rmtree(seg_dir)
    seg_dir.mkdir(parents=True)

    manifest = json.loads((common.WORKING_DIR / "manifest.json").read_text())
    clips = manifest["clips"]

    # --- voiceover_clean.mp3 -------------------------------------------------
    clean_path = common.AUDIO_DIR / "voiceover_clean.mp3"
    common.run([
        "ffmpeg", "-y", "-i", str(common.MASTER_VO_MP3),
        "-c:a", "libmp3lame", "-q:a", "2", str(clean_path),
    ], capture_output=True, text=True)

    # --- voiceover_for_timeline.wav ------------------------------------------
    seg_files = []
    for clip in clips:
        seg_path = seg_dir / f"{clip['clip_number']:03d}.wav"
        cat = clip["audio_use_category"]
        if cat == "OVERLAY" and clip["vo_start"] is not None and clip["vo_end"] is not None:
            make_vo_slice(seg_path, clip["vo_start"], clip["vo_end"])
        else:
            # PRE_VO cold-open shots and INSERT clips get silence here —
            # the insert clip's own audio (if any) plays from the clip itself.
            make_silence(seg_path, clip["duration"])
        seg_files.append(seg_path)

    concat_list = seg_dir / "concat_list.txt"
    with open(concat_list, "w") as f:
        for seg in seg_files:
            f.write(f"file '{seg.resolve()}'\n")

    timeline_wav = common.AUDIO_DIR / "voiceover_for_timeline.wav"
    common.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c:a", "pcm_s16le", str(timeline_wav),
    ], capture_output=True, text=True)

    out_duration = common.ffprobe_duration(timeline_wav)
    expected = manifest["total_project_duration"]
    print(f"Wrote {clean_path}")
    print(f"Wrote {timeline_wav}")
    print(f"  Expected total project duration: {expected:.3f}s")
    print(f"  Actual voiceover_for_timeline.wav duration: {out_duration:.3f}s" if out_duration else "  WARNING: could not read output duration")
    if out_duration and abs(out_duration - expected) > 0.5:
        print("  WARNING: durations differ by more than 0.5s — check segment generation.")


if __name__ == "__main__":
    main()
