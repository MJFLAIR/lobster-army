import os

SANDBOX_ROOT = os.path.abspath("sandbox")

def write_file(path: str, content: str, overwrite: bool = False) -> dict:
    """Safely writes content bound rigidly within a designated sandbox directory."""
    try:
        # Guardrail 2: traversal check natively protecting against escaping paths up front
        if ".." in path:
            return {"status": "failed", "error": "Path traversal detected"}
            
        target_path = os.path.abspath(os.path.join(SANDBOX_ROOT, path))

        # Guardrail 1: Sandbox boundaries logically mapped
        if not target_path.startswith(SANDBOX_ROOT):
            return {"status": "failed", "error": "Path outside sandbox"}

        # Structuring directory arrays natively avoiding crashing IO bindings
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        # Guardrail 3: Strict limitations against blind overwrite modifications
        if os.path.exists(target_path) and not overwrite:
            return {"status": "failed", "error": "File exists"}

        # Write execution path
        with open(target_path, "w", encoding="utf-8", errors="strict") as f:
            f.write(content)

        return {
            "status": "success",
            "path": target_path,
            "bytes_written": len(content)
        }

    except Exception as e:
        return {"status": "failed", "error": str(e)}
