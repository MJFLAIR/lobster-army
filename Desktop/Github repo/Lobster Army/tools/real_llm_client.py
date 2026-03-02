import os
import json
import logging
from typing import Dict, Any, Optional

from tools.llm_adapter import LLMAdapter
from tools.json_extract import extract_json

class RealLLMClient(LLMAdapter):
    """
    Real LLMClient that hits remote APIs (OpenAI or Gemini).
    Handles timeout, retries, and token cost guards.
    """

    def __init__(self):
        self.provider = os.environ.get("LLM_PROVIDER", "openai").lower()
        self.timeout = int(os.environ.get("LLM_TIMEOUT_S", "60"))
        self.max_retries = int(os.environ.get("LLM_RETRY", "2"))
        self.max_tokens_guard = int(os.environ.get("LLM_MAX_TOKENS", "5000"))
        self.model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
        
        self.openai_client = None
        self.gemini_model = None

        if self.provider == "openai":
            try:
                from openai import OpenAI
                self.openai_client = OpenAI(
                    timeout=self.timeout,
                    max_retries=self.max_retries
                )
            except ImportError:
                logging.warning("openai package not installed.")
        elif self.provider == "gemini":
            try:
                import google.generativeai as genai
                # Configure API key only if it's there; assume IAM otherwise
                api_key = os.environ.get("GEMINI_API_KEY")
                if api_key:
                    genai.configure(api_key=api_key)
                
                # We instantiate the model dynamically later in _complete_gemini,
                # but we can try to import module here for fast failure check
                self._genai = genai
            except ImportError:
                logging.warning("google-generativeai package not installed.")
        else:
            raise ValueError(f"Unsupported LLM_PROVIDER: {self.provider}")

    def complete(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """
        Executes a real remote LLM request with extraction.
        Raises exception if it fails (so fallback can handle it).
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
            logging.error(f"RealLLMClient (OpenAI) request failed: {e}")
            raise

    def _complete_gemini(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        if not hasattr(self, "_genai"):
            raise RuntimeError("google-generativeai package is not installed. Cannot use Gemini provider.")
        
        try:
            # Setup generation config (temperature, max tokens)
            generation_config = self._genai.GenerationConfig(
                temperature=0.2,
                max_output_tokens=self.max_tokens_guard
            )
            
            # Combine system_prompt and prompt for Gemini, or use system_instruction if available in model
            # To be safe across versions, we merge them into the text query
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"System Instruction:\n{system_prompt}\n\nTask:\n{prompt}"
                
            model = self._genai.GenerativeModel(self.model)
            response = model.generate_content(
                full_prompt,
                generation_config=generation_config
            )

            # Use `.text` safely
            content = response.text if response and response.parts else ""

            # Extract JSON to ensure it's valid
            extracted = extract_json(content)

            return {
                "content": json.dumps(extracted),
                "usage": {"total_tokens": 0} # As per requirement, Gemini usage can return 0
            }

        except Exception as e:
            logging.error(f"RealLLMClient (Gemini) request failed: {e}")
            raise
