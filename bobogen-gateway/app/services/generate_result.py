from dataclasses import dataclass, field
from typing import Any


@dataclass
class JsonResult:
    payload: dict[str, Any]
    headers: dict[str, str] = field(default_factory=dict)
