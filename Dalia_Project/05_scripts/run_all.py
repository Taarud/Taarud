#!/usr/bin/env python3
"""Run the full CapCut assembly kit pipeline end to end.

  00_scan_media.py            -> inventory 02_source_media/
  01_build_media_map.py       -> classify CSV rows, match media, compute timeline
  02_make_timeline_clips.py   -> render 001.mp4 ... NNN.mp4
  03_build_timeline_voiceover.py -> voiceover_clean.mp3 + voiceover_for_timeline.wav
  04_build_preview.py         -> roughcut_preview.mp4
  05_build_captions.py        -> captions.srt
  06_write_reports.py         -> assembly_report.txt, missing_media_report.txt,
                                  capcut_import_steps.txt + QC checks

Usage:  python3 05_scripts/run_all.py
"""
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = [
    "00_scan_media.py",
    "01_build_media_map.py",
    "02_make_timeline_clips.py",
    "03_build_timeline_voiceover.py",
    "04_build_preview.py",
    "05_build_captions.py",
    "06_write_reports.py",
]


def main():
    script_dir = Path(__file__).resolve().parent

    for exe in ("ffmpeg", "ffprobe"):
        if shutil.which(exe) is None:
            print(f"ERROR: '{exe}' was not found on PATH.")
            print("Install FFmpeg first (https://ffmpeg.org/download.html) and re-run.")
            sys.exit(1)

    root = script_dir.parent
    for required in [
        root / "01_input" / "CodeCopper_Dalia_Visual_Coverage_AUDIO_ALIGNED.csv",
        root / "01_input" / "Dalia_ElevenLabs_Word_Timing.csv",
        root / "01_input" / "Dalia_ElevenLabs_Master_VO.mp3",
    ]:
        if not required.exists():
            print(f"ERROR: required input file missing: {required}")
            sys.exit(1)

    for script in SCRIPTS:
        path = script_dir / script
        print("\n" + "=" * 72)
        print(f"RUNNING {script}")
        print("=" * 72)
        start = time.time()
        result = subprocess.run([sys.executable, str(path)])
        elapsed = time.time() - start
        if result.returncode != 0:
            print(f"\n{script} failed (exit code {result.returncode}) after {elapsed:.1f}s. Stopping.")
            sys.exit(result.returncode)
        print(f"({script} finished in {elapsed:.1f}s)")

    print("\n" + "=" * 72)
    print("PIPELINE COMPLETE")
    print("=" * 72)
    print(f"Timeline clips : {root / '04_output' / '01_timeline_clips'}")
    print(f"Audio          : {root / '04_output' / '02_audio'}")
    print(f"Preview        : {root / '04_output' / '03_preview'}")
    print(f"Captions       : {root / '04_output' / '05_captions'}")
    print(f"Reports        : {root / '04_output' / '04_reports'}")
    print("\nRead 04_output/04_reports/capcut_import_steps.txt for what to do next.")


if __name__ == "__main__":
    main()
