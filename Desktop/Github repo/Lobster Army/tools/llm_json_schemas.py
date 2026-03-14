from typing import Any, Dict, List


def _require_keys(data: Dict[str, Any], keys: List[str]) -> None:
    for k in keys:
        if k not in data:
            raise ValueError(f"missing required field: {k}")


def _require_type(value: Any, t, field: str) -> None:
    if not isinstance(value, t):
        raise ValueError(f"{field} must be {t.__name__}")


def _require_range(value: float, field: str, min_v: float = 0.0, max_v: float = 1.0) -> None:
    if not (min_v <= value <= max_v):
        raise ValueError(f"{field} must be between {min_v} and {max_v}")


# --------------------------------------------------------
# PR Gate schema
# --------------------------------------------------------

def require_pr_gate_schema(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Expected schema:

    {
        "decision": "approve" | "reject",
        "score": float (0..1),
        "reason": string
    }
    """

    if not isinstance(data, dict):
        raise ValueError("root must be object")

    _require_keys(data, ["decision", "score", "reason"])

    decision = data["decision"]
    score = data["score"]
    reason = data["reason"]

    _require_type(decision, str, "decision")
    _require_type(score, (int, float), "score")
    _require_type(reason, str, "reason")

    decision = decision.lower()

    if decision not in ["approve", "reject"]:
        raise ValueError("decision must be 'approve' or 'reject'")

    score = float(score)
    _require_range(score, "score")

    return {
        "decision": decision,
        "score": score,
        "reason": reason.strip()
    }


# --------------------------------------------------------
# PM Agent schema
# --------------------------------------------------------

def require_pm_schema(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Expected schema:

    {
        "tasks": [
            {
                "title": "...",
                "description": "...",
                "priority": "low|medium|high"
            }
        ]
    }
    """

    if not isinstance(data, dict):
        raise ValueError("root must be object")

    _require_keys(data, ["tasks"])

    tasks = data["tasks"]

    if not isinstance(tasks, list):
        raise ValueError("tasks must be array")

    normalized_tasks = []

    for t in tasks:
        if not isinstance(t, dict):
            raise ValueError("task item must be object")

        _require_keys(t, ["title", "description", "priority"])

        title = t["title"]
        desc = t["description"]
        priority = t["priority"]

        _require_type(title, str, "title")
        _require_type(desc, str, "description")
        _require_type(priority, str, "priority")

        priority = priority.lower()

        if priority not in ["low", "medium", "high"]:
            raise ValueError("priority must be low|medium|high")

        normalized_tasks.append({
            "title": title.strip(),
            "description": desc.strip(),
            "priority": priority
        })

    return {"tasks": normalized_tasks}


# --------------------------------------------------------
# Review Agent schema
# --------------------------------------------------------

def require_review_schema(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Expected schema:

    {
        "approved": true | false,
        "comments": [
            {
                "file": "...",
                "line": int,
                "comment": "..."
            }
        ]
    }
    """

    if not isinstance(data, dict):
        raise ValueError("root must be object")

    _require_keys(data, ["approved", "comments"])

    approved = data["approved"]
    comments = data["comments"]

    if not isinstance(approved, bool):
        raise ValueError("approved must be boolean")

    if not isinstance(comments, list):
        raise ValueError("comments must be array")

    normalized_comments = []

    for c in comments:
        if not isinstance(c, dict):
            raise ValueError("comment item must be object")

        _require_keys(c, ["file", "line", "comment"])

        file = c["file"]
        line = c["line"]
        comment = c["comment"]

        _require_type(file, str, "file")
        _require_type(line, int, "line")
        _require_type(comment, str, "comment")

        normalized_comments.append({
            "file": file.strip(),
            "line": line,
            "comment": comment.strip()
        })

    return {
        "approved": approved,
        "comments": normalized_comments
    }