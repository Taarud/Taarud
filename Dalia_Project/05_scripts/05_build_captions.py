#!/usr/bin/env python3
"""Build 04_output/05_captions/captions.srt from the ElevenLabs word-timing
CSV, grouped phrase-by-phrase (one cue per "Unit").

Cue times are converted from raw voiceover time into *project* time (the
same clock the numbered timeline clips and voiceover_for_timeline.wav use),
by locating each timestamp inside the OVERLAY clip whose VO range contains
it and re-basing on that clip's project_start. That way the captions line
up with the assembled timeline, not just the standalone narration file.

Run after 01_build_media_map.py.
"""
import bisect
import json
import sys
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def build_time_mapper(manifest):
    overlays = sorted(
        (c for c in manifest["clips"] if c["audio_use_category"] == "OVERLAY"),
        key=lambda c: c["vo_start"],
    )
    starts = [c["vo_start"] for c in overlays]

    def vo_to_project(t):
        if not overlays:
            return t
        i = bisect.bisect_right(starts, t) - 1
        i = max(0, min(i, len(overlays) - 1))
        seg = overlays[i]
        if t < seg["vo_start"] and i > 0:
            seg = overlays[i - 1]
        offset = t - seg["vo_start"]
        return seg["project_start"] + max(0.0, offset)

    return vo_to_project


def main():
    common.CAPTIONS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((common.WORKING_DIR / "manifest.json").read_text())
    vo_to_project = build_time_mapper(manifest)

    rows = common.read_word_timing_rows()
    units = OrderedDict()
    for row in rows:
        unit = row["Unit"]
        start = float(row["StartSec"])
        end = float(row["EndSec"])
        text = row["Utterance"]
        if unit not in units:
            units[unit] = {"start": start, "end": end, "text": text}
        else:
            units[unit]["start"] = min(units[unit]["start"], start)
            units[unit]["end"] = max(units[unit]["end"], end)

    srt_path = common.CAPTIONS_DIR / "captions.srt"
    skipped = 0
    with open(srt_path, "w", encoding="utf-8") as f:
        idx = 1
        for unit in units.values():
            p_start = vo_to_project(unit["start"])
            p_end = vo_to_project(unit["end"])
            if p_end <= p_start:
                skipped += 1
                continue
            f.write(f"{idx}\n")
            f.write(f"{common.fmt_srt_time(p_start)} --> {common.fmt_srt_time(p_end)}\n")
            f.write(f"{unit['text'].strip()}\n\n")
            idx += 1

    print(f"Wrote {srt_path} ({idx - 1} cues, timed to project/timeline seconds)")
    if skipped:
        print(f"  Skipped {skipped} unit(s) with non-positive duration after remapping.")


if __name__ == "__main__":
    main()
