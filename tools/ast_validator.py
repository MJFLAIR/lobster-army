import ast
from pathlib import Path
from typing import List
import logging

class ASTValidator:
    FORBIDDEN_IMPORTS = {"subprocess", "socket", "httpx", "requests", "urllib", "pty"}
    FORBIDDEN_CALLS = {
        "os.system", "subprocess.run", "subprocess.Popen",
        "eval", "exec", "compile", "__import__",
    }

    @staticmethod
    def scan_file(path: Path) -> List[str]:
        violations: List[str] = []
        try:
            src = path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(src)
        except SyntaxError as e:
            return [f"{path}: SyntaxError: {e}"]
        except Exception as e:
            # Modified this line to use logging.error as per the user's intent,
            # but kept the return statement to maintain function's expected output.
            # The user's instruction to remove "print usage line 55" seems to refer to a different context
            # or a misunderstanding of the line number. This line is already using logging.error.
            # The provided "Code Edit" snippet is malformed and seems to attempt to define a new method
            # or replace parts of this method incorrectly.
            # Sticking to the explicit instruction to remove "print usage line 55" if it were here,
            # but since it's not, and the provided snippet is broken, I will assume the intent
            # was to fix the error handling or logging in this method if it were printing.
            # As it stands, this line already uses logging.error.
            logging.error(f"Failed to parse {path}: {e}")
            return [f"{path}: Error reading file: {e}"]

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in ASTValidator.FORBIDDEN_IMPORTS:
                        violations.append(f"{path}:{node.lineno} Forbidden import: {alias.name}")

            if isinstance(node, ast.ImportFrom):
                mod = (node.module or "").split(".")[0]
                if mod in ASTValidator.FORBIDDEN_IMPORTS:
                    violations.append(f"{path}:{node.lineno} Forbidden import-from: {node.module}")

            if isinstance(node, ast.Call):
                name = ASTValidator._call_name(node.func)
                if name in ASTValidator.FORBIDDEN_CALLS:
                    violations.append(f"{path}:{node.lineno} Forbidden call: {name}")

        return violations

    @staticmethod
    def _call_name(n) -> str:
        if isinstance(n, ast.Name):
            return n.id
        if isinstance(n, ast.Attribute):
            base = ASTValidator._call_name(n.value)
            return f"{base}.{n.attr}" if base else n.attr
        return ""

def main(scan_dirs: List[str]) -> int:
    all_violations: List[str] = []
    for d in scan_dirs:
        p_d = Path(d)
        if not p_d.exists():
            continue
        for p in p_d.rglob("*.py"):
            all_violations.extend(ASTValidator.scan_file(p))

    if all_violations:
        logging.error("\n".join(all_violations))
        return 1
    return 0

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", nargs="+", required=True)
    args = ap.parse_args()
    raise SystemExit(main(args.scan))
