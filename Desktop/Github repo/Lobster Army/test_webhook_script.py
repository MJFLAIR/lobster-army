import json
import requests
import hmac
import hashlib
import os

secret = "test_secret_for_local"
os.environ["GITHUB_WEBHOOK_SECRET"] = secret

payload_dict = {
    "action": "opened",
    "pull_request": {
        "number": 999,
        "title": "Local test PR",
        "html_url": "https://github.com/lobster/repo/pull/999",
        "head": {"sha": "headsha123", "ref": "feature-branch"},
        "base": {"ref": "main"}
    },
    "repository": {"full_name": "lobster/repo"},
    "sender": {"login": "local_dev"}
}
payload = json.dumps(payload_dict).encode('utf-8')
hmac_gen = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256)
signature = f"sha256={hmac_gen.hexdigest()}"

try:
    res = requests.post(
        "http://127.0.0.1:5000/api/webhook/github",
        data=payload,
        headers={
            "X-Hub-Signature-256": signature,
            "X-GitHub-Event": "pull_request",
            "Content-Type": "application/json"
        }
    )
    print("Webhook Response Code:", res.status_code)
    try:
        print("Webhook JSON Response:", res.json())
    except:
        print("Webhook Response Text:", res.text)
except requests.exceptions.ConnectionError:
    print("Error: Could not connect to 127.0.0.1:5000. Is the Gateway running?")
