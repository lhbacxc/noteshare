from __future__ import annotations

import json
from typing import Any
from urllib import error, request


class WorkerClientError(Exception):
    pass


class WorkerClient:
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    )

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
            "User-Agent": self.DEFAULT_USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
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

        compact_body = " ".join(raw_body.split())
        if compact_body:
            preview = compact_body[:180]
            return f"Worker 返回错误（{status}）：{preview}"

    if status == 403:
        return (
            "Worker 返回错误（403）：访问被 Cloudflare 拒绝。"
            "请检查 Worker 地址、ADMIN_TOKEN、workers.dev 访问策略，"
            "以及当前网络环境是否被 Cloudflare 拦截。"
        )

    return f"Worker 返回错误（{status}）。"
