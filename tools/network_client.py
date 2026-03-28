import urllib.request
from urllib.parse import urlparse
from typing import Dict, Optional
from workflows.storage.db import Config

class NetworkPolicyError(Exception):
    pass

class NetworkClient:
    def __init__(self):
        cfg = Config.load("config/network.yaml")
        self.mode = cfg.get("network", {}).get("mode", "deny_by_default")
        self.allow = set(cfg.get("network", {}).get("allowlist_domains", []))

    def request(self, method: str, url: str, headers: Optional[Dict[str, str]] = None, body: Optional[bytes] = None, timeout: int = 30) -> bytes:
        host = urlparse(url).hostname or ""
        
        if self.mode == "deny_by_default":
            if host not in self.allow:
                 raise NetworkPolicyError(f"Outbound host not allowlisted: {host}")

        req = urllib.request.Request(url=url, method=method.upper(), data=body, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
