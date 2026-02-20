from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime

@dataclass
class Task:
    task_id: int
    source: str
    requester_id: str
    channel_id: Optional[str] = None
    description: str = ""
    status: str = "PENDING"
    branch_name: Optional[str] = None
    plan_json: Optional[Dict[str, Any]] = None
    result_summary: Optional[str] = None
    cost_json: Optional[Dict[str, Any]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

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
