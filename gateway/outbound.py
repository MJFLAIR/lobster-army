from typing import Dict, Any
from flask import jsonify

def post_async_ack(cmd: Dict[str, Any], task_id: int):
    """
    Returns an immediate ACK to Discord.
    For interaction response type 4 (Channel Message With Source) or 5 (Deferred).
    """
    # Type 4 = Respond immediately
    # We return a message saying the task is queued.
    return jsonify({
        "type": 4, 
        "data": {
            "content": f"🦞 Task queued. ID: `{task_id}`. I'm on it."
        }
    })
