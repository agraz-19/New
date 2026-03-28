from minio import Minio
from django.conf import settings
from datetime import datetime
import json
import io


def get_minio_client():
    return Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


def format_title(name):
    """
    Convert folder slug to readable title
    hindi-diwas -> Hindi Diwas
    """
    return name.replace("-", " ").title()


def read_meta(client, bucket, folder):
    """
    Read meta.json from a folder in MinIO.
    Returns a dict, or {} if not found.
    """
    try:
        response = client.get_object(bucket, f"{folder}/meta.json")
        data = json.loads(response.read().decode("utf-8"))
        response.close()
        response.release_conn()
        return data
    except Exception:
        return {}


def write_meta(client, bucket, folder, meta: dict):
    """
    Upload meta.json to the folder in MinIO.
    """
    raw = json.dumps(meta, ensure_ascii=False).encode("utf-8")
    client.put_object(
        bucket,
        f"{folder}/meta.json",
        io.BytesIO(raw),
        length=len(raw),
        content_type="application/json",
    )


def get_all_events():
    client = get_minio_client()
    bucket = settings.MINIO_BUCKET_NAME

    folders = {}
    events = []

    objects = client.list_objects(bucket, recursive=True)

    # Collect images grouped by folder (skip meta.json)
    for obj in objects:

        parts = obj.object_name.split("/")

        if len(parts) < 2:
            continue

        folder = parts[0]
        filename = parts[-1]

        # Skip the meta file itself
        if filename == "meta.json":
            continue

        if filename.lower().endswith(("jpg", "jpeg", "png", "webp")):

            image_url = f"http://{settings.MINIO_ENDPOINT}/{bucket}/{obj.object_name}"

            if folder not in folders:
                folders[folder] = []

            folders[folder].append(image_url)

    # Convert folders to event objects
    for folder, images in folders.items():

        try:

            if "_" in folder and folder[:4].isdigit():
                date_str, slug = folder.split("_", 1)
                event_date = datetime.strptime(date_str, "%Y-%m-%d")
                display_date = event_date.strftime("%d %B %Y")
                sort_date = event_date
            else:
                slug = folder
                display_date = "Unknown Date"
                sort_date = datetime(1900, 1, 1)

            # Read optional Hindi title from meta.json
            meta = read_meta(client, bucket, folder)
            title_en = meta.get("title_en") or format_title(slug)
            title_hi = meta.get("title_hi") or title_en   # fallback to English title

            events.append({
                "folder": folder,
                "title": title_en,           # English title
                "title_hi": title_hi,        # Hindi title
                "date": display_date,
                "thumbnail": images[0],
                "images": images,
                "sort_date": sort_date,
            })

        except Exception as e:
            print("Skipping folder:", folder, e)

    # Sort newest → oldest
    events.sort(key=lambda x: x["sort_date"], reverse=True)

    return events


def upload_event(event_date, event_name, event_name_hi, files):
    """
    Create a new event folder, write meta.json with both titles, upload images.
    """
    client = get_minio_client()
    bucket = settings.MINIO_BUCKET_NAME

    slug = event_name.lower().replace(" ", "-")
    folder = f"{event_date}_{slug}"

    # Save both titles in meta.json
    write_meta(client, bucket, folder, {
        "title_en": event_name,
        "title_hi": event_name_hi or event_name,   # fallback to English if blank
    })

    for file in files:

        if file.size > 5 * 1024 * 1024:
            raise Exception("Image must be under 5MB")

        object_name = f"{folder}/{file.name}"

        client.put_object(
            bucket,
            object_name,
            file,
            length=-1,
            part_size=10 * 1024 * 1024,
            content_type=file.content_type,
        )

    return folder


def delete_event(folder):

    client = get_minio_client()
    bucket = settings.MINIO_BUCKET_NAME

    objects = client.list_objects(bucket, prefix=folder, recursive=True)

    for obj in objects:
        client.remove_object(bucket, obj.object_name)


def upload_images_to_existing_event(folder, files):

    client = get_minio_client()
    bucket = settings.MINIO_BUCKET_NAME

    for file in files:

        object_name = f"{folder}/{file.name}"

        client.put_object(
            bucket,
            object_name,
            file,
            length=-1,
            part_size=10 * 1024 * 1024,
            content_type=file.content_type,
        )