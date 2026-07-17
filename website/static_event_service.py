
import io
import json
import re
import shutil
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from django.conf import settings
from PIL import Image, UnidentifiedImageError

# ── Paths ──────────────────────────────────────────────────────────────────────
EVENTS_ROOT = Path(settings.BASE_DIR) / "static" / "images" / "events"
STATIC_URL_PREFIX = "/static/images/events"   # used to build URLs in templates
logger = logging.getLogger(__name__)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
IMAGE_MIME_WHITELIST = {
    ".jpg": {"image/jpeg", "image/pjpeg"},
    ".jpeg": {"image/jpeg", "image/pjpeg"},
    ".png": {"image/png"},
    ".webp": {"image/webp"},
}
PIL_FORMAT_TO_EXTS = {
    "JPEG": {".jpg", ".jpeg"},
    "PNG": {".png"},
    "WEBP": {".webp"},
}
FILENAME_SANITIZE_RE = re.compile(r"[^A-Za-z0-9 _\-.]")
FOLDER_SLUG_SANITIZE_RE = re.compile(r"[^A-Za-z0-9 _\-]")


def _ensure_inside_root(path: Path) -> Path:
    path = path.resolve()
    root = EVENTS_ROOT.resolve()
    if path == root or root in path.parents:
        return path
    raise ValueError("Invalid upload destination path.")


def _sanitize_upload_filename(filename: str) -> str:
    if not filename:
        raise ValueError("Upload filename required.")

    filename = unquote(filename)
    filename = filename.replace("\\", "/")
    filename = Path(filename).name

    if filename in {"", ".", ".."}:
        raise ValueError("Invalid upload filename.")

    name = Path(filename).stem
    ext = Path(filename).suffix.lower()
    if ext not in IMAGE_EXTS:
        raise ValueError("Unsupported image extension.")

    name = name.strip()
    name = FILENAME_SANITIZE_RE.sub("", name)
    name = re.sub(r"\s+", " ", name).strip(" .-_")

    if not name:
        raise ValueError("Upload filename does not contain any safe characters.")

    return f"{name}{ext}"


def _sanitize_event_folder_name(event_name: str) -> str:
    if not event_name or not isinstance(event_name, str):
        raise ValueError("Event name required.")

    safe = event_name.replace("\\", " ").replace("/", " ")
    safe = FOLDER_SLUG_SANITIZE_RE.sub(" ", safe)
    safe = re.sub(r"\s+", " ", safe).strip()
    safe = safe.replace(" ", "-")

    if not safe:
        raise ValueError("Invalid event name.")

    return safe


def _resolve_event_folder(folder: str) -> Path:
    if not folder or Path(folder).name != folder:
        raise ValueError("Invalid event folder name.")
    if ".." in folder or folder.startswith(("/", "\\")):
        raise ValueError("Invalid event folder name.")

    folder_path = EVENTS_ROOT / folder
    return _ensure_inside_root(folder_path)


def _sanitize_event_date(event_date: str) -> str:
    if not event_date or not isinstance(event_date, str):
        raise ValueError("Event date required.")

    safe_date = event_date.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", safe_date):
        raise ValueError("Invalid event date.")

    return safe_date


def _validate_image_upload(uploaded_file, filename: str) -> bytes:
    if uploaded_file.size > 5 * 1024 * 1024:
        raise ValueError(f"{filename} exceeds 5MB limit.")

    ext = Path(filename).suffix.lower()
    expected_mimes = IMAGE_MIME_WHITELIST.get(ext)
    if not expected_mimes:
        raise ValueError("Unsupported image extension.")

    content_type = getattr(uploaded_file, "content_type", "") or ""
    if content_type not in expected_mimes:
        raise ValueError("Uploaded file MIME type does not match allowed image type.")

    content = b"".join(chunk for chunk in uploaded_file.chunks())
    if not content:
        raise ValueError("Uploaded file is empty.")

    if content.startswith((b"MZ", b"#!", b"PK\x03\x04")):
        raise ValueError("Executable or archive content is not allowed.")

    try:
        with Image.open(io.BytesIO(content)) as image:
            image_format = image.format
            image.verify()
    except (UnidentifiedImageError, OSError):
        raise ValueError("Uploaded file is not a valid image.")

    allowed_exts = PIL_FORMAT_TO_EXTS.get(image_format)
    if not allowed_exts or ext not in allowed_exts:
        raise ValueError("Image content does not match file extension.")

    return content


def _unique_filename(folder_path: Path, filename: str) -> str:
    candidate = filename
    dest = _ensure_inside_root(folder_path / candidate)
    if not dest.exists():
        return candidate

    name, ext = Path(filename).stem, Path(filename).suffix
    counter = 1
    while True:
        candidate = f"{name}_{counter}{ext}"
        dest = _ensure_inside_root(folder_path / candidate)
        if not dest.exists():
            return candidate
        counter += 1


def _ensure_dirs():
    EVENTS_ROOT.mkdir(parents=True, exist_ok=True)


def _meta_path(folder):
    folder_path = _resolve_event_folder(folder)
    return folder_path / "meta.json"


def _read_meta(folder):
    try:
        path = _meta_path(folder)
    except ValueError:
        return {}

    if not path.exists():
        return {}

    if not path.is_file():
        logger.warning("Event metadata path is not a regular file.")
        return {}

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to read event metadata.")
        return {}


def _write_meta(folder, meta: dict):
    path = _meta_path(folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

def update_event_meta(folder, title_en, title_hi, thumbnail=None):
    """
    Update titles + optional thumbnail safely
    """

    folder_path = _resolve_event_folder(folder)

    if not folder_path.exists():
        raise Exception(f"Event folder '{folder}' does not exist.")

    meta_path = _meta_path(folder)

    meta = {}

    # Read existing meta safely
    if meta_path.exists() and meta_path.is_file():
        try:
            with meta_path.open("r", encoding="utf-8") as f:
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
        thumbnail = Path(thumbnail).name
        if thumbnail and (folder_path / thumbnail).is_file():
            meta["thumbnail"] = thumbnail
        else:
            logger.warning("Requested event thumbnail was not found in the event folder.")

    # Save
    try:
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception("Failed writing event metadata.")
        raise Exception("Could not update event metadata.")

def _format_title(slug):
    return slug.replace("-", " ").title()


def get_all_events():
    """
    Scan EVENTS_ROOT, read each folder's meta.json, return sorted event list.
    """
    _ensure_dirs()
    events = []

    for folder_path in EVENTS_ROOT.iterdir():
        if not folder_path.is_dir():
            continue

        folder_name = folder_path.name

        # Collect image files
        image_files = [
            f.name for f in folder_path.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS
        ]

        # Sort by creation time (upload order)
        image_files.sort(
            key=lambda file_name: (folder_path / file_name).stat().st_ctime
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

    safe_date = _sanitize_event_date(event_date)
    folder_slug = _sanitize_event_folder_name(event_name)
    folder_name = f"{safe_date}_{folder_slug}"
    folder_path = _resolve_event_folder(folder_name)
    folder_path.mkdir(parents=True, exist_ok=True)

    # Write meta
    _write_meta(folder_name, {
        "title_en": event_name.strip(),
        "title_hi": (event_name_hi or event_name).strip(),
    })

    # Save uploaded images
    for uploaded_file in files:
        sanitized_name = _sanitize_upload_filename(uploaded_file.name)
        safe_name = _unique_filename(folder_path, sanitized_name)
        dest_path = _ensure_inside_root(folder_path / safe_name)
        content = _validate_image_upload(uploaded_file, sanitized_name)
        dest_path.write_bytes(content)

    return folder_name


def upload_images_to_existing_event(folder, files):
    """
    Add more images to an existing event folder.
    """
    folder_path = _resolve_event_folder(folder)
    if not folder_path.exists():
        raise Exception(f"Event folder '{folder}' does not exist.")

    for uploaded_file in files:
        sanitized_name = _sanitize_upload_filename(uploaded_file.name)
        safe_name = _unique_filename(folder_path, sanitized_name)
        dest_path = _ensure_inside_root(folder_path / safe_name)
        content = _validate_image_upload(uploaded_file, sanitized_name)
        dest_path.write_bytes(content)


def delete_event(folder):
    """
    Delete an entire event folder (images + meta.json).
    """
    folder_path = _resolve_event_folder(folder)
    if folder_path.exists():
        shutil.rmtree(folder_path)
