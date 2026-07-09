
import json
import os
import re
import shutil
import logging
from datetime import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.text import get_valid_filename
from PIL import Image, UnidentifiedImageError

# ── Paths ──────────────────────────────────────────────────────────────────────
EVENTS_ROOT = os.path.join(settings.BASE_DIR, "static", "images", "events")
STATIC_URL_PREFIX = "/static/images/events"   # used to build URLs in templates
logger = logging.getLogger(__name__)


def _ensure_dirs():
    os.makedirs(EVENTS_ROOT, exist_ok=True)


def _meta_path(folder):
    return os.path.join(EVENTS_ROOT, folder, "meta.json")


def _read_meta(folder):
    path = _meta_path(folder)

    if not os.path.exists(path):
        return {}

    if not os.path.isfile(path):
        logger.warning("Event metadata path is not a regular file.")
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to read event metadata.")
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
        except Exception:
            logger.exception("Failed reading existing event metadata.")

    # Update titles
    if title_en:
        meta["title_en"] = title_en.strip()
    if title_hi:
        meta["title_hi"] = (title_hi or title_en).strip()

    # Thumbnail support
    if thumbnail:
        if thumbnail in os.listdir(folder_path):
            meta["thumbnail"] = thumbnail
        else:
            logger.warning("Requested event thumbnail was not found in the event folder.")

    # Save
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Failed writing event metadata.")
        raise Exception("Could not update event metadata.")
def _format_title(slug):
    return slug.replace("-", " ").title()


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
IMAGE_MIME_TYPES = {
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".webp": {"image/webp"},
}
PIL_FORMAT_BY_EXT = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}
MAX_IMAGE_SIZE = 5 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 25_000_000


def _safe_event_folder_path(folder):
    folder_path = os.path.abspath(os.path.join(EVENTS_ROOT, folder))
    events_root = os.path.abspath(EVENTS_ROOT)
    if os.path.commonpath([events_root, folder_path]) != events_root:
        raise ValidationError("Invalid event folder.")
    return folder_path


def validate_existing_event_folder(folder):
    folder = (folder or "").strip()
    if not folder or folder != os.path.basename(folder):
        raise ValidationError("Invalid event folder.")

    folder_path = _safe_event_folder_path(folder)
    if not os.path.isdir(folder_path):
        raise ValidationError("Event folder does not exist.")
    return folder


def _safe_event_folder_name(event_date, event_name):
    try:
        datetime.strptime(event_date or "", "%Y-%m-%d")
    except (TypeError, ValueError):
        raise ValidationError("Event date must be a valid YYYY-MM-DD date.")

    cleaned_name = re.sub(r"[^A-Za-z0-9_ -]", "", event_name or "").strip()
    if not cleaned_name:
        raise ValidationError("Event name is required.")

    slug = get_valid_filename(cleaned_name.replace(" ", "-"))
    folder_name = f"{event_date}_{slug}"
    _safe_event_folder_path(folder_name)
    return folder_name


def _validated_image_name(uploaded_file):
    original_name = get_valid_filename(os.path.basename(uploaded_file.name or ""))
    if not original_name:
        raise ValidationError("Uploaded file name is invalid.")

    stem, ext = os.path.splitext(original_name)
    ext = ext.lower()
    if ext not in IMAGE_EXTS:
        raise ValidationError(f"{original_name} has an unsupported file extension.")

    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    if content_type not in IMAGE_MIME_TYPES[ext]:
        raise ValidationError(f"{original_name} has an invalid MIME type.")

    if uploaded_file.size > MAX_IMAGE_SIZE:
        raise ValidationError(f"{original_name} exceeds 5MB limit.")

    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as image:
            image.verify()
            if image.format != PIL_FORMAT_BY_EXT[ext]:
                raise ValidationError(f"{original_name} content does not match its extension.")
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError):
        raise ValidationError(f"{original_name} is not a valid image file.")
    finally:
        uploaded_file.seek(0)

    return f"{stem}{ext}"


def _unique_destination(folder_path, filename):
    stem, ext = os.path.splitext(filename)
    candidate = filename
    counter = 1
    while os.path.exists(os.path.join(folder_path, candidate)):
        candidate = f"{stem}_{counter}{ext}"
        counter += 1
    return os.path.join(folder_path, candidate)


def _save_validated_image(folder_path, uploaded_file):
    filename = _validated_image_name(uploaded_file)
    dest = _unique_destination(folder_path, filename)
    with open(dest, "wb") as out:
        for chunk in uploaded_file.chunks():
            out.write(chunk)


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

        # Sort by creation time (upload order)
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
    if not files:
        raise ValidationError("At least one image is required.")

    for file in files:
        _validated_image_name(file)

    folder_name = _safe_event_folder_name(event_date, event_name)
    folder_path = _safe_event_folder_path(folder_name)
    os.makedirs(folder_path, exist_ok=True)

    # Write meta
    _write_meta(folder_name, {
        "title_en": event_name.strip(),
        "title_hi": (event_name_hi or event_name).strip(),
    })

    for file in files:
        _save_validated_image(folder_path, file)

    return folder_name


def upload_images_to_existing_event(folder, files):
    """
    Add more images to an existing event folder.
    """
    folder_path = _safe_event_folder_path(folder)
    if not os.path.exists(folder_path):
        raise Exception(f"Event folder '{folder}' does not exist.")
    if not files:
        raise ValidationError("At least one image is required.")

    for file in files:
        _validated_image_name(file)

    for file in files:
        _save_validated_image(folder_path, file)


def delete_event(folder):
    """
    Delete an entire event folder (images + meta.json).
    """
    folder_path = os.path.join(EVENTS_ROOT, folder)
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)
