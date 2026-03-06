from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def append_event(event_path: Path, event: dict[str, object]) -> None:
    event_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {"timestamp": datetime.now(timezone.utc).isoformat(), **event}
    with event_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=True) + "\n")
