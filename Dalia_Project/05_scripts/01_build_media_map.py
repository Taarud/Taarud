#!/usr/bin/env python3
"""Parse the audio-aligned timeline CSV, classify every row, match it against
local source media, compute the two-clock project timeline, and write:

  04_output/04_reports/media_map_used.csv   (every CSV row + match decision)
  04_output/04_reports/timeline_manifest.csv (only the rows that make the cut)
  03_working/manifest.json                   (rich data for later scripts)

Run after 00_scan_media.py.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

MATCH_THRESHOLD = 0.55
GRAPHIC_VISUAL_TYPES = {"original graphic", "title card"}


def load_inventory():
    path = common.WORKING_DIR / "media_inventory.json"
    if path.exists():
        return json.loads(path.read_text())
    return []


def expected_category(visual_type):
    vt = (visual_type or "").lower()
    if "video" in vt or "audio/video" in vt:
        return "video"
    if "image" in vt or "photo" in vt:
        return "image"
    if "document" in vt:
        return "document"
    return None  # web/reference/graphic rows have no fixed category


def is_graphic_row(row):
    source_name = (row.get("Source Name") or "").strip().lower()
    source_class = (row.get("Source Class") or "").strip().lower()
    visual_type = (row.get("Visual Type") or "").strip().lower()
    return (
        source_name.startswith("original")
        or source_class == "original asset"
        or visual_type in GRAPHIC_VISUAL_TYPES
    )


def find_match(row, inventory):
    if not inventory:
        return None, 0.0, "no local media files found in 02_source_media"

    cat = expected_category(row.get("Visual Type"))
    candidates = [e for e in inventory if cat is None or e["category"] == cat] or inventory

    source_name = row.get("Source Name") or ""
    on_screen = row.get("What Goes On Screen") or ""
    best, best_score = None, 0.0
    for entry in candidates:
        stem = Path(entry["filename"]).stem.replace("_", " ").replace("-", " ")
        score = max(
            common.fuzzy_score(source_name, stem),
            common.fuzzy_score(on_screen, stem),
            common.fuzzy_score(source_name + " " + on_screen, stem),
        )
        if score > best_score:
            best, best_score = entry, score

    if best and best_score >= MATCH_THRESHOLD:
        return best, best_score, f"fuzzy filename match on source/description (score {best_score:.2f})"
    if best:
        return None, best_score, (
            f"best candidate '{best['filename']}' scored only {best_score:.2f} "
            f"(below {MATCH_THRESHOLD} threshold) — not used"
        )
    return None, 0.0, "no plausible candidate in inventory"


# Media-pack MEDIA STATUS handling. When the CSV was produced by the
# Claude media pack (has a MEDIA STATUS / LOCAL MEDIA FILE column), those
# columns are authoritative and we skip fuzzy matching entirely — the pack
# already did the rights-aware triage.
MISSING_STATUS_REASONS = {
    "DOWNLOAD_ON_USER_MACHINE_OFFICIAL": (
        "Official public-record video not yet downloaded — this sandboxed session "
        "couldn't reach YouTube (network policy blocks it: yt-dlp got a 403 on the "
        "proxy tunnel). Run 07_CLAUDE_TOOLS/DOWNLOAD_OFFICIAL_MEDIA.bat (or "
        "`python3 download_public_record_media.py`) on a machine with internet "
        "access, then drop the result into 02_source_media/pack_media/"
        "04_DOWNLOADED_PUBLIC_RECORD_VIDEO/ and re-run the pipeline."
    ),
    "REVIEW_PUBLIC_RECORD_COPY": (
        "Requires manual rights/provenance review before use (see "
        "01_input/download_list.csv notes) — not auto-downloaded."
    ),
    "COPYRIGHTED_REFERENCE_ONLY": (
        "Copyrighted broadcaster material (Court TV/ABC/Law&Crime/etc.) — reference "
        "only. Replace with your own licensed/fair-use clip or a public-record "
        "equivalent, then drop it into 02_source_media/ and re-run the pipeline."
    ),
    "THIRD_PARTY_VIDEO_REVIEW": "Third-party video — needs manual review before use.",
}


def resolve_media(row, inventory):
    """Returns (is_graphic, chosen_rel_path_or_None, confidence, why)."""
    status = (row.get("MEDIA STATUS") or "").strip()
    if status:  # media-pack CSV — MEDIA STATUS/LOCAL MEDIA FILE are authoritative
        if status == "CREATE_ORIGINAL":
            return True, None, 1.0, "Original/editor-created graphic (CREATE_ORIGINAL)."

        local_file = row.get("LOCAL MEDIA FILE") or ""
        resolved = common.resolve_pack_media_path(local_file)
        if resolved:
            rel = str(resolved.relative_to(common.SOURCE_MEDIA_DIR))
            tag = "INCLUDED_ACTUAL" if status == "INCLUDED_ACTUAL" else status
            return False, rel, 1.0, f"Included in the media pack ({tag})."

        reason = MISSING_STATUS_REASONS.get(
            status, f"MEDIA STATUS = '{status}' with no resolvable local file."
        )
        return False, None, 0.0, reason

    # No MEDIA STATUS column (plain/original CSV) — fall back to fuzzy matching.
    if is_graphic_row(row):
        return True, None, 1.0, "Original/editor-created graphic — generated directly, no source media needed."
    match, confidence, why = find_match(row, inventory)
    return False, (match["rel_path"] if match else None), confidence, why


def compute_duration(row, category, vo_start, vo_end):
    cue = row.get("Exact Source Cue / What to Pull") or ""
    on_screen = row.get("What Goes On Screen") or ""
    note = row.get("Editor Note") or ""
    beat_id = f"Beat {row.get('Beat Order')}.{row.get('Visual #')}"

    if category == "PRE_VO":
        hint, basis = common.parse_duration_hint(cue, on_screen, note)
        if hint:
            return hint, basis
        visual_type = (row.get("Visual Type") or "").lower()
        beat_type = (row.get("Beat Type") or "").lower()
        if "title card" in visual_type or "title card" in beat_type:
            common.log_assumption(beat_id, "No duration cue for title card — defaulted to 2.5s.")
            return 2.5, "default title-card duration (no cue found)"
        common.log_assumption(beat_id, "No duration cue for cold-open shot — defaulted to 4.0s.")
        return 4.0, "default cold-open shot duration (no cue found)"

    if category == "OVERLAY":
        # vo_start/vo_end are already snapped to word boundaries by the caller.
        if vo_start is not None and vo_end is not None and (vo_end - vo_start) > 0.05:
            return round(vo_end - vo_start, 3), "VO End - VO Start"
        hint, basis = common.parse_duration_hint(cue, on_screen)
        if hint:
            common.log_assumption(beat_id, "OVERLAY row had a zero/near-zero VO span — used cue text duration instead.")
            return hint, basis
        common.log_assumption(beat_id, "OVERLAY row had a zero/near-zero VO span and no cue duration — defaulted to 2.0s.")
        return 2.0, "default fallback (VO span was zero/negative and no cue found)"

    # INSERT
    hint, basis = common.parse_duration_hint(cue, on_screen, note)
    if hint:
        return hint, basis
    common.log_assumption(beat_id, "INSERT row had no explicit duration cue — defaulted to 10.0s. Adjust in CapCut once real footage is placed.")
    return 10.0, "default insert duration (no cue found)"


def main():
    common.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    common.WORKING_DIR.mkdir(parents=True, exist_ok=True)

    rows = common.read_timeline_rows()
    inventory = load_inventory()

    media_map_rows = []
    processed = []

    for row in rows:
        beat_order = row.get("Beat Order")
        visual_number = row.get("Visual #")
        category = common.audio_use_category(row)
        primary = is_primary_row = common.is_primary_row(row)
        graphic, chosen_file, confidence, why = resolve_media(row, inventory)

        media_map_rows.append({
            "beat_order": beat_order,
            "visual_number": visual_number,
            "is_primary": primary,
            "audio_use_category": category,
            "is_graphic": graphic,
            "source_name": row.get("Source Name"),
            "chosen_local_file": chosen_file or "",
            "confidence": round(confidence, 2),
            "why_this_file_was_chosen": why,
        })

        if not primary:
            continue

        # Snap VO timestamps to actual word edges before computing duration —
        # the coverage CSV's own alignment pass isn't always word-exact, and
        # hard-cutting audio at an imprecise boundary chops off the tail of
        # a word. See common.snap_to_word_boundary for details.
        raw_vo_start = common.parse_vo_time(row.get("VO Start"))
        raw_vo_end = common.parse_vo_time(row.get("VO End"))
        vo_start = common.snap_to_word_boundary(raw_vo_start)
        vo_end = common.snap_to_word_boundary(raw_vo_end)
        if vo_start != raw_vo_start or vo_end != raw_vo_end:
            common.log_assumption(
                f"Beat {beat_order}.{visual_number}",
                f"Snapped VO boundary to the nearest word edge (VO Start "
                f"{raw_vo_start}->{vo_start}, VO End {raw_vo_end}->{vo_end}) so "
                f"narration audio doesn't get cut off mid-word.",
            )
        vo_anchor_raw = (row.get("VO Anchor Sec") or "").strip()
        vo_anchor = common.snap_to_word_boundary(float(vo_anchor_raw)) if vo_anchor_raw else None

        duration, duration_basis = compute_duration(row, category, vo_start, vo_end)

        uses_source_audio = category == "INSERT"

        processed.append({
            "beat_order": beat_order,
            "visual_number": visual_number,
            "section": row.get("Section"),
            "audio_use_raw": row.get("Audio Use"),
            "audio_use_category": category,
            "visual_type": row.get("Visual Type"),
            "is_graphic": graphic,
            "what_goes_on_screen": row.get("What Goes On Screen"),
            "source_name": row.get("Source Name"),
            "chosen_local_file": chosen_file,
            "match_confidence": round(confidence, 2),
            "match_reason": why,
            "vo_start": vo_start,
            "vo_end": vo_end,
            "vo_anchor": vo_anchor,
            "duration": duration,
            "duration_basis": duration_basis,
            "uses_source_audio": uses_source_audio,
            "editor_note": row.get("Editor Note"),
        })

    # --- project-time math -------------------------------------------------
    # The master spec's formula (project_start = cold_open_total + vo_start +
    # insert_offset) assumes the CSV's VO Start/End values are perfectly
    # monotonic and non-overlapping across beats. In this real CSV a handful
    # of beat boundaries overlap slightly (the source audio-alignment pass
    # that produced VO Start/End wasn't perfectly clean), which would leave
    # the absolute formula with gaps or even overlaps between clips —
    # desyncing the rendered clips from voiceover_for_timeline.wav. Instead
    # we lay every primary row out *sequentially*, in CSV row order, each
    # one starting exactly where the previous ends. Every row's duration is
    # still computed the documented way (VO End-VO Start for overlays, a
    # parsed/default target length for inserts and cold opens) — only the
    # *positioning* is sequential rather than VO-anchored, which guarantees
    # the numbered clips, the timeline-adjusted voiceover, and the roughcut
    # preview always add up to the exact same total, by construction.
    common.log_assumption(
        "project timeline",
        "Positioned every primary row sequentially (each starts where the previous "
        "ends) rather than at its absolute VO-anchored position, because a few beat "
        "boundaries in the source CSV have overlapping VO Start/End values. Each "
        "row's own duration is unchanged (VO End-VO Start for overlays, parsed/"
        "default target length for inserts and cold opens) — this only affects where "
        "the clip is placed on the project timeline. See vo_start/vo_end/vo_anchor "
        "columns in timeline_manifest.csv for the original VO-time reference.",
    )

    pre_vo = [r for r in processed if r["audio_use_category"] == "PRE_VO"]
    rest = [r for r in processed if r["audio_use_category"] != "PRE_VO"]
    final_sequence = pre_vo + rest

    t = 0.0
    for r in final_sequence:
        r["project_start"] = round(t, 3)
        r["project_end"] = round(t + r["duration"], 3)
        t += r["duration"]

    cold_open_total = round(sum(r["duration"] for r in pre_vo), 3)

    for i, r in enumerate(final_sequence, start=1):
        r["clip_number"] = i
        r["clip_filename"] = f"{i:03d}.mp4"

    total_project_duration = final_sequence[-1]["project_end"] if final_sequence else 0.0

    # --- write media_map_used.csv ------------------------------------------
    with open(common.REPORTS_DIR / "media_map_used.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(media_map_rows[0].keys()))
        w.writeheader()
        w.writerows(media_map_rows)

    # --- write timeline_manifest.csv ----------------------------------------
    manifest_fields = [
        "clip_number", "clip_filename", "beat_order", "visual_number", "section",
        "audio_use_category", "is_graphic", "visual_type", "what_goes_on_screen",
        "source_name", "chosen_local_file", "match_confidence",
        "project_start", "project_end", "duration", "duration_basis",
        "vo_start", "vo_end", "uses_source_audio",
    ]
    with open(common.REPORTS_DIR / "timeline_manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=manifest_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(final_sequence)

    # --- write manifest.json for downstream scripts -------------------------
    manifest = {
        "cold_open_total": cold_open_total,
        "total_project_duration": round(total_project_duration, 3),
        "clip_count": len(final_sequence),
        "clips": final_sequence,
    }
    (common.WORKING_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))

    common.save_assumptions()

    print(f"Parsed {len(rows)} CSV rows.")
    print(f"  Primary rows kept for the timeline: {len(final_sequence)}")
    print(f"  Backup/alternate rows excluded: {len(rows) - len(final_sequence)}")
    print(f"  Cold open total: {cold_open_total:.3f}s")
    print(f"  Total project duration: {total_project_duration:.3f}s")
    matched = sum(1 for r in final_sequence if r["chosen_local_file"])
    graphics = sum(1 for r in final_sequence if r["is_graphic"])
    missing = len(final_sequence) - matched - graphics
    print(f"  Matched to local media: {matched}")
    print(f"  Auto-generated graphics: {graphics}")
    print(f"  Missing (will render as placeholder slates): {missing}")
    print(f"Wrote {common.REPORTS_DIR / 'media_map_used.csv'}")
    print(f"Wrote {common.REPORTS_DIR / 'timeline_manifest.csv'}")


if __name__ == "__main__":
    main()
