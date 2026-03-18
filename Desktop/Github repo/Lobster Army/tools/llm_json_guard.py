import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class GuardResult:
    ok: bool
    raw_text: str
    cleaned_text: str
    extracted_text: Optional[str]
    data: Optional[Any]
    error: Optional[str]


class LLMJSONGuard:
    """
    Production-grade JSON guard for Lobster Army.

    Features:
    - strips markdown code fences
    - trims leading / trailing junk
    - extracts first balanced JSON object or array
    - parses JSON safely
    - optional root type enforcement
    - optional custom schema validator hook
    - fail-close by default
    """

    def __init__(
        self,
        *,
        allow_root_object: bool = True,
        allow_root_array: bool = False,
        max_scan_chars: int = 200_000,
    ) -> None:
        self.allow_root_object = allow_root_object
        self.allow_root_array = allow_root_array
        self.max_scan_chars = max_scan_chars

    def parse(
        self,
        raw_text: str,
        *,
        validator: Optional[Callable[[Any], None]] = None,
    ) -> GuardResult:
        if raw_text is None:
            return GuardResult(
                ok=False,
                raw_text="",
                cleaned_text="",
                extracted_text=None,
                data=None,
                error="raw_text is None",
            )

        cleaned = self._clean_text(raw_text)
        extracted = self._extract_first_json_block(cleaned)

        if not extracted:
            return GuardResult(
                ok=False,
                raw_text=raw_text,
                cleaned_text=cleaned,
                extracted_text=None,
                data=None,
                error="no JSON block found",
            )

        try:
            data = json.loads(extracted)
        except Exception as e:
            return GuardResult(
                ok=False,
                raw_text=raw_text,
                cleaned_text=cleaned,
                extracted_text=extracted,
                data=None,
                error=f"json.loads failed: {e}",
            )

        if isinstance(data, dict) and not self.allow_root_object:
            return GuardResult(
                ok=False,
                raw_text=raw_text,
                cleaned_text=cleaned,
                extracted_text=extracted,
                data=None,
                error="root object is not allowed",
            )

        if isinstance(data, list) and not self.allow_root_array:
            return GuardResult(
                ok=False,
                raw_text=raw_text,
                cleaned_text=cleaned,
                extracted_text=extracted,
                data=None,
                error="root array is not allowed",
            )

        if not isinstance(data, (dict, list)):
            return GuardResult(
                ok=False,
                raw_text=raw_text,
                cleaned_text=cleaned,
                extracted_text=extracted,
                data=None,
                error="root must be object or array",
            )

        if validator is not None:
            try:
                validator(data)
            except Exception as e:
                return GuardResult(
                    ok=False,
                    raw_text=raw_text,
                    cleaned_text=cleaned,
                    extracted_text=extracted,
                    data=None,
                    error=f"validator failed: {e}",
                )

        return GuardResult(
            ok=True,
            raw_text=raw_text,
            cleaned_text=cleaned,
            extracted_text=extracted,
            data=data,
            error=None,
        )

    def parse_object(
        self,
        raw_text: str,
        *,
        validator: Optional[Callable[[dict], None]] = None,
    ) -> GuardResult:
        def _validator(data: Any) -> None:
            if not isinstance(data, dict):
                raise ValueError("root must be a JSON object")
            if validator:
                validator(data)

        return self.parse(raw_text, validator=_validator)

    def _clean_text(self, text: str) -> str:
        text = text[: self.max_scan_chars].strip()

        # Remove leading / trailing markdown fences if present
        # Examples:
        # ```json ... ```
        # ``` ... ```
        text = re.sub(r"^\s*```(?:json|JSON)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)

        # Remove common leading chatter lines before JSON
        # We still do structural extraction later, so this is just cleanup.
        text = text.strip()

        return text

    def _extract_first_json_block(self, text: str) -> Optional[str]:
        """
        Extract the first balanced JSON object {...} or array [...].
        Ignores braces inside strings.
        """
        start_positions = []
        if self.allow_root_object:
            idx = text.find("{")
            if idx != -1:
                start_positions.append(idx)
        if self.allow_root_array:
            idx = text.find("[")
            if idx != -1:
                start_positions.append(idx)

        if not start_positions:
            return None

        start = min(start_positions)
        opening = text[start]
        closing = "}" if opening == "{" else "]"

        depth = 0
        in_string = False
        escape = False

        for i in range(start, len(text)):
            ch = text[i]

            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue

            if ch == opening:
                depth += 1
            elif ch == closing:
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

        return None


def require_keys(*required_keys: str) -> Callable[[dict], None]:
    def _validator(data: dict) -> None:
        missing = [k for k in required_keys if k not in data]
        if missing:
            raise ValueError(f"missing required keys: {missing}")
    return _validator


def require_pr_gate_schema(data: dict) -> None:
    if not isinstance(data, dict):
        raise ValueError("root must be dict")

    decision = data.get("decision")
    score = data.get("score")
    reason = data.get("reason")

    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be 'approve' or 'reject'")

    if not isinstance(score, (int, float)):
        raise ValueError("score must be number")

    if score < 0.0 or score > 1.0:
        raise ValueError("score must be between 0.0 and 1.0")

    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason must be non-empty string")