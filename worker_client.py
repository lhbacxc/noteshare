from __future__ import annotations

import json
from typing import Any
from urllib import error, request


class WorkerClientError(Exception):
    pass


class WorkerClient:
    def __init__(self, base_url: str, admin_token: str) -> None:
        normalized_base_url = base_url.strip().rstrip("/")
        if not normalized_base_url:
            raise WorkerClientError("Worker Base URL 不能为空。")
        if not admin_token.strip():
            raise WorkerClientError("Worker Admin Token 不能为空。")

        self.base_url = normalized_base_url
        self.admin_token = admin_token.strip()

    def create_share(
        self,
        bucket: str,
        object_key: str,
        expire_seconds: int,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/shares",
            {
                "bucket": bucket,
                "object_key": object_key,
                "expire_seconds": expire_seconds,
            },
        )

    def revoke_share(self, token: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/shares/revoke",
            {"token": token},
        )

    def get_share(self, token: str) -> dict[str, Any]:
        return self._request("GET", f"/api/shares/{token}")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        data: bytes | None = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.admin_token}",
        }

        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"

        req = request.Request(url, data=data, headers=headers, method=method)

        try:
            with request.urlopen(req, timeout=15) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            raise WorkerClientError(_build_http_error_message(exc)) from exc
        except error.URLError as exc:
            raise WorkerClientError(f"无法连接 Worker：{exc.reason}") from exc

        if not body:
            return {}

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise WorkerClientError("Worker 返回了无法解析的响应。") from exc

        if not isinstance(parsed, dict):
            raise WorkerClientError("Worker 返回的数据格式不正确。")

        return parsed


def _build_http_error_message(exc: error.HTTPError) -> str:
    status = exc.code

    try:
        raw_body = exc.read().decode("utf-8")
    except OSError:
        raw_body = ""

    if raw_body:
        try:
            parsed = json.loads(raw_body)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            detail = str(parsed.get("error", "")).strip()
            if detail:
                return f"Worker 返回错误（{status}）：{detail}"

    return f"Worker 返回错误（{status}）。"
