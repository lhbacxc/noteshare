from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from app_logger import clean_log_level


if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"


def get_default_config() -> dict[str, Any]:
    return {
        "account_id": "",
        "access_key_id": "",
        "secret_access_key": "",
        "endpoint_url": "",
        "worker_base_url": "",
        "worker_admin_token": "",
        "webdav_url": "",
        "webdav_username": "",
        "webdav_password": "",
        "webdav_remote_path": "noteshare/config.json",
        "default_bucket": "",
        "url_expire_seconds": 3600,
        "log_level": "error",
        "recent_buckets": [],
        "object_url_settings": {},
    }


def _clean_config(raw: dict[str, Any]) -> dict[str, Any]:
    config = get_default_config()
    config.update(raw or {})

    config["account_id"] = str(config.get("account_id", "")).strip()
    config["access_key_id"] = str(config.get("access_key_id", "")).strip()
    config["secret_access_key"] = str(config.get("secret_access_key", "")).strip()
    config["endpoint_url"] = str(config.get("endpoint_url", "")).strip()
    config["worker_base_url"] = str(config.get("worker_base_url", "")).strip()
    config["worker_admin_token"] = str(config.get("worker_admin_token", "")).strip()
    config["webdav_url"] = str(config.get("webdav_url", "")).strip()
    config["webdav_username"] = str(config.get("webdav_username", "")).strip()
    config["webdav_password"] = str(config.get("webdav_password", "")).strip()
    config["webdav_remote_path"] = (
        str(config.get("webdav_remote_path", "")).strip() or "noteshare/config.json"
    )
    config["default_bucket"] = str(config.get("default_bucket", "")).strip()
    config["log_level"] = clean_log_level(config.get("log_level", "error"))

    try:
        expire_seconds = int(config.get("url_expire_seconds", 3600))
    except (TypeError, ValueError):
        expire_seconds = 3600
    config["url_expire_seconds"] = max(1, expire_seconds)

    recent_buckets = config.get("recent_buckets", [])
    if not isinstance(recent_buckets, list):
        recent_buckets = []
    config["recent_buckets"] = [
        str(bucket).strip() for bucket in recent_buckets if str(bucket).strip()
    ]

    object_url_settings = config.get("object_url_settings", {})
    if not isinstance(object_url_settings, dict):
        object_url_settings = {}
    config["object_url_settings"] = _clean_object_url_settings(object_url_settings)

    return config


def clean_config_data(raw: dict[str, Any]) -> dict[str, Any]:
    return _clean_config(raw)


def _clean_object_url_settings(raw: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    cleaned: dict[str, dict[str, dict[str, Any]]] = {}

    for bucket_name, bucket_settings in raw.items():
        bucket_key = str(bucket_name).strip()
        if not bucket_key or not isinstance(bucket_settings, dict):
            continue

        cleaned_bucket: dict[str, dict[str, Any]] = {}
        for object_key, object_settings in bucket_settings.items():
            normalized_object_key = str(object_key).strip()
            if not normalized_object_key or not isinstance(object_settings, dict):
                continue

            try:
                expire_seconds = int(object_settings.get("default_expire_seconds", 3600))
            except (TypeError, ValueError):
                expire_seconds = 3600

            cleaned_bucket[normalized_object_key] = {
                "default_expire_seconds": max(1, expire_seconds),
                "last_presigned_url": str(
                    object_settings.get("last_presigned_url", "")
                ).strip(),
                "last_generated_at": str(
                    object_settings.get("last_generated_at", "")
                ).strip(),
                "last_expires_at": str(
                    object_settings.get("last_expires_at", "")
                ).strip(),
                "last_share_token": str(
                    object_settings.get("last_share_token", "")
                ).strip(),
                "last_share_url": str(
                    object_settings.get("last_share_url", "")
                ).strip(),
                "last_share_status": _clean_share_status(
                    object_settings.get("last_share_status", "")
                ),
                "last_share_created_at": str(
                    object_settings.get("last_share_created_at", "")
                ).strip(),
                "last_share_expires_at": str(
                    object_settings.get("last_share_expires_at", "")
                ).strip(),
            }

        cleaned[bucket_key] = cleaned_bucket

    return cleaned


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return get_default_config()

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            raw = json.load(file)
        if not isinstance(raw, dict):
            return get_default_config()
        return _clean_config(raw)
    except (OSError, json.JSONDecodeError):
        return get_default_config()


def save_config(config: dict[str, Any]) -> None:
    cleaned = _clean_config(config)
    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        json.dump(cleaned, file, ensure_ascii=False, indent=2)


def _clean_share_status(value: Any) -> str:
    normalized = str(value).strip().lower()
    if normalized in {"active", "revoked"}:
        return normalized
    return ""
