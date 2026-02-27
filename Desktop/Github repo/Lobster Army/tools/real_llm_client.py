import os
import json
import logging
from typing import Dict, Any, Optional

from tools.llm_adapter import LLMAdapter
from tools.json_extract import extract_json

class RealLLMClient(LLMAdapter):
    """
    Real LLMClient that hits remote APIs (OpenAI by default).
    Handles timeout, retries, and token cost guards.
    """

    def __init__(self):
        self.timeout = int(os.environ.get("LLM_TIMEOUT_S", "60"))
        self.max_retries = int(os.environ.get("LLM_RETRY", "2"))
        self.max_tokens_guard = int(os.environ.get("LLM_MAX_TOKENS", "5000"))
        self.model = os.environ.get("LLM_MODEL", "gpt-4o-mini")

        try:
            from openai import OpenAI
            self.client = OpenAI(
                timeout=self.timeout,
                max_retries=self.max_retries
            )
        except ImportError:
            self.client = None

    def complete(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Executes a real remote LLM request with extraction.
        Raises exception if it fails (so fallback can handle it).
        """
        if self.client is None:
            raise RuntimeError("openai package is not installed. Cannot use RealLLMClient.")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})

        try:

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2, # Low temperature for more deterministic JSON
                max_tokens=self.max_tokens_guard,
                response_format={"type": "json_object"} if "gpt" in self.model else None
            )

            content = response.choices[0].message.content
            usage = response.usage
            total_tokens = usage.total_tokens if usage else 0

            # Verify it didn't hit our token limit
            if total_tokens > self.max_tokens_guard:
                raise ValueError(f"Token limit exceeded: {total_tokens} > {self.max_tokens_guard}")

            # Extract JSON to ensure it's valid
            extracted = extract_json(content)

            # Return standard format
            return {
                "content": json.dumps(extracted),
                "usage": {"total_tokens": total_tokens}
            }

        except Exception as e:
            logging.error(f"RealLLMClient request failed: {e}")
            raise
