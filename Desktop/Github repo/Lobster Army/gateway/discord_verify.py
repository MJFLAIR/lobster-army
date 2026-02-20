import nacl.signing
import nacl.exceptions
from flask import Request
from workflows.storage.db import Secrets

def verify_discord_interaction(request: Request) -> bool:
    sig = request.headers.get("X-Signature-Ed25519", "")
    ts = request.headers.get("X-Signature-Timestamp", "")
    if not sig or not ts:
        return False

    raw_body = request.get_data()
    message = ts.encode("utf-8") + raw_body

    public_key_hex = Secrets.get_secret_by_alias("discord_public_key")
    if not public_key_hex:
        return False
        
    try:
        verify_key = nacl.signing.VerifyKey(bytes.fromhex(public_key_hex))
        verify_key.verify(message, bytes.fromhex(sig))
        return True
    except (ValueError, nacl.exceptions.BadSignatureError):
        return False
