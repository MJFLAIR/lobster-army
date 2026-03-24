import os

def load_prompt(name: str) -> str:
    # Ensure name ends with .txt
    if not name.endswith(".txt"):
        name = name + ".txt"
        
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", name)
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        # Fallback to local execution relative if needed
        # Assuming run from root
        return f"PROMPT_NOT_FOUND: {prompt_path}"
