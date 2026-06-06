from __future__ import annotations


class UploadInterrupted(Exception):
    def __init__(self, reason: str = "cancel") -> None:
        self.reason = reason
        message = "上传已暂停" if reason == "pause" else "上传已取消"
        super().__init__(message)
