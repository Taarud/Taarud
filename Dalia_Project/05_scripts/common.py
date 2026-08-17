"""Shared helpers for the Dalia CapCut assembly kit scripts.

All paths are resolved relative to the project root (the parent of this
05_scripts/ folder), so the scripts can be run from any working directory.
"""
import csv
import difflib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT / "01_input"
SOURCE_MEDIA_DIR = ROOT / "02_source_media"
WORKING_DIR = ROOT / "03_working"
OUTPUT_DIR = ROOT / "04_output"
CLIPS_DIR = OUTPUT_DIR / "01_timeline_clips"
AUDIO_DIR = OUTPUT_DIR / "02_audio"
PREVIEW_DIR = OUTPUT_DIR / "03_preview"
REPORTS_DIR = OUTPUT_DIR / "04_reports"
CAPTIONS_DIR = OUTPUT_DIR / "05_captions"

TIMELINE_CSV = INPUT_DIR / "CodeCopper_Dalia_CLAUDE_MEDIA_READY.csv"
TIMELINE_CSV_FALLBACK = INPUT_DIR / "CodeCopper_Dalia_Visual_Coverage_AUDIO_ALIGNED.csv"
if not TIMELINE_CSV.exists() and TIMELINE_CSV_FALLBACK.exists():
    TIMELINE_CSV = TIMELINE_CSV_FALLBACK
WORD_TIMING_CSV = INPUT_DIR / "Dalia_ElevenLabs_Word_Timing.csv"
MASTER_VO_MP3 = INPUT_DIR / "Dalia_ElevenLabs_Master_VO.mp3"
PACK_MEDIA_DIR = SOURCE_MEDIA_DIR / "pack_media"

FPS = 30
WIDTH, HEIGHT = 1920, 1080

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif"}
DOCUMENT_EXTS = {".pdf"}

# --- Assumption / judgment-call log, shared across a single run -----------
ASSUMPTIONS = []


def log_assumption(scope, message):
    ASSUMPTIONS.append({"scope": scope, "message": message})


def save_assumptions():
    """Overwrites 03_working/assumptions.json with this run's ASSUMPTIONS.
    Call once, at the end of the single script that logs them
    (01_build_media_map.py) — not additive across runs/scripts."""
    path = WORKING_DIR / "assumptions.json"
    path.write_text(json.dumps(ASSUMPTIONS, indent=2))


# --- Time parsing -----------------------------------------------------------

def parse_vo_time(raw):
    """'02:31.400' -> 151.4 seconds. 'BEFORE VO' / '' -> None."""
    if raw is None:
        return None
    raw = raw.strip()
    if not raw or raw.upper() == "BEFORE VO":
        return None
    parts = raw.split(":")
    try:
        if len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + float(seconds)
        return float(raw)
    except ValueError:
        return None


def fmt_srt_time(seconds):
    seconds = max(0.0, seconds)
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# --- Duration parsing from free-text cue notes ------------------------------

_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[-–—]\s*(\d+(?:\.\d+)?)\s*sec")
_SINGLE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*sec")


def parse_duration_hint(*texts):
    """Look for '20-25 sec' or '12 sec' style hints in free text. Returns
    (seconds, basis_description) or (None, None) if nothing found."""
    for text in texts:
        if not text:
            continue
        m = _RANGE_RE.search(text)
        if m:
            lo, hi = float(m.group(1)), float(m.group(2))
            mid = round((lo + hi) / 2, 3)
            return mid, f"midpoint of stated range '{m.group(0)}'"
        m = _SINGLE_RE.search(text)
        if m:
            val = float(m.group(1))
            return val, f"explicit single value '{m.group(0)}'"
    return None, None


# --- CSV row classification --------------------------------------------------

NON_PRIMARY_KEYWORDS = ("backup", "alternate", "optional")


def is_primary_row(row):
    visual_type = (row.get("Visual Type") or "").strip().lower()
    place = (row.get("Place Against Script") or "").strip().lower()
    if visual_type == "alternate":
        return False
    if any(kw in place for kw in NON_PRIMARY_KEYWORDS):
        return False
    if any(kw in visual_type for kw in NON_PRIMARY_KEYWORDS):
        return False
    return True


def audio_use_category(row):
    """Return one of PRE_VO, OVERLAY, INSERT based on the Audio Use column
    (plus a judgment call for the ambiguous 'OVERLAY / OPTIONAL PAUSE FOR
    SOURCE AUDIO' rows)."""
    au = (row.get("Audio Use") or "").strip().upper()
    if au == "PRE-VO COLD OPEN":
        return "PRE_VO"
    if au == "PAUSE VO / INSERT REAL CLIP":
        return "INSERT"
    if au == "OVERLAY UNDER VO":
        return "OVERLAY"
    if au == "OVERLAY / OPTIONAL PAUSE FOR SOURCE AUDIO":
        # Per the master prompt: default to OVERLAY unless context clearly
        # indicates a real insert. These rows carry real scripted narration
        # across their VO Start/End span (unlike true INSERT rows, whose VO
        # Start == VO End, a zero-width pause anchor) — silencing that span
        # to play optional source audio would drop actual narration content,
        # so we keep it as an overlay and just log the option was available.
        log_assumption(
            f"Beat {row.get('Beat Order')}.{row.get('Visual #')}",
            "Audio Use = 'OVERLAY / OPTIONAL PAUSE FOR SOURCE AUDIO' — kept as an "
            "overlay (narration plays, VO span used as duration) per the default "
            "rule, since this row has real scripted narration across VO Start/End. "
            "Source audio could optionally replace it — swap manually in CapCut if desired.",
        )
        return "OVERLAY"
    # Unknown Audio Use value: treat conservatively as overlay and log it.
    log_assumption(
        f"Beat {row.get('Beat Order')}.{row.get('Visual #')}",
        f"Unrecognized Audio Use value '{row.get('Audio Use')}' — treated as OVERLAY.",
    )
    return "OVERLAY"


def read_timeline_rows():
    with open(TIMELINE_CSV, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    # Drop fully blank trailing rows.
    return [r for r in rows if any((v or "").strip() for v in r.values())]


def read_word_timing_rows():
    with open(WORD_TIMING_CSV, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# --- ffprobe / ffmpeg helpers ------------------------------------------------

def ffprobe_duration(path):
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())
    except Exception:
        return None


def ffprobe_dimensions(path):
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate",
                "-of", "csv=s=x:p=0", str(path),
            ],
            capture_output=True, text=True, check=True,
        )
        parts = out.stdout.strip().split("x")
        if len(parts) >= 2:
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return None, None


def run(cmd, **kwargs):
    kwargs.setdefault("check", True)
    return subprocess.run(cmd, **kwargs)


def resolve_pack_media_path(local_media_file):
    """The media pack's 'LOCAL MEDIA FILE' column gives paths relative to the
    pack root, e.g. '03_ACTUAL_MEDIA/04_location_assets/Boynton_Beach_map.webp'.
    We copied that pack's 03_ACTUAL_MEDIA/ contents into
    02_source_media/pack_media/, so strip the '03_ACTUAL_MEDIA/' (or
    '04_DOWNLOADED_PUBLIC_RECORD_VIDEO/') prefix and resolve under there."""
    if not local_media_file:
        return None
    rel = local_media_file.strip().replace("\\", "/")
    for prefix in ("03_ACTUAL_MEDIA/", "04_DOWNLOADED_PUBLIC_RECORD_VIDEO/"):
        if rel.startswith(prefix):
            rel = rel[len(prefix):]
            break
    candidate = PACK_MEDIA_DIR / rel
    return candidate if candidate.exists() else None


def classify_media_path(path: Path):
    ext = path.suffix.lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in IMAGE_EXTS:
        return "image"
    if ext in DOCUMENT_EXTS:
        return "document"
    return "misc"


def fuzzy_score(a, b):
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def drawtext_escape(text):
    """Escape text for use inside an ffmpeg drawtext filter argument."""
    return (
        text.replace("\\", "\\\\\\\\")
        .replace(":", "\\:")
        .replace("'", "’")
        .replace("%", "\\%")
    )
