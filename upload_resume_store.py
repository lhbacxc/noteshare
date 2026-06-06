from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from config_manager import BASE_DIR


RESUME_STATE_PATH = BASE_DIR / "upload_resume_state.json"
MD5_CHUNK_SIZE = 8 * 1024 * 1024


def calculate_file_md5(local_path: str, cancel_check=None) -> str:
    digest = hashlib.md5()
    with Path(local_path).open("rb") as file:
        while True:
            if cancel_check is not None:
                cancel_check()
            chunk = file.read(MD5_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    if cancel_check is not None:
        cancel_check()
    return digest.hexdigest()


def make_upload_session_key(
    endpoint_url: str,
    bucket: str,
    object_key: str,
    local_path: str,
    *,
    content_md5: str | None = None,
    local_size: int | None = None,
) -> str:
    normalized_md5 = _normalize_md5(content_md5)
    if normalized_md5:
        identity = {
            "endpoint_url": endpoint_url.strip(),
            "bucket": bucket.strip(),
            "object_key": object_key.strip(),
            "local_size": _resolve_local_size(local_path, local_size),
            "content_hash_algorithm": "md5",
            "content_md5": normalized_md5,
        }
        payload = json.dumps(identity, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    path = Path(local_path)
    try:
        stat = path.stat()
        local_size = int(stat.st_size)
        local_mtime_ns = int(stat.st_mtime_ns)
        normalized_path = str(path.resolve())
    except OSError:
        local_size = 0
        local_mtime_ns = 0
        normalized_path = str(path)

    identity = {
        "endpoint_url": endpoint_url.strip(),
        "bucket": bucket.strip(),
        "object_key": object_key.strip(),
        "local_path": normalized_path,
        "local_size": local_size,
        "local_mtime_ns": local_mtime_ns,
    }
    payload = json.dumps(identity, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def find_upload_session_by_content(
    endpoint_url: str,
    bucket: str,
    object_key: str,
    local_path: str,
    local_size: int,
    content_md5: str,
) -> tuple[str, dict[str, Any]] | tuple[None, None]:
    session_key = make_upload_session_key(
        endpoint_url,
        bucket,
        object_key,
        local_path,
        content_md5=content_md5,
        local_size=local_size,
    )
    session = load_upload_session(session_key)
    if isinstance(session, dict):
        return session_key, session

    normalized_md5 = _normalize_md5(content_md5)
    if not normalized_md5:
        return None, None

    latest_key: str | None = None
    latest_session: dict[str, Any] | None = None
    latest_updated_at = ""
    for candidate_key, candidate in list_upload_sessions().items():
        if str(candidate.get("endpoint_url", "")).strip() != endpoint_url.strip():
            continue
        if str(candidate.get("bucket", "")).strip() != bucket.strip():
            continue
        try:
            candidate_size = int(candidate.get("local_size", 0))
        except (TypeError, ValueError):
            continue
        if candidate_size != int(local_size):
            continue
        if _normalize_md5(candidate.get("content_md5")) != normalized_md5:
            continue
        candidate_object_key = str(candidate.get("object_key", "")).strip()
        if not candidate_object_key:
            continue
        updated_at = str(candidate.get("updated_at", "")).strip()
        if latest_session is None or updated_at >= latest_updated_at:
            latest_key = candidate_key
            latest_session = candidate
            latest_updated_at = updated_at

    if latest_key is not None and latest_session is not None:
        return latest_key, latest_session
    return None, None


def find_upload_sessions_for_file(
    endpoint_url: str,
    bucket: str,
    object_key: str,
    local_path: str,
    *,
    content_md5: str | None = None,
    local_size: int | None = None,
) -> dict[str, dict[str, Any]]:
    normalized_endpoint = endpoint_url.strip()
    normalized_bucket = bucket.strip()
    normalized_object_key = object_key.strip()
    normalized_path = _normalize_local_path(local_path)
    normalized_md5 = _normalize_md5(content_md5)
    resolved_size = _resolve_local_size(local_path, local_size)
    expected_keys = {
        make_upload_session_key(endpoint_url, bucket, object_key, local_path),
    }
    if normalized_md5:
        expected_keys.add(
            make_upload_session_key(
                endpoint_url,
                bucket,
                object_key,
                local_path,
                content_md5=normalized_md5,
                local_size=resolved_size,
            )
        )

    matches: dict[str, dict[str, Any]] = {}
    for candidate_key, candidate in list_upload_sessions().items():
        if candidate_key in expected_keys:
            matches[candidate_key] = candidate
            continue
        if str(candidate.get("endpoint_url", "")).strip() != normalized_endpoint:
            continue
        if str(candidate.get("bucket", "")).strip() != normalized_bucket:
            continue
        if str(candidate.get("object_key", "")).strip() != normalized_object_key:
            continue

        candidate_path = _normalize_local_path(str(candidate.get("local_path", "")).strip())
        if candidate_path and candidate_path == normalized_path:
            matches[candidate_key] = candidate
            continue

        if not normalized_md5:
            continue
        try:
            candidate_size = int(candidate.get("local_size", 0))
        except (TypeError, ValueError):
            continue
        if candidate_size != resolved_size:
            continue
        if _normalize_md5(candidate.get("content_md5")) == normalized_md5:
            matches[candidate_key] = candidate

    return matches


def load_upload_session(session_key: str) -> dict[str, Any] | None:
    state = _load_state()
    sessions = state.get("sessions", {})
    if not isinstance(sessions, dict):
        return None
    session = sessions.get(session_key)
    if not isinstance(session, dict):
        return None
    return session


def list_upload_sessions() -> dict[str, dict[str, Any]]:
    state = _load_state()
    sessions = state.get("sessions", {})
    if not isinstance(sessions, dict):
        return {}
    return {
        str(session_key): session
        for session_key, session in sessions.items()
        if isinstance(session, dict)
    }


def save_upload_session(session_key: str, session: dict[str, Any]) -> None:
    state = _load_state()
    sessions = state.get("sessions", {})
    if not isinstance(sessions, dict):
        sessions = {}
    session_to_save = dict(session)
    session_to_save["updated_at"] = _utc_now_text()
    sessions[session_key] = session_to_save
    state["version"] = 1
    state["sessions"] = sessions
    _save_state(state)


def delete_upload_session(session_key: str) -> None:
    state = _load_state()
    sessions = state.get("sessions", {})
    if not isinstance(sessions, dict) or session_key not in sessions:
        return
    sessions.pop(session_key, None)
    state["sessions"] = sessions
    _save_state(state)


def delete_upload_sessions_for_file(
    endpoint_url: str,
    bucket: str,
    object_key: str,
    local_path: str,
    *,
    content_md5: str | None = None,
    local_size: int | None = None,
) -> None:
    for session_key in find_upload_sessions_for_file(
        endpoint_url,
        bucket,
        object_key,
        local_path,
        content_md5=content_md5,
        local_size=local_size,
    ):
        delete_upload_session(session_key)


def _load_state() -> dict[str, Any]:
    if not RESUME_STATE_PATH.exists():
        return {"version": 1, "sessions": {}}
    try:
        with RESUME_STATE_PATH.open("r", encoding="utf-8") as file:
            state = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "sessions": {}}
    if not isinstance(state, dict):
        return {"version": 1, "sessions": {}}
    if not isinstance(state.get("sessions"), dict):
        state["sessions"] = {}
    return state


def _save_state(state: dict[str, Any]) -> None:
    RESUME_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = RESUME_STATE_PATH.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)
    temp_path.replace(RESUME_STATE_PATH)


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _resolve_local_size(local_path: str, local_size: int | None) -> int:
    if local_size is not None:
        try:
            return max(0, int(local_size))
        except (TypeError, ValueError):
            pass
    try:
        return max(0, int(Path(local_path).stat().st_size))
    except OSError:
        return 0


def _normalize_md5(value: object) -> str:
    text = str(value or "").strip().lower()
    if len(text) != 32:
        return ""
    if any(character not in "0123456789abcdef" for character in text):
        return ""
    return text


def _normalize_local_path(local_path: str) -> str:
    if not local_path:
        return ""
    path = Path(local_path)
    try:
        return str(path.resolve())
    except OSError:
        return str(path)
