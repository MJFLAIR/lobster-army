import json
from typing import Dict, Any
from tools.llm_adapter import LLMAdapter
from tools.network_client import NetworkClient
from workflows.storage.db import Secrets, Config

class LLMClient(LLMAdapter):
    def __init__(self):
        self.network = NetworkClient()
        self.api_key = Secrets.get_secret_by_alias("llm_api_key") or "mock-key-for-tests"
        # Config for provider/url
        cfg = Config.load("config/api_pool.yaml")
        # Assume a default provider or hardcode for 6B
        self.api_url = cfg.get("openai", {}).get("url", "https://api.openai.com/v1/chat/completions") 
        self.model = "gpt-4o"

    def complete(self, prompt: str, system_prompt: str = None) -> Dict[str, Any]:
        """
        Real Network Call to LLM Provider via NetworkClient.
        """
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2
        }

        try:
            body = json.dumps(payload).encode("utf-8")
            response_bytes = self.network.request(
                method="POST",
                url=self.api_url,
                headers=headers,
                body=body,
                timeout=60
            )
            
            resp_json = json.loads(response_bytes.decode("utf-8"))
            
            # extract content and usage (OpenAI format)
            content = resp_json["choices"][0]["message"]["content"]
            usage = resp_json.get("usage", {})
            
            return {
                "content": content,
                "usage": usage # e.g. {"total_tokens": 123}
            }

        except Exception as e:
            # Phase 6B: If we are in test mode with mocked network, we might get here if mock fails.
            # But normally we expect NetworkClient to raise NetworkPolicyError or urllib error.
            raise RuntimeError(f"LLMClient Request Failed: {e}")
