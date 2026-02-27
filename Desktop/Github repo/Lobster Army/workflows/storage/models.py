from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class CommandQueue:
    task_id: int
    status: str
    locked_by: Optional[str] = None
    locked_at: Optional[datetime] = None
    attempts: int = 0

@dataclass
class Event:
    event_id: str
    task_id: int
    ts: datetime
    event_type: str
    payload_json: Dict[str, Any]
