import json
import pytest
from unittest.mock import patch
from gateway.app import create_app
from nacl.signing import SigningKey
from nacl.encoding import HexEncoder

@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"

@patch("gateway.discord_verify.Secrets")
def test_discord_interaction_valid(mock_secrets, client):
    # Generate a keypair
    signing_key = SigningKey.generate()
    verify_key = signing_key.verify_key
    public_key_hex = verify_key.encode(encoder=HexEncoder).decode("utf-8")
    
    # Mock the secret retrieval to return our generated public key
    mock_secrets.get_secret_by_alias.return_value = public_key_hex

    # Create payload and signature
    payload = json.dumps({"type": 1}).encode("utf-8")
    timestamp = "1234567890"
    message = timestamp.encode("utf-8") + payload
    signature = signing_key.sign(message).signature.hex()

    headers = {
        "X-Signature-Ed25519": signature,
        "X-Signature-Timestamp": timestamp
    }

    resp = client.post("/discord/interactions", data=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json["type"] == 1

@patch("gateway.discord_verify.Secrets")
def test_discord_interaction_invalid(mock_secrets, client):
    mock_secrets.get_secret_by_alias.return_value = "00" * 32
    
    resp = client.post("/discord/interactions", data=b"{}", headers={
        "X-Signature-Ed25519": "bad_sig",
        "X-Signature-Timestamp": "123"
    })
    assert resp.status_code == 401

@patch("gateway.ide_relay.Secrets")
def test_ide_relay_valid(mock_secrets, client):
    mock_secrets.get_secret_by_alias.return_value = "secret-token"
    
    payload = {"requester_id": "test", "channel": "test", "text": "hello"}
    resp = client.post("/ide/relay", json=payload, headers={"X-IDE-Relay-Token": "secret-token"})
    
    assert resp.status_code == 200
    assert resp.json["ok"] is True

@patch("gateway.ide_relay.Secrets")
def test_ide_relay_invalid(mock_secrets, client):
    mock_secrets.get_secret_by_alias.return_value = "secret-token"
    
    resp = client.post("/ide/relay", json={}, headers={"X-IDE-Relay-Token": "wrong-token"})
    assert resp.status_code == 401

def test_webhook_valid(client):
    # In Phase 2 we hardcoded "mock-shared-token" in verify_shared_token
    resp = client.post("/discord/webhook", json={"command": "ping"}, headers={"X-Webhook-Token": "mock-shared-token"})
    assert resp.status_code == 200
    assert resp.json["ok"] is True
