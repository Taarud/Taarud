#!/usr/bin/env python3
"""Write the final human-readable reports and run quality-control checks:

  04_output/04_reports/assembly_report.txt
  04_output/04_reports/missing_media_report.txt
  04_output/04_reports/capcut_import_steps.txt

(media_map_used.csv and timeline_manifest.csv are already written by
01_build_media_map.py.)

Run last, after every other script.
"""
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def load_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def qc_checks(manifest):
    lines = []
    ok = True

    clip_paths = sorted(common.CLIPS_DIR.glob("*.mp4"))
    expected_numbers = list(range(1, len(manifest["clips"]) + 1))
    actual_numbers = sorted(int(p.stem) for p in clip_paths if p.stem.isdigit())
    if actual_numbers == expected_numbers:
        lines.append(f"[PASS] Sequential numbering: {len(actual_numbers)} clips, 001-{len(actual_numbers):03d}, no gaps.")
    else:
        ok = False
        missing = sorted(set(expected_numbers) - set(actual_numbers))
        lines.append(f"[FAIL] Sequential numbering: expected {len(expected_numbers)} clips, found {len(actual_numbers)}. Missing: {missing}")

    bad_res = []
    for p in clip_paths:
        w, h = common.ffprobe_dimensions(p)
        if (w, h) != (common.WIDTH, common.HEIGHT):
            bad_res.append((p.name, w, h))
    if not bad_res:
        lines.append(f"[PASS] All {len(clip_paths)} clips are {common.WIDTH}x{common.HEIGHT}.")
    else:
        ok = False
        lines.append(f"[FAIL] {len(bad_res)} clip(s) are not {common.WIDTH}x{common.HEIGHT}: {bad_res[:5]}{'...' if len(bad_res) > 5 else ''}")

    expected_total = manifest["total_project_duration"]
    timeline_wav = common.AUDIO_DIR / "voiceover_for_timeline.wav"
    wav_dur = common.ffprobe_duration(timeline_wav) if timeline_wav.exists() else None
    if wav_dur is not None and abs(wav_dur - expected_total) <= 0.5:
        lines.append(f"[PASS] voiceover_for_timeline.wav duration ({wav_dur:.2f}s) matches project timeline ({expected_total:.2f}s).")
    else:
        ok = False
        lines.append(f"[FAIL] voiceover_for_timeline.wav duration ({wav_dur}) vs expected project timeline ({expected_total:.2f}s).")

    preview_path = common.PREVIEW_DIR / "roughcut_preview.mp4"
    preview_dur = common.ffprobe_duration(preview_path) if preview_path.exists() else None
    if preview_dur is not None and abs(preview_dur - expected_total) <= 1.0:
        lines.append(f"[PASS] roughcut_preview.mp4 rendered successfully ({preview_dur:.2f}s, matches project timeline).")
    elif preview_dur is not None:
        ok = False
        lines.append(f"[WARN] roughcut_preview.mp4 duration ({preview_dur:.2f}s) differs from expected ({expected_total:.2f}s) by more than 1s.")
    else:
        ok = False
        lines.append("[FAIL] roughcut_preview.mp4 was not found / did not render.")

    return ok, lines


def main():
    manifest = load_json(common.WORKING_DIR / "manifest.json", {"clips": [], "cold_open_total": 0, "total_project_duration": 0})
    assumptions = load_json(common.WORKING_DIR / "assumptions.json", [])
    clips = manifest["clips"]

    with open(common.REPORTS_DIR / "timeline_manifest.csv", newline="", encoding="utf-8") as f:
        manifest_rows = list(csv.DictReader(f))

    # --- QC ------------------------------------------------------------------
    qc_ok, qc_lines = qc_checks(manifest)

    # --- counts ----------------------------------------------------------------
    all_rows = common.read_timeline_rows()
    total_rows = len(all_rows)
    primary_count = len(clips)
    excluded_count = total_rows - primary_count
    by_category = {}
    for c in clips:
        by_category[c["audio_use_category"]] = by_category.get(c["audio_use_category"], 0) + 1

    matched = [c for c in clips if c["chosen_local_file"] and not c["is_graphic"]]
    graphics = [c for c in clips if c["is_graphic"]]
    missing = [c for c in clips if not c["chosen_local_file"] and not c["is_graphic"]]

    # --- assembly_report.txt ----------------------------------------------------
    lines = []
    lines.append("DALIA DIPPOLITO DOCUMENTARY — CAPCUT ASSEMBLY REPORT")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("=" * 72)
    lines.append("")
    lines.append("INPUTS")
    lines.append(f"  Timeline CSV : {common.TIMELINE_CSV.name}")
    lines.append(f"  Word timing  : {common.WORD_TIMING_CSV.name}")
    lines.append(f"  Master VO    : {common.MASTER_VO_MP3.name}")
    vo_dur = common.ffprobe_duration(common.MASTER_VO_MP3)
    if vo_dur:
        lines.append(f"  Master VO duration: {vo_dur:.2f}s")
    lines.append("")
    lines.append("TIMELINE ROWS")
    lines.append(f"  Total CSV rows            : {total_rows}")
    lines.append(f"  Primary rows kept         : {primary_count}")
    lines.append(f"  Backup/alternate excluded : {excluded_count}")
    for cat in ("PRE_VO", "OVERLAY", "INSERT"):
        lines.append(f"    {cat:8s}: {by_category.get(cat, 0)}")
    lines.append("")
    lines.append("PROJECT TIMELINE")
    lines.append(f"  Cold open total      : {manifest['cold_open_total']:.3f}s")
    lines.append(f"  Total project length : {manifest['total_project_duration']:.3f}s "
                 f"({manifest['total_project_duration']/60:.2f} min)")
    if vo_dur:
        lines.append(f"  Master VO length     : {vo_dur:.3f}s")
        lines.append(f"  Added by cold open + inserts: {manifest['total_project_duration'] - vo_dur:.3f}s")
    lines.append("")
    lines.append("MEDIA MATCHING")
    lines.append(f"  Matched to local source media : {len(matched)}")
    lines.append(f"  Auto-generated original graphics: {len(graphics)}")
    lines.append(f"  Missing (placeholder slate)   : {len(missing)}")
    lines.append("")
    lines.append("QUALITY CONTROL")
    for line in qc_lines:
        lines.append(f"  {line}")
    lines.append("")
    lines.append("ASSUMPTIONS / JUDGMENT CALLS")
    lines.append("  - 'OVERLAY / OPTIONAL PAUSE FOR SOURCE AUDIO' rows were classified as a real")
    lines.append("    INSERT (source audio preserved, VO paused) when their Beat Type/Visual Type")
    lines.append("    said 'real audio/footage'; otherwise treated as a plain overlay. Verify in")
    lines.append("    media_map_used.csv (audio_use_category column) before final export.")
    lines.append("  - A row was treated as backup/non-primary (excluded) whenever its Visual Type")
    lines.append("    was 'Alternate' or its Place-Against-Script field mentioned")
    lines.append("    backup/alternate/optional, per the CSV's own labeling.")
    lines.append("  - Rows whose Source Name/Source Class marked them as an original/editor-created")
    lines.append("    asset (title cards, timelines, lower-thirds) were rendered directly as text")
    lines.append("    cards rather than flagged as missing media.")
    lines.append("  - INSERT / cold-open clip durations came from numeric ranges found in the")
    lines.append("    'Exact Source Cue / What to Pull' text (range midpoint used) where present;")
    lines.append("    rows with no numeric cue got a logged default (see below).")
    lines.append("  - Matched real video clips are trimmed from the start of the matched file")
    lines.append("    (the CSV gives descriptive in/out cues, not exact source timecodes) —")
    lines.append("    re-park the in/out points by hand once real footage is dropped in.")
    if assumptions:
        lines.append("")
        lines.append(f"  Per-row logged assumptions ({len(assumptions)}):")
        for a in assumptions:
            lines.append(f"    [{a['scope']}] {a['message']}")
    lines.append("")
    lines.append(f"See media_map_used.csv and timeline_manifest.csv in this folder for full detail.")

    (common.REPORTS_DIR / "assembly_report.txt").write_text("\n".join(lines) + "\n")

    # --- missing_media_report.txt ------------------------------------------------
    ml = []
    ml.append("MISSING MEDIA REPORT")
    ml.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    ml.append("=" * 72)
    ml.append("")
    if not missing:
        ml.append("Nothing missing — every primary row matched local source media or was an")
        ml.append("auto-generated graphic.")
    else:
        ml.append(f"{len(missing)} row(s) had no local file in 02_source_media/ and were rendered")
        ml.append("as an obvious 'MISSING MEDIA' placeholder slate at the correct duration so the")
        ml.append("timeline stays intact. Drop the real footage/image into 02_source_media/ and")
        ml.append("re-run the pipeline to replace them.")
        ml.append("")
        for c in missing:
            ml.append(f"Clip {c['clip_filename']} — Beat {c['beat_order']}.{c['visual_number']} ({c['section']})")
            ml.append(f"  Needed   : {c['source_name']}")
            ml.append(f"  On screen: {c['what_goes_on_screen']}")
            ml.append(f"  Duration : {c['duration']:.2f}s ({c['duration_basis']})")
            ml.append(f"  Match note: {c['match_reason']}")
            ml.append("")
    (common.REPORTS_DIR / "missing_media_report.txt").write_text("\n".join(ml) + "\n")

    # --- capcut_import_steps.txt --------------------------------------------------
    steps = f"""HOW TO IMPORT THIS INTO CAPCUT
Generated: {datetime.now().isoformat(timespec='seconds')}
{'=' * 72}

1. Open CapCut and start a new project (1920x1080, 30fps).
2. Import every file from 04_output/01_timeline_clips/ (001.mp4 ... {len(clips):03d}.mp4).
3. Select all imported clips in the media bin, sorted by name, and drag them
   onto the video track in order (001 first). They already run the correct
   length, so they'll snap end-to-end with no trimming needed.
4. Import 04_output/02_audio/voiceover_for_timeline.wav and drag it onto an
   audio track starting at 00:00 of the timeline. It already has silence
   inserted everywhere a real-audio insert clip plays, so it lines up under
   the video without further adjustment.
5. (Optional) Import 04_output/05_captions/captions.srt for burn-in or
   soft captions — cue times are already in project-timeline seconds, not
   raw voiceover seconds.
6. (Optional) Import 04_output/02_audio/voiceover_clean.mp3 if you ever need
   the plain, unmodified narration by itself.
7. Check 04_output/04_reports/missing_media_report.txt — swap out any clip
   still showing a red "MISSING MEDIA" placeholder for the real footage/
   image, matching the beat/visual number in the filename, then re-render
   just that clip (or drop the file into 02_source_media/ and re-run
   05_scripts/run_all.py to regenerate everything automatically).
8. From there: add music, transitions, and polish to taste. The heavy
   lifting (timing, ordering, muting/audio decisions) is already done.

Reference: 04_output/03_preview/roughcut_preview.mp4 is a same-length QC
render of steps 2-4 combined — use it to sanity-check pacing before you
start manual polish in CapCut.
"""
    (common.REPORTS_DIR / "capcut_import_steps.txt").write_text(steps)

    print(f"Wrote {common.REPORTS_DIR / 'assembly_report.txt'}")
    print(f"Wrote {common.REPORTS_DIR / 'missing_media_report.txt'}")
    print(f"Wrote {common.REPORTS_DIR / 'capcut_import_steps.txt'}")
    print()
    print("QC summary:")
    for line in qc_lines:
        print(f"  {line}")
    print()
    print("QC " + ("PASSED" if qc_ok else "FOUND ISSUES — see assembly_report.txt"))


if __name__ == "__main__":
    main()
