"""S3_BUCKET must be a name for boto3; users sometimes paste object URLs."""

import pytest

from app.config import Settings, normalize_s3_bucket_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("videosrv", "videosrv"),
        (
            "https://videosrv.s3.ap-south-1.amazonaws.com/videosrv/",
            "videosrv",
        ),
        (
            "https://s3.ap-south-1.amazonaws.com/my-bucket/prefix/key",
            "my-bucket",
        ),
    ],
)
def test_normalize_s3_bucket_name(raw: str, expected: str) -> None:
    assert normalize_s3_bucket_name(raw) == expected


def test_settings_s3_bucket_validator() -> None:
    s = Settings(
        S3_BUCKET="https://videosrv.s3.ap-south-1.amazonaws.com/videosrv/",
        S3_REGION="ap-south-1",
    )
    assert s.s3_bucket == "videosrv"
