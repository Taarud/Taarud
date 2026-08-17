#!/usr/bin/env python3
"""Scan 02_source_media/ and write an inventory to 03_working/media_inventory.json.

Run first. Safe to re-run any time new media is dropped into the source
media folders.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402


def main():
    common.WORKING_DIR.mkdir(parents=True, exist_ok=True)
    inventory = []

    for sub in ("images", "videos", "documents", "misc"):
        folder = common.SOURCE_MEDIA_DIR / sub
        folder.mkdir(parents=True, exist_ok=True)
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            category = common.classify_media_path(path)
            entry = {
                "path": str(path),
                "rel_path": str(path.relative_to(common.SOURCE_MEDIA_DIR)),
                "filename": path.name,
                "category": category,
                "declared_folder": sub,
                "size_bytes": path.stat().st_size,
            }
            if category == "video":
                entry["duration_sec"] = common.ffprobe_duration(path)
                w, h = common.ffprobe_dimensions(path)
                entry["width"], entry["height"] = w, h
            elif category == "image":
                w, h = common.ffprobe_dimensions(path)
                entry["width"], entry["height"] = w, h
            inventory.append(entry)

    out_path = common.WORKING_DIR / "media_inventory.json"
    out_path.write_text(json.dumps(inventory, indent=2))

    print(f"Scanned {common.SOURCE_MEDIA_DIR}")
    for sub in ("images", "videos", "documents", "misc"):
        n = sum(1 for e in inventory if e["declared_folder"] == sub)
        print(f"  {sub:10s}: {n} file(s)")
    print(f"Total: {len(inventory)} file(s). Inventory written to {out_path}")
    if not inventory:
        print(
            "\nNo local source media found. Every timeline row will be logged "
            "as missing and rendered as a labeled placeholder slate.\n"
            "Drop images/videos/documents into 02_source_media/ and re-run "
            "the pipeline to replace placeholders with real footage."
        )


if __name__ == "__main__":
    main()
