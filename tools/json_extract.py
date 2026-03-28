import json
import re

def extract_json(content: str) -> dict:
    # Try fenced block first
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL | re.IGNORECASE)
    if fenced:
        return json.loads(fenced.group(1))

    # Fallback: balanced braces
    start = content.find("{")
    if start == -1:
        raise ValueError("No JSON object found")

    brace = 0
    for i in range(start, len(content)):
        if content[i] == "{":
            brace += 1
        elif content[i] == "}":
            brace -= 1
            if brace == 0:
                candidate = content[start:i+1]
                return json.loads(candidate)

    raise ValueError("Unbalanced JSON braces")
