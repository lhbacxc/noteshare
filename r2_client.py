from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import mimetypes
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


class R2Error(Exception):
    pass


@dataclass
class R2Credentials:
    account_id: str
    access_key_id: str
    secret_access_key: str
    endpoint_url: str


class R2Manager:
    def __init__(self, credentials: R2Credentials) -> None:
        self.credentials = credentials
        self.client = boto3.client(
            "s3",
            endpoint_url=credentials.endpoint_url,
            aws_access_key_id=credentials.access_key_id,
            aws_secret_access_key=credentials.secret_access_key,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )

    def test_connection(self) -> dict[str, Any]:
        buckets = self.list_buckets()
        return {
            "bucket_count": len(buckets),
            "buckets": buckets,
        }

    def list_buckets(self) -> list[str]:
        try:
            response = self.client.list_buckets()
            buckets = response.get("Buckets", [])
            return [bucket["Name"] for bucket in buckets if bucket.get("Name")]
        except (ClientError, BotoCoreError) as exc:
            raise R2Error(_format_boto_error(exc)) from exc

    def list_objects(self, bucket: str, prefix: str = "") -> list[dict[str, Any]]:
        try:
            paginator = self.client.get_paginator("list_objects_v2")
            page_iterator = paginator.paginate(Bucket=bucket, Prefix=prefix)
            objects: list[dict[str, Any]] = []

            for page in page_iterator:
                for item in page.get("Contents", []):
                    last_modified = item.get("LastModified")
                    objects.append(
                        {
                            "key": item.get("Key", ""),
                            "size": int(item.get("Size", 0)),
                            "last_modified": _format_datetime(last_modified),
                            "storage_class": item.get("StorageClass", ""),
                        }
                    )
            return objects
        except (ClientError, BotoCoreError) as exc:
            raise R2Error(_format_boto_error(exc)) from exc

    def upload_file(self, bucket: str, local_path: str, object_key: str) -> None:
        try:
            extra_args = _build_upload_extra_args(local_path)
            if extra_args:
                self.client.upload_file(
                    local_path,
                    bucket,
                    object_key,
                    ExtraArgs=extra_args,
                )
            else:
                self.client.upload_file(local_path, bucket, object_key)
        except (ClientError, BotoCoreError, OSError) as exc:
            raise R2Error(_format_boto_error(exc)) from exc

    def download_file(self, bucket: str, object_key: str, local_path: str) -> None:
        destination = Path(local_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.client.download_file(bucket, object_key, str(destination))
        except (ClientError, BotoCoreError, OSError) as exc:
            raise R2Error(_format_boto_error(exc)) from exc

    def delete_objects(self, bucket: str, object_keys: list[str]) -> dict[str, Any]:
        deleted: list[str] = []
        errors: list[str] = []

        try:
            for start in range(0, len(object_keys), 1000):
                chunk = object_keys[start : start + 1000]
                response = self.client.delete_objects(
                    Bucket=bucket,
                    Delete={"Objects": [{"Key": key} for key in chunk], "Quiet": False},
                )
                deleted.extend(item["Key"] for item in response.get("Deleted", []))
                errors.extend(
                    f'{item.get("Key", "")}: {item.get("Message", "删除失败")}'
                    for item in response.get("Errors", [])
                )
            return {"deleted": deleted, "errors": errors}
        except (ClientError, BotoCoreError) as exc:
            raise R2Error(_format_boto_error(exc)) from exc

    def generate_presigned_url(
        self,
        bucket: str,
        object_key: str,
        expires_in: int,
    ) -> str:
        try:
            params: dict[str, str] = {"Bucket": bucket, "Key": object_key}
            response_content_type = _guess_content_type(object_key)
            if response_content_type:
                params["ResponseContentType"] = response_content_type
                if _should_force_inline(response_content_type):
                    params["ResponseContentDisposition"] = "inline"
            return self.client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=expires_in,
            )
        except (ClientError, BotoCoreError) as exc:
            raise R2Error(_format_boto_error(exc)) from exc


def _format_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    return ""


def _format_boto_error(exc: Exception) -> str:
    if isinstance(exc, ClientError):
        error = exc.response.get("Error", {})
        code = error.get("Code", "Unknown")
        message = error.get("Message", str(exc))
        return f"{code}: {message}"
    return str(exc)


def _build_upload_extra_args(local_path: str) -> dict[str, str]:
    content_type = _guess_content_type(local_path)
    if not content_type:
        return {}
    return {"ContentType": content_type}


def _guess_content_type(name: str) -> str | None:
    content_type, _encoding = mimetypes.guess_type(name)
    if not content_type:
        return None
    return _append_utf8_charset(content_type)


def _append_utf8_charset(content_type: str) -> str:
    normalized = content_type.lower()
    if "charset=" in normalized:
        return content_type
    if _is_utf8_textual_content_type(normalized):
        return f"{content_type}; charset=utf-8"
    return content_type


def _is_utf8_textual_content_type(content_type: str) -> bool:
    return (
        content_type.startswith("text/")
        or content_type in {"application/javascript", "application/json", "application/xml"}
        or content_type.endswith("+json")
        or content_type.endswith("+xml")
        or content_type == "image/svg+xml"
    )


def _should_force_inline(content_type: str) -> bool:
    base_type = content_type.split(";", 1)[0].strip().lower()
    return _is_utf8_textual_content_type(base_type)
