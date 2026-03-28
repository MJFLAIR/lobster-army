from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime

@dataclass
class Task:
    task_id: int
    source: Optional[str] = None
    requester_id: Optional[str] = None
    channel_id: Optional[str] = None
    description: Optional[str] = None
    branch_name: Optional[str] = None
    plan_json: Optional[Dict[str, Any]] = None
    result_summary: Optional[str] = None
    cost_json: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None
    meta_json: Optional[Dict[str, Any]] = None