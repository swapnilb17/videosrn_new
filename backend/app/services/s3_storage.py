import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings


@contextmanager
def _without_blank_aws_profile() -> Iterator[None]:
    """Blank AWS_PROFILE= in .env makes botocore look up a profile named '' and raises ProfileNotFound."""
    key = "AWS_PROFILE"
    if key not in os.environ:
        yield
        return
    val = os.environ.get(key)
    if val is None or str(val).strip() != "":
        yield
        return
    del os.environ[key]
    try:
        yield
    finally:
        os.environ[key] = val


def s3_client(settings: Settings) -> BaseClient:
    region = (settings.s3_region or "").strip() or None
    profile = (settings.aws_profile or "").strip()
    kw: dict[str, Any] = {}
    endpoint = (settings.s3_endpoint_url or "").strip()
    if endpoint:
        kw["endpoint_url"] = endpoint
    with _without_blank_aws_profile():
        if profile:
            session = boto3.session.Session(
                region_name=region,
                profile_name=profile,
            )
        else:
            session = boto3.session.Session(region_name=region)
        return session.client("s3", **kw)


def upload_file(
    client: BaseClient,
    bucket: str,
    key: str,
    path: Path,
    *,
    content_type: str | None = None,
) -> None:
    extra: dict[str, str] = {}
    if content_type:
        extra["ContentType"] = content_type
    client.upload_file(
        str(path),
        bucket,
        key,
        ExtraArgs=extra if extra else None,
    )


def generate_presigned_get_url(
    client: BaseClient,
    bucket: str,
    key: str,
    *,
    expires_in: int,
    response_content_disposition: str | None = None,
) -> str:
    params: dict[str, Any] = {"Bucket": bucket, "Key": key}
    if response_content_disposition:
        params["ResponseContentDisposition"] = response_content_disposition
    return client.generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=expires_in,
    )


class S3UploadError(RuntimeError):
    pass


def safe_upload(
    settings: Settings,
    local_path: Path,
    key: str,
    *,
    content_type: str | None = None,
) -> None:
    try:
        client = s3_client(settings)
        upload_file(
            client,
            (settings.s3_bucket or "").strip(),
            key,
            local_path,
            content_type=content_type,
        )
    except (BotoCoreError, ClientError, OSError) as e:
        raise S3UploadError(str(e)) from e


def safe_presign_get(
    settings: Settings,
    key: str,
    *,
    attachment: bool = False,
    download_filename: str | None = None,
) -> str:
    disp: str | None = None
    if attachment and download_filename:
        safe = (download_filename or "").replace('"', "").replace("\\", "")
        if safe:
            disp = f'attachment; filename="{safe}"'
    try:
        client = s3_client(settings)
        return generate_presigned_get_url(
            client,
            (settings.s3_bucket or "").strip(),
            key,
            expires_in=max(60, int(settings.media_presign_expires_seconds)),
            response_content_disposition=disp,
        )
    except (BotoCoreError, ClientError) as e:
        raise S3UploadError(str(e)) from e


def upload_job_directory(settings: Settings, job_dir: Path, job_id: str) -> dict[str, str]:
    """Upload standard job outputs; returns logical filename -> S3 object key."""
    client = s3_client(settings)
    bucket = (settings.s3_bucket or "").strip()
    prefix = settings.s3_key_prefix_for_job(job_id)
    keys: dict[str, str] = {}
    pairs: list[tuple[Path, str, str | None]] = [
        (job_dir / "voiceover.mp3", "voiceover.mp3", "audio/mpeg"),
        (job_dir / "output.mp4", "output.mp4", "video/mp4"),
        (job_dir / "script.json", "script.json", "application/json"),
    ]
    try:
        for path, logical_name, ctype in pairs:
            if path.is_file():
                key = prefix + logical_name
                upload_file(client, bucket, key, path, content_type=ctype)
                keys[logical_name] = key
        slides = job_dir / "slides"
        if slides.is_dir():
            for png in sorted(slides.glob("*.png")):
                logical = f"slides/{png.name}"
                key = prefix + logical
                upload_file(client, bucket, key, png, content_type="image/png")
                keys[logical] = key
        title = job_dir / "title.png"
        if title.is_file():
            key = prefix + "title.png"
            upload_file(client, bucket, key, title, content_type="image/png")
            keys["title.png"] = key
        brand = job_dir / "branding_logo.png"
        if brand.is_file():
            key = prefix + "branding_logo.png"
            upload_file(client, bucket, key, brand, content_type="image/png")
            keys["branding_logo.png"] = key
        for logical, ctype in (
            ("user_product.png", "image/png"),
            ("user_cta.png", "image/png"),
            ("user_thumbnail.jpg", "image/jpeg"),
        ):
            p = job_dir / logical
            if p.is_file():
                key = prefix + logical
                upload_file(client, bucket, key, p, content_type=ctype)
                keys[logical] = key
        addr_txt = job_dir / "user_address.txt"
        if addr_txt.is_file():
            key = prefix + "user_address.txt"
            upload_file(client, bucket, key, addr_txt, content_type="text/plain; charset=utf-8")
            keys["user_address.txt"] = key
    except (BotoCoreError, ClientError, OSError) as e:
        raise S3UploadError(str(e)) from e
    if "voiceover.mp3" not in keys or "output.mp4" not in keys:
        raise S3UploadError("Missing voiceover.mp3 or output.mp4 after upload")
    return keys


def ensure_bucket_exists(client: BaseClient, bucket: str, region: str) -> None:
    """Dev/tests only — create bucket if missing (e.g. moto)."""
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as e:
        code = (e.response.get("Error") or {}).get("Code", "")
        if code not in ("404", "403", "NoSuchBucket"):
            raise
        r = (region or "").strip() or "us-east-1"
        if r == "us-east-1":
            client.create_bucket(Bucket=bucket)
        else:
            client.create_bucket(
                Bucket=bucket,
                CreateBucketConfiguration={"LocationConstraint": r},
            )
