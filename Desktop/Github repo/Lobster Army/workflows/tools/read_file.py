import os

def read_file(path: str) -> dict:
    """Reads a file safely for LLM context injection."""
    try:
        if ".." in path:
            return {"status": "failed", "error": "directory traversal not allowed"}
            
        if os.path.isabs(path):
            return {"status": "failed", "error": "absolute paths not allowed"}
            
        base_dir = os.path.abspath(os.getcwd())
        target_path = os.path.abspath(os.path.join(base_dir, path))
        
        if not target_path.startswith(base_dir):
            return {"status": "failed", "error": "path outside project root"}
            
        if not os.path.exists(target_path):
            return {"status": "failed", "error": "file not found"}
            
        if not os.path.isfile(target_path):
            return {"status": "failed", "error": "not a file"}
            
        max_size = 100 * 1024
        content = ""
        with open(target_path, "r", encoding="utf-8", errors="strict") as f:
            content = f.read(max_size)
            
        return {
            "status": "success",
            "content": content
        }
        
    except UnicodeDecodeError:
        return {"status": "failed", "error": "binary files not supported"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}
