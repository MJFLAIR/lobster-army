import re


def normalize_whitespace(text: str) -> str:
    """
    Normalize repeated whitespace into single spaces and trim edges.
    """
    return " ".join(text.split())


def slugify(text: str) -> str:
    """
    Convert text into a lowercase URL-friendly slug.
    """
    text = normalize_whitespace(text).lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text)
    return text.strip("-")
