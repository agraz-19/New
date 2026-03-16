from minio import Minio
from django.conf import settings
from datetime import datetime


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
    rajbhasha-kirti-awards -> Rajbhasha Kirti Awards
    """
    return name.replace("-", " ").title()


def get_all_events():
    client = get_minio_client()
    bucket = settings.MINIO_BUCKET_NAME

    folders = {}
    events = []

    objects = client.list_objects(bucket, recursive=True)

    # Collect images grouped by folder
    for obj in objects:

        parts = obj.object_name.split("/")

        if len(parts) < 2:
            continue

        folder = parts[0]
        filename = parts[-1]

        if filename.lower().endswith(("jpg", "jpeg", "png", "webp")):

            image_url = f"http://{settings.MINIO_ENDPOINT}/{bucket}/{obj.object_name}"

            if folder not in folders:
                folders[folder] = []

            folders[folder].append(image_url)

    # Convert folders to event objects
    for folder, images in folders.items():

        try:

            if "_" in folder and folder[:4].isdigit():
                # Folder with date
                date_str, slug = folder.split("_", 1)

                event_date = datetime.strptime(date_str, "%Y-%m-%d")

                display_date = event_date.strftime("%d %B %Y")

                sort_date = event_date

            else:
                # Folder without date
                slug = folder
                display_date = "Unknown Date"
                sort_date = datetime(1900, 1, 1)

            events.append({
                "folder": folder,
                "title": format_title(slug),
                "date": display_date,
                "thumbnail": images[0],  # first image auto thumbnail
                "images": images,
                "sort_date": sort_date
            })

        except Exception as e:
            print("Skipping folder:", folder, e)

    # Sort newest → oldest
    events.sort(
        key=lambda x: x["sort_date"],
        reverse=True
    )

    return events

def upload_event(event_date, event_name, files):

    client = get_minio_client()
    bucket = settings.MINIO_BUCKET_NAME

    slug = event_name.lower().replace(" ", "-")
    folder = f"{event_date}_{slug}"

    for file in files:

        if file.size > 5 * 1024 * 1024:
            raise Exception("Image must be under 5MB")

        object_name = f"{folder}/{file.name}"

        client.put_object(
            bucket,
            object_name,
            file,
            length=-1,
            part_size=10*1024*1024,
            content_type=file.content_type
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
            part_size=10*1024*1024,
            content_type=file.content_type
        )