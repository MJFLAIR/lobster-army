import re


def normalize_identifier(name: str) -> str:
    if not isinstance(name, str):
        return ""

    value = name.strip()
    if not value:
        return ""

    # Convert common CamelCase boundaries to snake_case first.
    value = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)

    # Normalize separators and drop non-alnum noise.
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_").lower()
