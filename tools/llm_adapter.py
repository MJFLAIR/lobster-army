from typing import Dict, Any
from abc import ABC, abstractmethod

class LLMAdapter(ABC):
    @abstractmethod
    def complete(self, prompt: str, system_prompt: str = None, **kwargs) -> Dict[str, Any]:
        pass

class FakeLLMAdapter(LLMAdapter):
    """
    Simulates LLM responses for testing/dev without external calls.
    Returns structured data based on keywords in the prompt to simulate different agents.
    """
    def complete(self, prompt: str, system_prompt: str = None, **kwargs) -> Dict[str, Any]:
        # Simple keyword matching to determine which agent is calling and what to return
        
        # PM Agent Response
        if "You are a Product Manager" in (system_prompt or ""):
            return {
                "content": '{"plan": [{"step": 1, "description": "Update README"}], "verification": "Check file"}',
                "usage": {"total_tokens": 100}
            }
            
        # Code Agent Response
        if "You are a Senior Python Engineer" in (system_prompt or ""):
            return {
                "content": '{"diff": "diff --git a/README.md b/README.md\\nindex...\\n+ New Content", "commits": ["Update README"]}',
                "usage": {"total_tokens": 200}
            }
            
        # Review Agent Response
        if "You are a Code Reviewer" in (system_prompt or ""):
            return {
                "content": '{"status": "PASS", "score": 90, "comments": "Looks good"}',
                "usage": {"total_tokens": 50}
            }

        # Default fallback
        return {
            "content": "{}",
            "usage": {"total_tokens": 0}
        }
