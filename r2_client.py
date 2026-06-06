from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import ceil
import mimetypes
from pathlib import Path
from typing import Any, Callable

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, HTTPClientError

from upload_control import UploadInterrupted


class R2Error(Exception):
    pass


MIN_MULTIPART_PART_SIZE = 5 * 1024 * 1024
DEFAULT_MULTIPART_PART_SIZE = 64 * 1024 * 1024
MAX_MULTIPART_PARTS = 10000


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

    def upload_file(
        self,
        bucket: str,
        local_path: str,
        object_key: str,
        progress_callback: Callable[[int], None] | None = None,
    ) -> None:
        try:
            extra_args = _build_upload_extra_args(local_path)
            if extra_args:
                self.client.upload_file(
                    local_path,
                    bucket,
                    object_key,
                    ExtraArgs=extra_args,
                    Callback=progress_callback,
                )
            else:
                self.client.upload_file(
                    local_path,
                    bucket,
                    object_key,
                    Callback=progress_callback,
                )
        except HTTPClientError as exc:
            interrupted = _upload_interruption_from_http_error(exc)
            if interrupted is not None:
                raise interrupted from exc
            raise R2Error(_format_boto_error(exc)) from exc
        except UploadInterrupted:
            raise
        except (ClientError, BotoCoreError, OSError) as exc:
            raise R2Error(_format_boto_error(exc)) from exc

    def upload_resumable_file(
        self,
        bucket: str,
        local_path: str,
        object_key: str,
        *,
        resume_session: dict[str, Any] | None = None,
        session_callback: Callable[[dict[str, Any]], None] | None = None,
        progress_callback: Callable[[int], None] | None = None,
        resumed_callback: Callable[[int], None] | None = None,
        cancel_check: Callable[[], None] | None = None,
        content_md5: str = "",
    ) -> None:
        path = Path(local_path)
        try:
            file_size = max(0, path.stat().st_size)
            if file_size == 0:
                put_args: dict[str, Any] = {"Bucket": bucket, "Key": object_key, "Body": b""}
                put_args.update(_build_upload_extra_args(local_path))
                self.client.put_object(**put_args)
                return

            part_size = _choose_part_size(file_size, resume_session)
            upload_id = _session_upload_id(resume_session)
            completed_parts: dict[int, dict[str, Any]] = {}

            if upload_id:
                remote_parts = self._list_multipart_parts(bucket, object_key, upload_id)
                if remote_parts is None:
                    upload_id = ""
                else:
                    completed_parts = {
                        part_number: {
                            "PartNumber": part_number,
                            "ETag": etag,
                            "Size": _part_length(file_size, part_size, part_number),
                        }
                        for part_number, etag in remote_parts.items()
                    }

            if not upload_id:
                upload_id = self._create_multipart_upload(bucket, object_key, local_path)
                completed_parts = {}

            session = _build_resume_session(
                self.credentials.endpoint_url,
                bucket,
                object_key,
                local_path,
                upload_id,
                part_size,
                file_size,
                completed_parts,
                content_md5,
            )
            _notify_session(session_callback, session)

            resumed_bytes = sum(int(part.get("Size", 0)) for part in completed_parts.values())
            if resumed_callback is not None:
                resumed_callback(min(file_size, resumed_bytes))

            part_count = ceil(file_size / part_size)
            for part_number in range(1, part_count + 1):
                if part_number in completed_parts:
                    continue
                if cancel_check is not None:
                    cancel_check()

                offset = (part_number - 1) * part_size
                length = _part_length(file_size, part_size, part_number)
                body = _ProgressFilePart(path, offset, length, progress_callback, cancel_check)
                try:
                    response = self.client.upload_part(
                        Bucket=bucket,
                        Key=object_key,
                        UploadId=upload_id,
                        PartNumber=part_number,
                        Body=body,
                        ContentLength=length,
                    )
                finally:
                    body.close()
                etag = str(response.get("ETag", "")).strip()
                if not etag:
                    raise R2Error(f"上传分片 {part_number} 后未返回 ETag")

                completed_parts[part_number] = {
                    "PartNumber": part_number,
                    "ETag": etag,
                    "Size": length,
                }
                session = _build_resume_session(
                    self.credentials.endpoint_url,
                    bucket,
                    object_key,
                    local_path,
                    upload_id,
                    part_size,
                    file_size,
                    completed_parts,
                    content_md5,
                )
                _notify_session(session_callback, session)

            complete_parts = [
                {"PartNumber": part_number, "ETag": part["ETag"]}
                for part_number, part in sorted(completed_parts.items())
            ]
            self.client.complete_multipart_upload(
                Bucket=bucket,
                Key=object_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": complete_parts},
            )
        except HTTPClientError as exc:
            interrupted = _upload_interruption_from_http_error(exc)
            if interrupted is not None:
                raise interrupted from exc
            raise R2Error(_format_boto_error(exc)) from exc
        except UploadInterrupted:
            raise
        except (ClientError, BotoCoreError, OSError) as exc:
            raise R2Error(_format_boto_error(exc)) from exc

    def download_file(self, bucket: str, object_key: str, local_path: str) -> None:
        destination = Path(local_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.client.download_file(bucket, object_key, str(destination))
        except (ClientError, BotoCoreError, OSError) as exc:
            raise R2Error(_format_boto_error(exc)) from exc

    def abort_multipart_upload(self, bucket: str, object_key: str, upload_id: str) -> None:
        try:
            self.client.abort_multipart_upload(
                Bucket=bucket,
                Key=object_key,
                UploadId=upload_id,
            )
        except ClientError as exc:
            if _is_missing_multipart_upload(exc):
                return
            raise R2Error(_format_boto_error(exc)) from exc
        except BotoCoreError as exc:
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

    def _create_multipart_upload(self, bucket: str, object_key: str, local_path: str) -> str:
        create_args: dict[str, Any] = {"Bucket": bucket, "Key": object_key}
        create_args.update(_build_upload_extra_args(local_path))
        response = self.client.create_multipart_upload(**create_args)
        upload_id = str(response.get("UploadId", "")).strip()
        if not upload_id:
            raise R2Error("创建 multipart upload 后未返回 upload id")
        return upload_id

    def _list_multipart_parts(
        self,
        bucket: str,
        object_key: str,
        upload_id: str,
    ) -> dict[int, str] | None:
        try:
            paginator = self.client.get_paginator("list_parts")
            page_iterator = paginator.paginate(
                Bucket=bucket,
                Key=object_key,
                UploadId=upload_id,
            )
            parts: dict[int, str] = {}
            for page in page_iterator:
                for part in page.get("Parts", []):
                    part_number = int(part.get("PartNumber", 0))
                    etag = str(part.get("ETag", "")).strip()
                    if part_number > 0 and etag:
                        parts[part_number] = etag
            return parts
        except ClientError as exc:
            if _is_missing_multipart_upload(exc):
                return None
            raise


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


def _choose_part_size(file_size: int, resume_session: dict[str, Any] | None) -> int:
    try:
        session_part_size = int((resume_session or {}).get("part_size", 0))
    except (TypeError, ValueError):
        session_part_size = 0
    if session_part_size >= MIN_MULTIPART_PART_SIZE:
        return session_part_size
    minimum_for_part_limit = ceil(max(1, file_size) / MAX_MULTIPART_PARTS)
    return max(DEFAULT_MULTIPART_PART_SIZE, MIN_MULTIPART_PART_SIZE, minimum_for_part_limit)


def _session_upload_id(resume_session: dict[str, Any] | None) -> str:
    if not isinstance(resume_session, dict):
        return ""
    return str(resume_session.get("upload_id", "")).strip()


def _part_length(file_size: int, part_size: int, part_number: int) -> int:
    offset = (part_number - 1) * part_size
    return max(0, min(part_size, file_size - offset))


def _build_resume_session(
    endpoint_url: str,
    bucket: str,
    object_key: str,
    local_path: str,
    upload_id: str,
    part_size: int,
    file_size: int,
    completed_parts: dict[int, dict[str, Any]],
    content_md5: str = "",
) -> dict[str, Any]:
    path = Path(local_path)
    try:
        stat = path.stat()
        local_mtime_ns = int(stat.st_mtime_ns)
        normalized_path = str(path.resolve())
    except OSError:
        local_mtime_ns = 0
        normalized_path = str(path)
    return {
        "endpoint_url": endpoint_url,
        "bucket": bucket,
        "object_key": object_key,
        "local_path": normalized_path,
        "local_size": file_size,
        "local_mtime_ns": local_mtime_ns,
        "content_hash_algorithm": "md5" if content_md5 else "",
        "content_md5": content_md5,
        "upload_id": upload_id,
        "part_size": part_size,
        "parts": [
            {
                "PartNumber": int(part["PartNumber"]),
                "ETag": str(part["ETag"]),
                "Size": int(part.get("Size", 0)),
            }
            for _part_number, part in sorted(completed_parts.items())
        ],
    }


def _notify_session(
    session_callback: Callable[[dict[str, Any]], None] | None,
    session: dict[str, Any],
) -> None:
    if session_callback is not None:
        session_callback(session)


def _is_missing_multipart_upload(exc: ClientError) -> bool:
    error = exc.response.get("Error", {})
    code = str(error.get("Code", "")).strip()
    return code in {"NoSuchUpload", "NoSuchKey", "404", "NotFound"}


def _upload_interruption_from_http_error(exc: HTTPClientError) -> UploadInterrupted | None:
    error = getattr(exc, "kwargs", {}).get("error")
    if isinstance(error, UploadInterrupted):
        return error
    message = str(error or exc)
    if "上传已暂停" in message:
        return UploadInterrupted("pause")
    if "上传已取消" in message:
        return UploadInterrupted("cancel")
    return None


class _ProgressFilePart:
    def __init__(
        self,
        path: Path,
        offset: int,
        length: int,
        progress_callback: Callable[[int], None] | None,
        cancel_check: Callable[[], None] | None,
    ) -> None:
        self._file = path.open("rb")
        self._start = offset
        self._length = length
        self._file.seek(offset)
        self._position = 0
        self._reported_position = 0
        self._progress_callback = progress_callback
        self._cancel_check = cancel_check

    def read(self, size: int = -1) -> bytes:
        if self._cancel_check is not None:
            self._cancel_check()
        remaining = self._length - self._position
        if remaining <= 0:
            return b""
        if size is None or size < 0:
            size = remaining
        size = min(size, remaining)
        data = self._file.read(size)
        read_size = len(data)
        self._position += read_size
        reportable_size = max(0, self._position - self._reported_position)
        if reportable_size > 0 and self._progress_callback is not None:
            self._progress_callback(reportable_size)
            self._reported_position = self._position
        return data

    def tell(self) -> int:
        return self._position

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            new_position = offset
        elif whence == 1:
            new_position = self._position + offset
        elif whence == 2:
            new_position = self._length + offset
        else:
            raise OSError("不支持的 seek whence")
        if new_position < 0 or new_position > self._length:
            raise OSError("multipart part stream seek 超出范围")
        self._position = new_position
        self._file.seek(self._start + self._position)
        return self._position

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "_ProgressFilePart":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
