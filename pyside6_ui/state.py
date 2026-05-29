from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UiState:
    config_data: dict[str, Any]
    all_objects: list[dict[str, Any]] = field(default_factory=list)
    filtered_objects: list[dict[str, Any]] = field(default_factory=list)
    selected_keys: list[str] = field(default_factory=list)
    current_capacity_bucket: str = ""
    current_capacity_total_bytes: int = 0
    current_capacity_sizes: dict[str, int] = field(default_factory=dict)
    current_capacity_loaded: bool = False
    status_message: str = "就绪"
