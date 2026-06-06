from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import HTTPBasicAuthHandler, HTTPPasswordMgrWithDefaultRealm, Request, build_opener

from config_manager import CONFIG_PATH, clean_config_data


class WebDavSyncError(Exception):
    pass


@dataclass(frozen=True)
class WebDavSettings:
    url: str
    username: str
    password: str
    remote_path: str


def make_webdav_settings(config: dict[str, Any]) -> WebDavSettings:
    url = str(config.get("webdav_url", "")).strip()
    username = str(config.get("webdav_username", "")).strip()
    password = str(config.get("webdav_password", "")).strip()
    remote_path = str(config.get("webdav_remote_path", "")).strip()
    if not url:
        raise WebDavSyncError("请先填写 WebDAV URL。")
    if not remote_path:
        raise WebDavSyncError("请先填写 WebDAV 远端路径。")
    if remote_path.endswith("/"):
        raise WebDavSyncError("WebDAV 远端路径需要包含文件名，例如 noteshare/config.json。")
    return WebDavSettings(
        url=url,
        username=username,
        password=password,
        remote_path=remote_path.lstrip("/"),
    )


def upload_config_to_webdav(config: dict[str, Any]) -> str:
    settings = make_webdav_settings(config)
    client = _WebDavClient(settings)
    client.ensure_parent_dirs()
    try:
        data = CONFIG_PATH.read_bytes()
    except OSError as exc:
        raise WebDavSyncError(f"读取本地配置失败：{exc}") from exc
    client.put(data)
    return settings.remote_path


def download_config_from_webdav(config: dict[str, Any]) -> dict[str, Any]:
    settings = make_webdav_settings(config)
    client = _WebDavClient(settings)
    raw_data = client.get()
    try:
        payload = json.loads(raw_data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WebDavSyncError("远端配置不是有效的 UTF-8 JSON 文件。") from exc
    if not isinstance(payload, dict):
        raise WebDavSyncError("远端配置格式不正确，顶层必须是 JSON 对象。")
    cleaned = clean_config_data(payload)
    try:
        CONFIG_PATH.write_text(
            json.dumps(cleaned, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        raise WebDavSyncError(f"写入本地配置失败：{exc}") from exc
    return cleaned


class _WebDavClient:
    def __init__(self, settings: WebDavSettings) -> None:
        self.settings = settings
        password_manager = HTTPPasswordMgrWithDefaultRealm()
        if settings.username or settings.password:
            password_manager.add_password(
                None,
                settings.url,
                settings.username,
                settings.password,
            )
        self.opener = build_opener(HTTPBasicAuthHandler(password_manager))

    def ensure_parent_dirs(self) -> None:
        parent_path = PurePosixPath(self.settings.remote_path).parent
        if str(parent_path) in {"", "."}:
            return
        current = PurePosixPath()
        for part in parent_path.parts:
            current = current / part
            self._request("MKCOL", self._url_for_path(str(current)), ok_statuses={201, 405})

    def put(self, data: bytes) -> None:
        self._request(
            "PUT",
            self._url_for_path(self.settings.remote_path),
            data=data,
            ok_statuses={200, 201, 204},
        )

    def get(self) -> bytes:
        return self._request(
            "GET",
            self._url_for_path(self.settings.remote_path),
            ok_statuses={200},
        )

    def _request(
        self,
        method: str,
        url: str,
        *,
        data: bytes | None = None,
        ok_statuses: set[int],
    ) -> bytes:
        request = Request(url, data=data, method=method)
        if data is not None:
            request.add_header("Content-Type", "application/json; charset=utf-8")
            request.add_header("Content-Length", str(len(data)))
        try:
            with self.opener.open(request, timeout=30) as response:
                status = int(response.status)
                body = response.read()
        except HTTPError as exc:
            if exc.code in ok_statuses:
                return exc.read()
            raise WebDavSyncError(f"WebDAV 请求失败：HTTP {exc.code} {exc.reason}") from exc
        except URLError as exc:
            raise WebDavSyncError(f"WebDAV 连接失败：{exc.reason}") from exc
        except OSError as exc:
            raise WebDavSyncError(f"WebDAV 请求失败：{exc}") from exc
        if status not in ok_statuses:
            raise WebDavSyncError(f"WebDAV 请求失败：HTTP {status}")
        return body

    def _url_for_path(self, remote_path: str) -> str:
        base_url = self.settings.url.rstrip("/") + "/"
        split = urlsplit(base_url)
        base_path = split.path.rstrip("/")
        encoded_parts = [quote(part) for part in remote_path.split("/") if part]
        remote = "/".join(encoded_parts)
        full_path = f"{base_path}/{remote}" if base_path else f"/{remote}"
        return urlunsplit((split.scheme, split.netloc, full_path, "", ""))
