import os
import json
import logging
from typing import Dict, Any, Optional

from tools.llm_adapter import LLMAdapter
# 🗑️ 已經移除舊的 tools.json_extract

class RealLLMClient(LLMAdapter):
    """
    Real LLMClient that hits remote APIs (OpenAI or Gemini).
    Handles timeout, retries, and token cost guards.
    """
    def __init__(self, provider: str, model: str):
        self.provider = provider.lower()
        self.model = model
        self.timeout = int(os.environ.get("LLM_TIMEOUT_S", "60"))
        self.max_retries = int(os.environ.get("LLM_RETRY", "2"))
        self.max_tokens_guard = int(os.environ.get("LLM_MAX_TOKENS", "5000"))
        self.openai_client = None
        self.gemini_model = None

        if self.provider == "openai":
            try:
                from openai import OpenAI
                api_key = os.environ.get("OPENAI_API_KEY", "").strip()
                if not api_key:
                    raise RuntimeError("OPENAI_API_KEY missing")
                self.openai_client = OpenAI(
                    api_key=api_key,
                    timeout=self.timeout,
                    max_retries=self.max_retries
                )
            except ImportError:
                logging.warning("openai package not installed.")

        elif self.provider == "gemini":
            try:
                from google import genai
                api_key = os.environ.get("GEMINI_API_KEY", "").strip()
                if not api_key:
                    raise RuntimeError("GEMINI_API_KEY missing")
                self._genai_client = genai.Client(api_key=api_key)
                self._log_gemini_diag()
            except ImportError:
                logging.warning("google-genai package not installed.")
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: {self.provider}")

    def _log_gemini_diag(self) -> None:
        if os.environ.get("DIAG_GEMINI") != "1":
            return
        auth_mode = "api_key" if os.environ.get("GEMINI_API_KEY") else "adc"
        logging.info(
            "[GEMINI_DIAG] library=google-genai endpoint=generativelanguage.googleapis.com auth_mode=%s model=%s",
            auth_mode,
            self.model,
        )

    def complete(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Executes a real remote LLM request.
        Returns the RAW content string. The parsing is delegated to LLMJSONGuard in the Agents.
        """
        if self.provider == "openai":
            return self._complete_openai(prompt, system_prompt, **kwargs)
        elif self.provider == "gemini":
            return self._complete_gemini(prompt, system_prompt, **kwargs)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def _complete_openai(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        if self.openai_client is None:
            raise RuntimeError("openai package is not installed. Cannot use OpenAI provider.")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,
                max_tokens=self.max_tokens_guard,
                response_format={"type": "json_object"} if "gpt" in self.model else None
            )
            content = response.choices[0].message.content
            usage = response.usage
            total_tokens = usage.total_tokens if usage else 0
            
            if total_tokens > self.max_tokens_guard:
                raise ValueError(
                    f"Token limit exceeded: {total_tokens} > {self.max_tokens_guard}"
                )
            
            # 💡 直接回傳原始字串，不進行任何萃取或轉檔
            return {
                "content": content,
                "usage": {"total_tokens": total_tokens}
            }
        except Exception as e:
            logging.error(f"RealLLMClient (OpenAI) request failed: {e}")
            raise

    def _complete_gemini(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        if not hasattr(self, "_genai_client"):
            raise RuntimeError("google-genai package is not installed. Cannot use Gemini provider.")
        
        try:
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"System Instruction:\n{system_prompt}\n\nTask:\n{prompt}"
            
            response = self._genai_client.models.generate_content(
                model=self.model,
                contents=full_prompt
            )
            content = response.text if response else ""
            
            # 💡 直接回傳原始字串，不進行任何萃取或轉檔
            return {
                "content": content,
                "usage": {"total_tokens": 0}
            }
        except Exception as e:
            logging.error(f"RealLLMClient (Gemini) request failed: {e}")
            raise