"""
static_event_service.py
Replaces minio_service.py — events are stored as static files + a JSON config.

Folder structure:
    static/
        images/
            events/
                2025-09-14_Hindi-Diwas/
                    img1.jpg
                    img2.jpg
                meta.json   ← auto-created, holds title_en + title_hi

events.json path: static/data/events.json  (auto-synced from folder scan)
"""

import json
import os
import shutil
from datetime import datetime

from django.conf import settings

# ── Paths ──────────────────────────────────────────────────────────────────────
EVENTS_ROOT = os.path.join(settings.BASE_DIR, "static", "images", "events")
STATIC_URL_PREFIX = "/static/images/events"   # used to build URLs in templates


def _ensure_dirs():
    os.makedirs(EVENTS_ROOT, exist_ok=True)


def _meta_path(folder):
    return os.path.join(EVENTS_ROOT, folder, "meta.json")


def _read_meta(folder):
    path = _meta_path(folder)

    # ✅ If path doesn't exist → return empty
    if not os.path.exists(path):
        return {}

    # 🔥 CRITICAL FIX: ensure it's a FILE, not a folder
    if not os.path.isfile(path):
        print(f"[ERROR] meta.json is not a file: {path}")
        return {}

    # ✅ Safe read with error handling
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to read meta.json in {folder}: {e}")
        return {}


def _write_meta(folder, meta: dict):
    path = _meta_path(folder)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

def update_event_meta(folder, title_en, title_hi, thumbnail=None):
    """
    Update titles + optional thumbnail safely
    """

    folder_path = os.path.join(EVENTS_ROOT, folder)

    if not os.path.exists(folder_path):
        raise Exception(f"Event folder '{folder}' does not exist.")

    meta_path = _meta_path(folder)

    meta = {}

    # Read existing meta safely
    if os.path.exists(meta_path) and os.path.isfile(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed reading meta: {e}")

    # Update titles
    if title_en:
        meta["title_en"] = title_en.strip()
    if title_hi:
        meta["title_hi"] = (title_hi or title_en).strip()

    # 🔥 Thumbnail support
    if thumbnail:
        if thumbnail in os.listdir(folder_path):
            meta["thumbnail"] = thumbnail
        else:
            print(f"[WARNING] Thumbnail file not found: {thumbnail}")

    # Save
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ERROR] Failed writing meta.json: {e}")
        raise Exception("Could not update event metadata.")
def _format_title(slug):
    return slug.replace("-", " ").title()


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def get_all_events():
    """
    Scan EVENTS_ROOT, read each folder's meta.json, return sorted event list.
    """
    _ensure_dirs()
    events = []

    for folder_name in os.listdir(EVENTS_ROOT):
        folder_path = os.path.join(EVENTS_ROOT, folder_name)

        if not os.path.isdir(folder_path):
            continue

        # Collect image files
        image_files = [
            fname for fname in os.listdir(folder_path)
            if os.path.splitext(fname)[1].lower() in IMAGE_EXTS
        ]

        # ✅ Sort by creation time (upload order)
        image_files.sort(
            key=lambda x: os.path.getctime(os.path.join(folder_path, x))
        )

        images = [
            f"{STATIC_URL_PREFIX}/{folder_name}/{fname}"
            for fname in image_files
        ]

        if not images:
            continue   # skip empty folders

        # Parse date + slug from folder name
        try:
            if "_" in folder_name and folder_name[:4].isdigit():
                date_str, slug = folder_name.split("_", 1)
                event_date = datetime.strptime(date_str, "%Y-%m-%d")
                display_date = event_date.strftime("%d %B %Y")
                sort_date = event_date
            else:
                slug = folder_name
                display_date = "Unknown Date"
                sort_date = datetime(1900, 1, 1)
        except Exception:
            slug = folder_name
            display_date = "Unknown Date"
            sort_date = datetime(1900, 1, 1)

        meta = _read_meta(folder_name)
        title_en = meta.get("title_en") or _format_title(slug)
        title_hi = meta.get("title_hi") or title_en
        thumbnail_file = meta.get("thumbnail")

        if thumbnail_file and thumbnail_file in image_files:
            thumbnail = f"{STATIC_URL_PREFIX}/{folder_name}/{thumbnail_file}"
        else:
            thumbnail = images[0] if images else None

        events.append({
            "folder":    folder_name,
            "title":     title_en,
            "title_hi":  title_hi,
            "date":      display_date,
            "thumbnail": thumbnail,
            "images":    images,
            "sort_date": sort_date,
        })

    events.sort(key=lambda x: x["sort_date"], reverse=True)
    return events


def upload_event(event_date, event_name, event_name_hi, files):
    """
    Create a new event folder under static/images/events/, save images + meta.json.
    Returns the folder name.
    """
    _ensure_dirs()

    slug = event_name.strip().replace(" ", "-")
    folder_name = f"{event_date}_{slug}"
    folder_path = os.path.join(EVENTS_ROOT, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    # Write meta
    _write_meta(folder_name, {
        "title_en": event_name.strip(),
        "title_hi": (event_name_hi or event_name).strip(),
    })

    # Save uploaded images
    for file in files:
        if file.size > 5 * 1024 * 1024:
            raise Exception(f"{file.name} exceeds 5MB limit.")
        dest = os.path.join(folder_path, file.name)
        with open(dest, "wb") as out:
            for chunk in file.chunks():
                out.write(chunk)

    return folder_name


def upload_images_to_existing_event(folder, files):
    """
    Add more images to an existing event folder.
    """
    folder_path = os.path.join(EVENTS_ROOT, folder)
    if not os.path.exists(folder_path):
        raise Exception(f"Event folder '{folder}' does not exist.")

    for file in files:
        if file.size > 5 * 1024 * 1024:
            raise Exception(f"{file.name} exceeds 5MB limit.")
        dest = os.path.join(folder_path, file.name)
        with open(dest, "wb") as out:
            for chunk in file.chunks():
                out.write(chunk)


def delete_event(folder):
    """
    Delete an entire event folder (images + meta.json).
    """
    folder_path = os.path.join(EVENTS_ROOT, folder)
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)


# def update_event_meta(folder, title_en, title_hi):
#     """
#     Update just the titles of an existing event (used by edit view).
#     """
#     meta = _read_meta(folder)
#     meta["title_en"] = title_en.strip()
#     meta["title_hi"] = (title_hi or title_en).strip()
#     _write_meta(folder, meta)