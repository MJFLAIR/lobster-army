from flask import Request
from workflows.storage.db import Secrets

def verify_ide_relay(request: Request) -> bool:
    token = request.headers.get("X-IDE-Relay-Token", "")
    expected = Secrets.get_secret_by_alias("ide_relay_token")
    return token == expected and len(token) > 0
